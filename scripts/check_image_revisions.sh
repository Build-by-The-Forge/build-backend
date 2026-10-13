#!/usr/bin/env bash
# The gate's images were built from the revisions it is testing.
#
#   scripts/check_image_revisions.sh <backend-revision> <ai-service-revision>
#
# Compares each image's org.opencontainers.image.revision label (set by
# deploy/compose.m3.yml from BACKEND_REVISION and AI_SERVICE_REVISION) with
# the revision the gate recorded at its start. A mismatch means a stale image
# or a checkout that moved: the gate must not test it.
set -euo pipefail

backend=${1:?usage: $0 <backend-revision> <ai-service-revision>}
ai=${2:?usage: $0 <backend-revision> <ai-service-revision>}

fail=0
expect() { # image expected-revision
  local got
  got=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1" 2>/dev/null) || got="(no such image)"
  if [[ "$got" == "$2" ]]; then
    echo "  ok   $1 built from $2"
  else
    echo "  FAIL $1 built from ${got:-(no revision label)}, expected $2"
    fail=1
  fi
}

echo "Image revisions"
expect build-m3-backend "$backend"
expect build-m3-backend-test "$backend"
expect build-m3-ai-service "$ai"
exit "$fail"
