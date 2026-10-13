"""Known advisories in the backend's Python packages, under the exception policy.

    python -m scripts.audit_python_packages requirements

Runs pip-audit (installed by the CI job, pinned there) on the exact pins in
requirements.txt (runtime) and requirements-dev.txt (development and test
tools, reported separately), with --no-deps: the files are the full closure.
Applies security/accepted-advisories.txt (docs/security-advisories.md) and
fails on any advisory that is not accepted, on an accepted entry that no
longer matches a finding, and on an entry past its review date. Needs network
access for the advisory database.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_FILE = ROOT / "security" / "accepted-advisories.txt"
ENTRY = re.compile(r"^(?P<advisory>\S+)\s+(?P<package>\S+)\s+(?P<review_by>\d{4}-\d{2}-\d{2})\s*#\s*(?P<reason>\S.*)$")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Finding:
    scope: str
    package: str
    version: str
    advisory: str
    aliases: tuple[str, ...]
    fixes: tuple[str, ...]


@dataclass(frozen=True)
class Acceptance:
    advisory: str
    package: str
    review_by: dt.date
    reason: str


def parse_accepted(text: str) -> list[Acceptance]:
    entries = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ENTRY.match(line)
        if not match:
            raise ValueError(f"accepted-advisories line {number}: expected '<id> <package> <YYYY-MM-DD>  # reason': {raw!r}")
        entries.append(
            Acceptance(
                advisory=match["advisory"],
                package=norm(match["package"]),
                review_by=dt.date.fromisoformat(match["review_by"]),
                reason=match["reason"],
            )
        )
    return entries


def evaluate(
    findings: list[Finding], accepted: list[Acceptance], today: dt.date
) -> tuple[list[Finding], list[Acceptance], list[Acceptance]]:
    """(unaccepted findings, stale acceptances, expired acceptances)."""

    def matches(acceptance: Acceptance, finding: Finding) -> bool:
        ids = {finding.advisory, *finding.aliases}
        return acceptance.package == norm(finding.package) and acceptance.advisory in ids

    unaccepted = [f for f in findings if not any(matches(a, f) for a in accepted)]
    stale = [a for a in accepted if not any(matches(a, f) for f in findings)]
    expired = [a for a in accepted if a.review_by < today]
    return unaccepted, stale, expired


def pip_audit(requirements: Path, scope: str) -> tuple[int, list[Finding]]:
    """(number of packages audited, findings) for one requirements file."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--no-deps",
            "--disable-pip",
            "--progress-spinner",
            "off",
        ]
        + ["--format", "json", "-r", str(requirements)],
        capture_output=True,
        text=True,
    )
    # Exit 1 means "vulnerabilities found"; anything else without JSON is an error.
    if result.returncode not in (0, 1) or not result.stdout.strip():
        raise RuntimeError(f"pip-audit failed ({result.returncode}) on {requirements.name}:\n{result.stderr.strip()}")
    dependencies = json.loads(result.stdout)["dependencies"]
    findings = [
        Finding(
            scope=scope,
            package=dep["name"],
            version=dep["version"],
            advisory=vuln["id"],
            aliases=tuple(vuln.get("aliases", [])),
            fixes=tuple(vuln.get("fix_versions", [])),
        )
        for dep in dependencies
        for vuln in dep.get("vulns", [])
    ]
    return len(dependencies), findings


def report(findings: list[Finding], counts: dict[str, int], today: dt.date) -> int:
    accepted = parse_accepted(ACCEPTED_FILE.read_text(encoding="utf-8"))
    for scope, count in counts.items():
        in_scope = {(f.package, f.advisory) for f in findings if f.scope == scope}
        print(f"  {scope}: {count} packages audited, {len(in_scope)} advisories")
    unaccepted, stale, expired = evaluate(findings, accepted, today)
    for f in sorted(set(unaccepted), key=lambda f: (f.scope, norm(f.package), f.advisory)):
        aliases = f" ({', '.join(f.aliases)})" if f.aliases else ""
        fixes = ", ".join(f.fixes) or "none"
        print(f"  FAIL {f.scope}: {f.package} {f.version}: {f.advisory}{aliases}; fixed in: {fixes}; not accepted")
    for a in stale:
        print(f"  FAIL accepted {a.advisory} for {a.package} no longer matches any finding: remove it")
    for a in expired:
        print(f"  FAIL accepted {a.advisory} for {a.package} is past its review date ({a.review_by}): re-assess it")
    if unaccepted or stale or expired:
        print("Advisory policy: docs/security-advisories.md")
        return 1
    print(f"  ok   every advisory is a reviewed acceptance ({len(accepted)} accepted)")
    return 0


def audit_requirements(today: dt.date) -> int:
    print("Python dependency audit (pinned requirements)")
    runtime_count, runtime = pip_audit(ROOT / "requirements.txt", "runtime")
    # The development scope is requirements-dev.txt without its
    # `-r requirements.txt` include, written out explicitly rather than
    # relying on how pip-audit treats includes.
    dev_lines = [
        line
        for line in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("-r")
    ]
    with tempfile.TemporaryDirectory() as tmp:
        dev_only = Path(tmp) / "requirements-dev-only.txt"
        dev_only.write_text("\n".join(dev_lines) + "\n", encoding="utf-8")
        dev_count, development = pip_audit(dev_only, "development")
    counts = {"runtime": runtime_count, "development": dev_count}
    return report(runtime + development, counts, today)


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["requirements"] and len(argv) == 1:
            return audit_requirements(dt.date.today())
    except (ValueError, RuntimeError) as error:
        print(f"  FAIL {error}", file=sys.stderr)
        return 2
    print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
