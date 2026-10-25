#!/usr/bin/env bash
# The object-storage secret keys of the m3 topology must appear nowhere they
# could leak: not in either image's history or configuration, and not in any
# container's logs (P3-1; plan gate "storage credentials appear in no image
# layer or log"). Values are read from deploy/m3.env and compared, never
# printed: a failure names the secret and where it was found, nothing more.
#
#   scripts/check_storage_secrets.sh      (after the topology has run)
set -euo pipefail

COMPOSE=(docker compose --env-file deploy/m3.env -f deploy/compose.m3.yml)
logs="$(mktemp)"
trap 'rm -f "$logs"' EXIT
"${COMPOSE[@]}" --profile gate logs --no-color >"$logs" 2>&1 || true

python3 - "$logs" <<'PY'
import subprocess, sys

logs_path = sys.argv[1]
names = ("OBJECT_STORAGE_ADMIN_SECRET_KEY", "OBJECT_STORAGE_BACKEND_SECRET_KEY", "OBJECT_STORAGE_AI_SECRET_KEY")
values = {}
for line in open("deploy/m3.env", encoding="utf-8"):
    name, _, value = line.strip().partition("=")
    if name in names and value:
        values[name] = value
missing = [n for n in names if n not in values]
if missing:
    sys.exit(f"deploy/m3.env lacks {', '.join(missing)}")

places = {"container logs": open(logs_path, encoding="utf-8", errors="replace").read()}
for image in ("build-m3-backend", "build-m3-ai-service"):
    for what, cmd in (("history", ["docker", "history", "--no-trunc", image]), ("config", ["docker", "image", "inspect", image])):
        places[f"{image} {what}"] = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

leaks = [f"{name} in {place}" for name, value in values.items() for place, text in places.items() if value in text]
if leaks:
    sys.exit("storage secret leaked: " + "; ".join(leaks))
print(f"storage secrets: none of {len(values)} found in {len(places)} images and logs")
PY
