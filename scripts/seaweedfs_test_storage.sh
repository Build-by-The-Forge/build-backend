#!/usr/bin/env bash
# A real S3-compatible service for the object-storage tests: SeaweedFS,
# pinned by digest (Phase 3 plan, D1 as amended). Used by the CI storage-gate
# job and for local runs.
#
#   scripts/seaweedfs_test_storage.sh start ENV_FILE   start, prove ready, write the test config
#   scripts/seaweedfs_test_storage.sh stop             remove the container and its data
#
# - Identities are generated for this run:
#   - admin creates the buckets during setup only and is never written out;
#   - writer-a may read, write and list bucket A; reader-a may only read A;
#   - writer-b may read, write and list bucket B.
# - The service runs as the invoking user, with its data on tmpfs, and
#   publishes only the S3 port, on 127.0.0.1.
# - Volumes are sized for a test store: 64 volumes of at most 64 MB. By
#   default SeaweedFS derives the volume count from free space divided by a
#   30 GB size limit; on tmpfs or a CI disk that is one volume, and then
#   every bucket after the first has no writable volume (HTTP 500).
# - Readiness is proven by a real write (admin creates both buckets), not by
#   /healthz, which answers before the master has elected a leader. Setup
#   fails closed after a timeout.
# - Before handing over, it checks that an anonymous request for a real
#   object is denied.
# - ENV_FILE receives OBJECT_STORAGE_TEST_* (mode 600). In GitHub Actions,
#   pass "$GITHUB_ENV"; each secret is masked in the log first.
# - Needs: a Linux shell (CI, WSL), docker, and python with boto3
#   (requirements.txt).
set -euo pipefail

IMAGE="chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d"
NAME="build-test-seaweedfs"
PORT="${SEAWEEDFS_TEST_PORT:-8333}"
BUCKET_A="build-test-a"
BUCKET_B="build-test-b"
WORKDIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/build-test-seaweedfs"

stop() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORKDIR"
}

start() {
  local env_file="$1"
  stop
  mkdir -p "$WORKDIR"
  chmod 700 "$WORKDIR"

  # Identities and their configuration, generated for this run.
  python - "$WORKDIR" "$BUCKET_A" "$BUCKET_B" <<'PY'
import json, os, secrets, sys
workdir, bucket_a, bucket_b = sys.argv[1:]
def identity(name):
    return name, "BUILDTEST" + secrets.token_hex(6).upper(), secrets.token_urlsafe(30)
admin, writer_a, reader_a, writer_b = (identity(n) for n in ("admin", "writer-a", "reader-a", "writer-b"))
config = {"identities": [
    {"name": admin[0], "credentials": [{"accessKey": admin[1], "secretKey": admin[2]}],
     "actions": ["Admin", "Read", "Write", "List"]},
    {"name": writer_a[0], "credentials": [{"accessKey": writer_a[1], "secretKey": writer_a[2]}],
     "actions": [f"Read:{bucket_a}", f"Write:{bucket_a}", f"List:{bucket_a}"]},
    {"name": reader_a[0], "credentials": [{"accessKey": reader_a[1], "secretKey": reader_a[2]}],
     "actions": [f"Read:{bucket_a}"]},
    {"name": writer_b[0], "credentials": [{"accessKey": writer_b[1], "secretKey": writer_b[2]}],
     "actions": [f"Read:{bucket_b}", f"Write:{bucket_b}", f"List:{bucket_b}"]},
]}
def write(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
write(os.path.join(workdir, "s3.json"), json.dumps(config))
write(os.path.join(workdir, "admin"), f"{admin[1]}:{admin[2]}")
write(os.path.join(workdir, "identities"), "".join(
    f"{n}={a}:{s}\n" for n, a, s in (writer_a, reader_a, writer_b)))
PY

  docker create --name "$NAME" \
    --user "$(id -u):$(id -g)" \
    --tmpfs "/data:uid=$(id -u),gid=$(id -g)" \
    -p "127.0.0.1:${PORT}:8333" \
    "$IMAGE" server -dir=/data -s3 -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json \
    -master.volumeSizeLimitMB=64 -volume.max=64 >/dev/null
  # The configuration holds secrets. It is copied in, keeping its owner and
  # 0600 mode, and never bind-mounted: a bind-mount source that disappears is
  # recreated by Docker as a root-owned directory. The host copy is deleted
  # at once.
  docker cp -a "$WORKDIR/s3.json" "$NAME:/etc/seaweedfs/s3.json"
  rm -f "$WORKDIR/s3.json"
  docker start "$NAME" >/dev/null

  # Ready means: the master has a leader, and a signed write succeeds.
  local deadline=$((SECONDS + 120))
  until docker exec "$NAME" wget -qO- http://127.0.0.1:9333/cluster/status 2>/dev/null | grep -q '"IsLeader":true'; do
    if ((SECONDS > deadline)); then
      echo "SeaweedFS master elected no leader within 120 s" >&2
      docker logs "$NAME" 2>&1 | tail -30 >&2
      exit 1
    fi
    sleep 1
  done
  python - "http://127.0.0.1:${PORT}" "$WORKDIR/admin" "$BUCKET_A" "$BUCKET_B" <<'PY'
import sys, time
import boto3, httpx
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
endpoint, admin_file, *buckets = sys.argv[1:]
access, secret = open(admin_file).read().split(":", 1)
s3 = boto3.session.Session().client(
    "s3", endpoint_url=endpoint, region_name="us-east-1",
    aws_access_key_id=access, aws_secret_access_key=secret,
    config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 1},
                  connect_timeout=3, read_timeout=10,
                  request_checksum_calculation="when_required",
                  response_checksum_validation="when_required"))
