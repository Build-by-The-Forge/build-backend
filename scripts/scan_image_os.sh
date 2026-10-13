#!/usr/bin/env bash
# OS package advisories in a built image (backend hardening C8c).
#
#   scripts/scan_image_os.sh <image>
#
# Trivy, pinned by version and digest, scans the image's Debian packages.
# Python packages are audited by `python -m scripts.audit_python_packages`.
#   1. Full report: every OS advisory, all severities, fixed or not.
#   2. Stale exceptions: an entry in security/trivyignore.yaml that matches no
#      finding fails the scan.
#   3. Gate: HIGH or CRITICAL advisories with a published fix fail the scan,
#      unless excepted (statement and expired_at) in security/trivyignore.yaml.
# Policy: docs/security-advisories.md. Needs network access for Trivy's
# database, which is kept in a Docker volume created for this run and removed
# afterwards; set TRIVY_CACHE_VOLUME to keep it in a named volume instead.
set -euo pipefail

image=${1:?usage: $0 <image>}
cd "$(dirname "$0")/.."
TRIVY=aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
# The first Python that actually runs (on Windows `python3` can be a store
# placeholder that only prints a message).
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null && "$candidate" -c "import sys" >/dev/null 2>&1; then
    PYTHON=$candidate
    break
  fi
done
if [[ -z $PYTHON ]]; then
  echo "no working python3 or python found" >&2
  exit 2
fi

# Windows Git Bash: Docker needs C:/... host paths and no MSYS path conversion.
export MSYS_NO_PATHCONV=1
security_dir=$( (cd security && (pwd -W 2>/dev/null || pwd)) )

report=$(mktemp)
cache=${TRIVY_CACHE_VOLUME:-}
created_volume=""
cleanup() {
  rm -f -- "$report"
  if [[ -n $created_volume ]]; then docker volume rm "$created_volume" >/dev/null; fi
}
trap cleanup EXIT
if [[ -z $cache ]]; then
  cache=$(docker volume create "trivy-cache-$$-$RANDOM")
  created_volume=$cache
fi
trivy() {
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$security_dir:/security:ro" \
    -v "$cache:/root/.cache" "$TRIVY" image --quiet --scanners vuln --pkg-types os "$@" "$image"
}

echo "OS package scan: $image ($TRIVY)"
trivy --format json >"$report"

# A native Windows Python needs the Windows form of the temporary path.
report_for_python=$(cygpath -w "$report" 2>/dev/null || echo "$report")
"$PYTHON" - "$report_for_python" security/trivyignore.yaml <<'PY'
import json
import re
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
found = [v for r in report.get("Results", []) for v in (r.get("Vulnerabilities") or [])]
os_name = report.get("Metadata", {}).get("OS", {})
print(f"  {os_name.get('Family', '?')} {os_name.get('Name', '?')}: {len(found)} OS advisories")
for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"):
    hits = [v for v in found if v.get("Severity") == severity]
    if hits:
        print(f"    {severity}: {len(hits)} ({sum(1 for v in hits if v.get('FixedVersion'))} with a fix)")
for v in sorted(found, key=lambda v: (v["Severity"], v["VulnerabilityID"], v["PkgName"])):
    if v["Severity"] in ("CRITICAL", "HIGH"):
        print(f"    {v['Severity']} {v['VulnerabilityID']} {v['PkgName']} {v.get('InstalledVersion')}"
              f" fixed in: {v.get('FixedVersion') or 'none'} ({v.get('Status', '?')})")
ids = {v["VulnerabilityID"] for v in found}
excepted = re.findall(r"^\s*-\s*id:\s*(\S+)", open(sys.argv[2], encoding="utf-8").read(), re.M)
stale = [i for i in excepted if i not in ids]
for i in stale:
    print(f"  FAIL excepted {i} in security/trivyignore.yaml no longer matches any finding: remove it")
sys.exit(1 if stale else 0)
PY

echo "  gate: HIGH or CRITICAL with a published fix, exceptions applied"
trivy --skip-db-update --severity HIGH,CRITICAL --ignore-unfixed --ignorefile /security/trivyignore.yaml \
  --exit-code 1 --format table
echo "  ok   no fixable HIGH or CRITICAL OS advisory"
