# Security advisories: audits and exceptions

The backend is audited for known advisories in three places. Each audit fails
closed: a finding fails it unless it is a reviewed exception.

| Audit | What it checks | Tool | Exceptions |
|---|---|---|---|
| Dependencies | the pinned packages in `requirements.txt` (runtime) and `requirements-dev.txt` (development and test tools) | pip-audit, pinned in CI | `security/accepted-advisories.txt` |
| Image packages | the Python packages actually installed in the built production image | pip-audit on the image's `pip freeze` | `security/accepted-advisories.txt` |
| Image OS packages | the Debian packages in the built production image | Trivy, pinned by version and digest | `security/trivyignore.yaml` |

The scripts are `python -m scripts.audit_python_packages` (dependencies and
image packages) and `scripts/scan_image_os.sh` (OS packages). CI runs them on
every change and on a weekly schedule, since new advisories appear without
any commit.

## Failure thresholds

- **Python packages** (both scopes): any advisory fails the audit, whatever
  its severity, unless it is accepted.
- **OS packages**: a HIGH or CRITICAL advisory fails the scan when Debian
  has published a fixed version. Advisories without a fix are listed in the
  report but do not fail it; the weekly run fails once a fix exists, and the
  remedy is then a newer base image or package, not an exception.

## Exceptions

An exception is allowed only when no fixed release exists, or the fix is
incompatible and that has been demonstrated. Each one needs:

- the advisory ID and the package;
- a review date, after which the audit fails again until it is re-assessed;
- a reason in the entry, and an assessment here that shows the vulnerable
  code is unreachable or not exploitable in this service, with the affected
  version, the exposure and any mitigation.

An audit also fails on an exception that no longer matches a finding, so an
exception cannot outlive its reason. Blanket rules (by severity, by package
or "all transitive") are not allowed.

## Current exceptions

None (Python and OS).