deadline = time.monotonic() + 90
for bucket in buckets:
    while True:
        try:
            s3.create_bucket(Bucket=bucket)
            break
        except ClientError as e:
            if e.response["Error"].get("Code") in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                break
            error = e.response["Error"].get("Code")
        except BotoCoreError as e:
            error = type(e).__name__
        if time.monotonic() > deadline:
            sys.exit(f"bucket {bucket} could not be created within 90 s: {error}")
        time.sleep(1)
# Prove the write path in every bucket (each needs writable volumes of its
# own), and private access with a real object.
for bucket in buckets:
    s3.put_object(Bucket=bucket, Key="setup/readiness-probe", Body=b"ready")
anonymous = httpx.get(f"{endpoint}/{buckets[0]}/setup/readiness-probe", timeout=5)
for bucket in buckets:
    s3.delete_object(Bucket=bucket, Key="setup/readiness-probe")
if anonymous.status_code != 403 or "<Code>AccessDenied</Code>" not in anonymous.text:
    sys.exit(f"anonymous object access was not denied (HTTP {anonymous.status_code})")
print(f"SeaweedFS ready: buckets {', '.join(buckets)} created; anonymous object access denied")
PY

  # Test configuration: no admin credentials.
  local lines=(
    "OBJECT_STORAGE_TEST_ENDPOINT=http://127.0.0.1:${PORT}"
    "OBJECT_STORAGE_TEST_REGION=us-east-1"
    "OBJECT_STORAGE_TEST_BUCKET_A=${BUCKET_A}"
    "OBJECT_STORAGE_TEST_BUCKET_B=${BUCKET_B}"
  )
  local name value key
  while IFS='=' read -r name value || [[ -n "$name" ]]; do
    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
      echo "::add-mask::${value#*:}"
    fi
    key="${name//-/_}"
    lines+=("OBJECT_STORAGE_TEST_${key^^}=${value}")
  done <"$WORKDIR/identities"
  if [[ ! -e "$env_file" ]]; then
    (umask 077 && : >"$env_file")
  fi
  printf '%s\n' "${lines[@]}" >>"$env_file"
  rm -f "$WORKDIR/admin" "$WORKDIR/identities"
}

case "${1:-}" in
  start) start "${2:?usage: $0 start ENV_FILE}" ;;
  stop) stop ;;
  *)
    echo "usage: $0 start ENV_FILE | stop" >&2
    exit 2
    ;;
esac
