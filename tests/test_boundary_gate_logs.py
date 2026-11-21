"""The boundary gate keeps its services' complete logs and the AI queue
state (scripts/gate_logs.sh, .github/workflows/boundary-gate.yml), so a
failure can be explained after the stack is torn down.

The helper runs against a fake ``docker``. What matters: it keeps whole logs
(never a tail), reads only IDs and counters from the task stream (never a
payload), redacts secrets before anything is written and withholds a file
that still holds one, does nothing without GATE_LOG_DIR, and can't change the
gate's exit status or outcome in either direction.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "gate_logs.sh"
GATE = ROOT / "scripts" / "m3_boundary_gate.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "boundary-gate.yml"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

DB_PASSWORD = "pg-pass-0123456789abcdef"
SIGNING_SECRET = "b2a-secret-fedcba9876543210"
ENV_FILE = f"POSTGRES_SUPERUSER_PASSWORD={DB_PASSWORD}\nBACKEND_TO_AI_SECRET={SIGNING_SECRET}\nAPP_NAME=build\nSHORT_KEY=abc\n"

# What the services might print: identifiers an investigation needs, and
# things that must never reach an artifact.
TASK_LINE = (
    '{"message": "ai_service_task_started", "job_id": "c6c73773-ecd3-4ed9-bc99-0dffb7780858", '
    '"task_id": "task_0bd5c489", "worker_id": "worker_734ed118", "entry_id": "1795209582694-0"}'
)
SENSITIVE_LOG = f"""2026-11-20T21:19:42.100Z ai-worker-1  | {TASK_LINE}
2026-11-20T21:19:43.000Z backend-1  | connecting postgresql://app:{DB_PASSWORD}@postgres:5432/build
2026-11-20T21:19:43.100Z backend-1  | signed with {SIGNING_SECRET} ok
2026-11-20T21:19:44.000Z ai-service-1  | Authorization: Bearer abc123.def456-ghi789
2026-11-20T21:19:44.100Z ai-service-1  | "x-build-signature": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
2026-11-20T21:19:44.200Z ai-service-1  | token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJlMTIz leaked
2026-11-20T21:19:44.300Z backend-1  | login for student@futa.edu.ng failed
2026-11-20T21:19:44.400Z backend-1  | "GET /content/my-documents?file_name=secret-notes.pdf HTTP/1.1" 200
2026-11-20T21:19:44.500Z backend-1  | password=hunter2hunter2 api_key: sk-live-123456
"""

# Records every invocation, then answers like docker compose would.
FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_DOCKER_CALLS"
[[ -n "${FAKE_DOCKER_FAIL:-}" ]] && exit 1
case " $* " in
  *" config --services "*) printf 'backend\nai-worker\nredis\n' ;;
  *" logs "*)
    if [[ -n "${FAKE_LOG_FILE:-}" ]]; then
      cat "$FAKE_LOG_FILE"
    else
      echo "complete log of ${@: -1}"
      echo "second line"
    fi ;;
  *" exec "*) echo "redis: $*" ;;
esac
"""


@pytest.fixture
def fake_docker(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, newline="\n")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    env_file = tmp_path / "m3.env"
    env_file.write_text(ENV_FILE, newline="\n")
    return {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DOCKER_CALLS": str(calls),
        "GATE_ENV_FILE": str(env_file),
    }, calls


def capture(env, label="snap", log_dir=None, fail=False, extra=None, path_prefix=None):
    full = {**os.environ, **env, **(extra or {})}
    if path_prefix:
        full["PATH"] = f"{path_prefix}{os.pathsep}{full['PATH']}"
    if log_dir is not None:
        full["GATE_LOG_DIR"] = str(log_dir)
    else:
        full.pop("GATE_LOG_DIR", None)
    if fail:
        full["FAKE_DOCKER_FAIL"] = "1"
    script = f'set -euo pipefail; COMPOSE=(docker compose); source "{HELPER.as_posix()}"; capture_gate_logs {label}; echo reached'
    return subprocess.run(["bash", "-c", script], env=full, capture_output=True, text=True, timeout=60)


