#!/usr/bin/env bash
# Production image checks (backend hardening C5b).
#
#   scripts/check_backend_image.sh <image>
#
# Fails unless the image holds what production runs and nothing else:
#   - /app is exactly the allowlist (app/, alembic/, alembic.ini,
#     scripts/provision_tenant.py);
#   - no development or test tooling is importable;
#   - no environment files, databases, git data, requirements files or test
#     directories anywhere under /app;
#   - no compiled bytecode or tool caches under /app (host artefacts);
#   - `pip check` is clean and the installed packages are exactly
#     requirements.txt's pins (markers evaluated for Linux);
#   - it runs as an unprivileged user that cannot change the code or the
#     installed packages, and owns /outbox (mode 0750).
# Runs the image with networking disabled; prints one line per check.
set -euo pipefail

image=${1:?usage: $0 <image>}
cd "$(dirname "$0")/.."

# The checks run as `python -c`, not from stdin: without `docker run -i` a
# script on stdin never reaches the container, and an empty script "passes".
CHECKS=$(cat <<'PY'
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

failed = False
ran = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global failed, ran
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok or not detail else f": {detail}"))
    failed |= not ok
    ran += 1


app = Path("/app")
top = sorted(p.name for p in app.iterdir())
check(top == ["alembic", "alembic.ini", "app", "scripts"], "/app holds only the allowlist", f"found {top}")
scripts = sorted(p.name for p in (app / "scripts").iterdir()) if (app / "scripts").is_dir() else []
check(scripts == ["provision_tenant.py"], "/app/scripts holds only provision_tenant.py", f"found {scripts}")

tools = ["pytest", "_pytest", "pytest_asyncio", "pytest_cov", "pytest_env", "ruff", "mypy", "pre_commit", "respx", "aiosqlite", "coverage"]
present = [m for m in tools if importlib.util.find_spec(m)]
check(not present, "no development or test tooling", f"importable: {present}")

banned = re.compile(r"^(\.env.*|m3\.env|.*\.db|.*\.sqlite3?|\.git|requirements.*\.txt|tests|pg_smoke|boundary)$")
hits = [str(p) for p in app.rglob("*") if banned.match(p.name)]
check(not hits, "no environment files, databases, git data, requirements or test directories", f"{hits[:5]}")

artefacts = [str(p) for p in app.rglob("*") if p.name in {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"} or p.suffix in {".pyc", ".pyo"}]
check(not artefacts, "no compiled bytecode or tool caches", f"{len(artefacts)} found, e.g. {artefacts[:3]}")

pip_check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
check(pip_check.returncode == 0, "pip check", pip_check.stdout.strip()[:200])


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# Markers are evaluated with the packaging library vendored in pip (the image
# has no separate packaging install), for this Linux image.
from pip._vendor.packaging.requirements import Requirement  # noqa: E402

pins = {}
for raw in os.environ["PINS"].splitlines():
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    req = Requirement(line)
    if req.marker is not None and not req.marker.evaluate():
        continue
    (spec,) = req.specifier
    pins[norm(req.name)] = spec.version
frozen = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True, text=True).stdout
installed = {norm(n): v for n, v in (l.split("==", 1) for l in frozen.splitlines() if "==" in l)}
for tool in ("pip", "setuptools", "wheel"):
    installed.pop(tool, None)
extra = sorted(set(installed) - set(pins))
missing = sorted(set(pins) - set(installed))
wrong = {k: (pins[k], installed[k]) for k in pins if k in installed and pins[k] != installed[k]}
check(not (extra or missing or wrong), f"installed packages are exactly requirements.txt ({len(pins)})",
      f"not pinned {extra}, missing {missing}, version differs {wrong}")

uid, gid = os.getuid(), os.getgid()
check(uid != 0 and gid != 0, "runs as an unprivileged user", f"uid {uid}, gid {gid}")

import sysconfig  # noqa: E402

purelib = sysconfig.get_paths()["purelib"]
writable = []
for target in (app, app / "app", Path(purelib)):
    probe = target / ".write-probe"
    try:
        probe.touch()
    except PermissionError:
        continue
    probe.unlink()
    writable.append(str(target))
check(not writable, "code and installed packages are not writable by it", f"writable: {writable}")

outbox = Path("/outbox")
info = outbox.stat() if outbox.is_dir() else None
check(info is not None and info.st_uid == uid and (info.st_mode & 0o777) == 0o750,
      "/outbox is owned by it, mode 0750",
      "missing" if info is None else f"owner {info.st_uid}, mode {oct(info.st_mode & 0o777)}")

print(f"checks run: {ran}")
sys.exit(1 if failed else 0)
PY
)
EXPECTED_CHECKS=10

echo "Production image checks: $image"
status=0
out=$(docker run --rm --network none -e PINS="$(cat requirements.txt)" --entrypoint python "$image" -c "$CHECKS" 2>&1) || status=$?
echo "$out" | grep -v '^checks run:' || true
# Every check must have run: a script that never started must not pass.
if ! grep -qx "checks run: $EXPECTED_CHECKS" <<<"$out"; then
  echo "  FAIL expected $EXPECTED_CHECKS checks to run; got: $(grep '^checks run:' <<<"$out" || echo none)"
  exit 1
fi
exit "$status"
