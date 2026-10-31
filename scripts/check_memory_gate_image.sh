#!/usr/bin/env bash
# The learning-memory gate on real images:
#
#   scripts/check_memory_gate_image.sh <production image> <runtime stage image>
#
# A production image misconfigured as development or testing must refuse to
# start with memory requested. The runtime stage differs only by the marker and
# must accept the same settings, so the refusal is shown to come from the marker.
set -euo pipefail

production=$1
runtime=$2
state='from app.core.config import settings; print(settings.learning_memory_allowed)'

for environment in development testing; do
  # The service's own start command, not an import: this is what must refuse.
  if output=$(timeout 180 docker run --rm --network none -e APP_ENVIRONMENT="$environment" \
    -e LEARNING_MEMORY_ENABLED=true "$production" uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1); then
    echo "FAIL: the production image started with APP_ENVIRONMENT=$environment and memory requested" >&2
    exit 1
  fi
  if ! grep -q "LEARNING_MEMORY_ENABLED is refused" <<<"$output"; then
    echo "FAIL: the production image failed with APP_ENVIRONMENT=$environment, but not by the gate" >&2
    exit 1
  fi
  echo "ok: production image refuses memory with APP_ENVIRONMENT=$environment"
done

result=$(docker run --rm --network none -e APP_ENVIRONMENT=development "$production" python -c "$state")
if [[ "$result" != "False" ]]; then
  echo "FAIL: the production image has memory on by default" >&2
  exit 1
fi
echo "ok: production image starts with memory off by default"

result=$(docker run --rm --network none -e APP_ENVIRONMENT=development -e LEARNING_MEMORY_ENABLED=true \
  "$runtime" python -c "$state")
if [[ "$result" != "True" ]]; then
  echo "FAIL: the runtime stage refuses too, so the refusal above doesn't prove the marker" >&2
  exit 1
fi
echo "ok: the runtime stage, with no marker, accepts the same settings"