def test_without_a_log_directory_nothing_is_done(fake_docker, tmp_path):
    env, calls = fake_docker
    result = capture(env)
    assert result.returncode == 0 and "reached" in result.stdout
    assert calls.read_text() == ""


def test_every_service_gets_its_complete_log_with_timestamps(fake_docker, tmp_path):
    env, calls = fake_docker
    out = tmp_path / "logs"
    result = capture(env, "after-main-suite", out)

    assert result.returncode == 0, result.stderr
    for service in ("backend", "ai-worker", "redis"):
        assert (out / "after-main-suite" / f"{service}.log").read_text().startswith(f"complete log of {service}")
    log_calls = [line for line in calls.read_text().splitlines() if " logs " in f" {line} "]
    assert len(log_calls) == 3
    assert all("--timestamps" in line and "--no-color" in line for line in log_calls)
    assert not any("--tail" in line or "--since" in line or "-n " in line for line in log_calls)


def test_the_task_stream_is_read_for_ids_and_counters_never_a_payload(fake_docker, tmp_path):
    env, calls = fake_docker
    out = tmp_path / "logs"
    capture(env, "final", out)

    state = (out / "final" / "ai-stream-state.txt").read_text()
    for section in ("XLEN", "XINFO GROUPS", "XINFO CONSUMERS ai_worker_group", "XPENDING ai_worker_group (summary)"):
        assert section in state
    redis_calls = [line for line in calls.read_text().splitlines() if " exec " in f" {line} "]
    commands = {re.search(r"redis-cli -n 1 (\w+)(?: (\w+))?", line).groups() for line in redis_calls}
    # Commands that return entry contents are never issued.
    assert not {c for c, _ in commands} & {"XRANGE", "XREVRANGE", "XREAD", "XREADGROUP", "GET", "KEYS"}
    assert ("XINFO", "STREAM") not in commands
    assert all("-n 1" in line for line in redis_calls)


def test_secrets_credentials_and_request_contents_never_reach_the_artifact(fake_docker, tmp_path):
    env, _ = fake_docker
    log = tmp_path / "sensitive.log"
    log.write_text(SENSITIVE_LOG, newline="\n")
    out = tmp_path / "logs"
    result = capture(env, "final", out, extra={"FAKE_LOG_FILE": str(log), "OCR_MODELS_TOKEN": "ocr-mirror-token-9876543210"})
    assert result.returncode == 0, result.stderr

    kept = (out / "final" / "backend.log").read_text()
    assert "REDACTION-FAILED" not in kept
    for secret in (
        DB_PASSWORD,  # a value from the env file
        SIGNING_SECRET,
        "abc123.def456-ghi789",  # a bearer token
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",  # a signature header
        "eyJhbGciOiJIUzI1NiJ9",  # a JWT
        "student@futa.edu.ng",  # an e-mail address
        "secret-notes.pdf",  # a query string
        "hunter2hunter2",  # a password field
        "sk-live-123456",  # an api key field
    ):
        assert secret not in kept, secret
    # What an investigation needs is kept: identifiers, timestamps, messages.
    for needed in (
        "2026-11-20T21:19:42.100Z",
        "ai_service_task_started",
        "c6c73773-ecd3-4ed9-bc99-0dffb7780858",
        "task_0bd5c489",
        "worker_734ed118",
        "1795209582694-0",
        "GET /content/my-documents",
        "login for",
    ):
        assert needed in kept, needed
    everything = "".join(p.read_text() for p in out.rglob("*") if p.is_file())
    assert "ocr-mirror-token-9876543210" not in everything


def test_a_short_or_non_secret_env_value_is_not_treated_as_a_secret(fake_docker, tmp_path):
    env, _ = fake_docker
    log = tmp_path / "plain.log"
    log.write_text("app build short abc\n", newline="\n")
    out = tmp_path / "logs"
    capture(env, "final", out, extra={"FAKE_LOG_FILE": str(log)})
    assert "app build short abc" in (out / "final" / "backend.log").read_text()


