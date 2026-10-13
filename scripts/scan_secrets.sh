#!/usr/bin/env bash
# Secret scan of the repository's tracked files (backend hardening, D-D).
#
#   scripts/scan_secrets.sh
#
# gitleaks 8.30.1, pinned by digest, with its default rules; findings are
# redacted, so no secret value reaches the log. It scans the tracked files as
# they are in the working tree (what a CI checkout contains), never untracked
# or ignored files: deploy/m3.env holds local secrets by design. Accepted
# findings are listed by fingerprint in .gitleaksignore, with their reasons
# in docs/security-advisories.md.
set -euo pipefail

cd "$(dirname "$0")/.."
GITLEAKS=zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f

# Windows Git Bash: Docker needs C:/... host paths and no MSYS path conversion.
export MSYS_NO_PATHCONV=1
host_path() { (cd "$1" && (pwd -W 2>/dev/null || pwd)); }

tree=$(mktemp -d)
trap 'rm -rf -- "$tree"' EXIT
git ls-files -z | tar --null --ignore-failed-read -T - -cf - | tar -xf - -C "$tree"

echo "Secret scan of tracked files ($GITLEAKS)"
docker run --rm -v "$(host_path "$tree"):/repo:ro" -v "$(host_path .):/ignore:ro" "$GITLEAKS" \
  dir /repo --redact --no-banner --exit-code 1 --gitleaks-ignore-path /ignore/.gitleaksignore
echo "  ok   no secrets in tracked files (accepted findings: .gitleaksignore)"
