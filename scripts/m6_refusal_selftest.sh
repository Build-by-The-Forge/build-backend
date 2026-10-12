#!/usr/bin/env bash
# Self-test for the M6 refusal check in scripts/m6_production_startup.sh.
#
#   scripts/m6_refusal_selftest.sh        # after the gate has built its images
#
# refuses() may count a startup failure as "unsafe configuration refused" only
# when it is a settings validation error carrying the case's own message. This
# feeds it three unrelated startup failures, each of which the check before
# C1a counted as a refusal, and requires for each that:
#   - the import really fails, with the intended error class, so a check that
#     trusted the exit status alone would have passed it;
#   - refuses() does not count it as a refusal;
#   - nothing reported carries a configuration secret.
# It also requires that a failed boot's log is printed with input values
# redacted. It covers these regressions only, not every possible startup
# failure.
#
# Fixtures are built on each run FROM the current build-m3-backend image (its
# ID, tagged for the run) and removed afterwards, with that tag; a temporary compose override, outside the
# repository, points only this script's runs at them. The gate's images and
# the working tree are not changed.
#
# Sourcing this file defines the checks without running them.
set -uo pipefail

# shellcheck source=scripts/m6_production_startup.sh
source "$(dirname "${BASH_SOURCE[0]}")/m6_production_startup.sh"

BASE_COMPOSE=("${COMPOSE[@]}")
BASE_ID=""
BASE_TAG=""
RUN_ID=""
FIXTURE=""
FIXTURES=()
OVERRIDE_DIR=""

cleanup() {
  local tag
  for tag in "${FIXTURES[@]}"; do
    docker rmi "$tag" >/dev/null 2>&1 || echo "  note: could not remove fixture image $tag"
  done
  FIXTURES=()
  if [[ -n $OVERRIDE_DIR ]]; then
    rm -f -- "$OVERRIDE_DIR/override.yml"
    rmdir -- "$OVERRIDE_DIR"
    OVERRIDE_DIR=""
  fi
  COMPOSE=("${BASE_COMPOSE[@]}")
}

build_fixture() { # name dockerfile-instruction...
  local tag="build-m3-selftest:$1-$RUN_ID"
  shift
  if ! printf '%s\n' "FROM $BASE_TAG" "$@" | docker build -q -t "$tag" - >/dev/null; then
    bad "could not build fixture $tag"
    return 1
  fi
  FIXTURES+=("$tag")
  FIXTURE=$tag
}

use_backend_image() { # image
  printf 'services:\n  backend:\n    image: %s\n' "$1" >"$OVERRIDE_DIR/override.yml"
  COMPOSE=("${BASE_COMPOSE[@]}" -f "$OVERRIDE_DIR/override.yml")
}

secret_free() { # label text
  local secret
  for secret in "$B2A" "$A2B" "$JWT"; do
    if [[ $2 == *"$secret"* ]]; then
      bad "$1: a configuration secret appeared in the output"
      return 1
    fi
  done
}

# label expected-error-class message-of-a-rule extra-args...
expect_unrelated() {
  local label=$1 class=$2 message=$3
  shift 3
  if refuses backend "$message" "$@"; then
    bad "$label: counted as a refusal (got: $REFUSAL_GOT)"
    return
  fi
  if [[ $REFUSAL_GOT == "started without error" ]]; then
    bad "$label: the fixture did not fail, so this case tests nothing"
    return
  fi
  if [[ $REFUSAL_GOT != "$class" ]]; then
    bad "$label: expected $class, got: $REFUSAL_GOT"
    return
  fi
  secret_free "$label" "$REFUSAL_GOT" || return
  pass "$label: not counted as a refusal (import failed with $class)"
}

main() {
  if ! BASE_ID=$(docker image inspect -f '{{.Id}}' build-m3-backend 2>/dev/null); then
    bad "no build-m3-backend image: build it first (scripts/m3_boundary_gate.sh)"
    return
  fi
  RUN_ID=$(rnd | cut -c1-12)
  OVERRIDE_DIR=$(mktemp -d)
  trap cleanup EXIT
  # BuildKit cannot build FROM a bare image ID, so the ID read above gets a
  # tag of its own for this run (build-m3-backend itself is never re-tagged).
  BASE_TAG="build-m3-selftest:base-$RUN_ID"
  if ! docker tag "$BASE_ID" "$BASE_TAG"; then
    bad "could not tag the base image $BASE_ID"
    return
  fi
  FIXTURES+=("$BASE_TAG")

  echo "M6 refusal self-test (fixtures from build-m3-backend ${BASE_ID:7:12})"
  expect_unrelated "broken database URL" sqlalchemy.exc.ArgumentError \
    "CORS_ALLOWED_ORIGINS must list exact origins" "${BACKEND_PROD[@]}" -e POSTGRES_URL=not-a-url

  # An unsafe configuration too: the unrelated failure must still not count.
  if build_fixture missing-module "RUN pip uninstall -y -q structlog"; then
    use_backend_image "$FIXTURE"
    expect_unrelated "missing module (structlog uninstalled)" ModuleNotFoundError \
      "AUTH_JWT_SECRET is required" "${BACKEND_PROD[@]}" -e AUTH_JWT_SECRET=
  fi
  if build_fixture unreadable-config "RUN chmod 000 /app/app/core/config.py" "USER 65534:65534"; then
    use_backend_image "$FIXTURE"
    expect_unrelated "unreadable app/core/config.py (unprivileged user)" PermissionError \
      "AUTH_JWT_SECRET is required" "${BACKEND_PROD[@]}" -e AUTH_JWT_SECRET=
  fi
  COMPOSE=("${BASE_COMPOSE[@]}")

  # A boot refused by validation prints pydantic's input_value; it must be
  # redacted before the log is shown.
  if boots backend /health/live "${BACKEND_PROD[@]}" -e CORS_ALLOWED_ORIGINS='*'; then
    bad "failed-boot log: backend booted with wildcard CORS"
  elif [[ $BOOT_LOG != *"input_value=<redacted>"* ]]; then
    bad "failed-boot log: no redacted input_value, so redaction was not exercised"
  elif secret_free "failed-boot log" "$BOOT_LOG"; then
    pass "failed-boot log: input values redacted, no secret shown"
  fi

  cleanup
  trap - EXIT
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main
  exit "$fail"
fi