def test_a_file_that_still_holds_a_secret_after_filtering_is_withheld(fake_docker, tmp_path):
    """Fails closed: if the filter didn't remove a known secret (here a sed
    that passes everything through), nothing from that file is kept."""
    env, _ = fake_docker
    log = tmp_path / "sensitive.log"
    log.write_text(SENSITIVE_LOG, newline="\n")
    fake_bin = tmp_path / "passthrough-bin"
    fake_bin.mkdir()
    sed = fake_bin / "sed"
    sed.write_text("#!/usr/bin/env bash\ncat\n", newline="\n")
    sed.chmod(sed.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "logs"
    result = capture(env, "final", out, extra={"FAKE_LOG_FILE": str(log)}, path_prefix=str(fake_bin))

    assert result.returncode == 0 and "reached" in result.stdout
    kept = (out / "final" / "backend.log").read_text()
    assert kept.startswith("REDACTION-FAILED")
    assert DB_PASSWORD not in kept and SIGNING_SECRET not in kept


def test_a_failing_docker_or_an_unwritable_directory_cannot_fail_the_gate(fake_docker, tmp_path):
    env, _ = fake_docker
    broken_docker = capture(env, "final", tmp_path / "logs", fail=True)
    assert broken_docker.returncode == 0 and "reached" in broken_docker.stdout

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x")
    unwritable = capture(env, "final", blocker / "inside")
    assert unwritable.returncode == 0 and "reached" in unwritable.stdout


def test_the_manifest_ties_the_logs_to_the_run_attempt_job_and_revisions(fake_docker, tmp_path):
    env, _ = fake_docker
    out = tmp_path / "logs"
    github = {
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "Build-by-The-Forge/build-backend",
        "GITHUB_RUN_ID": "44818389586",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_JOB": "boundary-gate",
        "GITHUB_WORKFLOW": "boundary-gate",
        "BACKEND_REVISION": "801aa811654bc625031f0ab600c5f399589ae870",
        "AI_SERVICE_REVISION": "de4e5fc17364079f0aaf6e158894923eea442463",
    }
    capture(env, "after-main-suite", out, extra=github)
    capture(env, "final", out, extra={**github, "GITHUB_RUN_ATTEMPT": "9"})

    manifest = (out / "MANIFEST.txt").read_text()
    assert "https://github.com/Build-by-The-Forge/build-backend/actions/runs/44818389586" in manifest
    assert "attempt:    2" in manifest and "job:        boundary-gate" in manifest
    assert "801aa811654bc625031f0ab600c5f399589ae870" in manifest and "de4e5fc17364079f0aaf6e158894923eea442463" in manifest
    assert "attempt:    9" not in manifest  # written once, at the first snapshot


def test_the_gate_captures_before_it_removes_the_stack_and_never_masks_its_status():
    text = GATE.read_text()
    cleanup = text[text.index("cleanup() {") : text.index("trap cleanup EXIT")]
    assert "capture_gate_logs final || true" in cleanup
    assert cleanup.index("capture_gate_logs final") < cleanup.index("down -v")
    # The first snapshot sits straight after the main suite, before any restart.
    assert text.index("capture_gate_logs after-main-suite || true") > text.index('-m "not redis_down')
    assert text.index("capture_gate_logs after-main-suite || true") < text.index("stopping the scanner")
    # No capture call can end the script or set the failure status.
    assert not re.search(r"capture_gate_logs [\w-]+(?! \|\| true)$", text, re.M)


def test_the_workflow_uploads_the_logs_without_deciding_the_gates_result():
    text = WORKFLOW.read_text()
    gate_step = text[text.index("name: Boundary gate") : text.index("name: Service logs on failure")]
    assert "continue-on-error" not in gate_step  # the gate step still decides the job
    assert "GATE_LOG_DIR: ${{ github.workspace }}/gate-logs" in gate_step
    upload = text[text.index("name: Keep the gate's service logs") :]
    assert "if: always() && steps.gate.outcome != 'skipped'" in upload
    assert "continue-on-error: true" in upload  # a failed upload can't fail a passing gate
    assert re.search(r"uses: actions/upload-artifact@v\d+", upload)
    assert "boundary-gate-logs-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.job }}" in upload
    assert "path: gate-logs" in upload and "retention-days: 14" in upload
