"""Summarise pytest JUnit reports for a GitHub Actions job summary.

    python scripts/ci_junit_summary.py pytest-junit.xml [more.xml ...] >> "$GITHUB_STEP_SUMMARY"

A red run explains itself: the failing and erroring tests, each with its first
error lines, are listed in Markdown, so nobody has to scrape a long log. It is
reporting only: it reads files, prints, and always exits 0, so it can never
change a job's result. A report that is missing (the tests didn't finish) or
unreadable is said so in the summary.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

MAX_FAILURES = 60
MAX_ERROR_LINES = 4
MAX_LINE = 200


def _clean(text: str) -> str:
    return text[:MAX_LINE].replace("`", "'").replace("\r", "")


def _problems(root: ET.Element) -> tuple[int, list[tuple[ET.Element, ET.Element]]]:
    cases = list(root.iter("testcase"))
    bad = []
    for case in cases:
        for tag in ("failure", "error"):
            found = case.find(tag)
            if found is not None:
                bad.append((case, found))
    return len(cases), bad


def summarise(paths: list[str]) -> str:
    out: list[str] = []
    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return "No JUnit report: the tests did not finish (see the run log)."
    total = 0
    failing: list[tuple[str, ET.Element, ET.Element]] = []
    for path in existing:
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            out.append(f"- `{os.path.basename(path)}` could not be read (see the run log).")
            continue
        count, bad = _problems(root)
        total += count
        failing.extend((os.path.basename(path), case, found) for case, found in bad)
    out.insert(0, f"### Tests: {total} run, {len(failing)} failing or erroring")
    for report, case, found in failing[:MAX_FAILURES]:
        # Which report, so which pytest invocation: postgres-gate runs four.
        out.append(f"- `{case.get('classname')}::{case.get('name')}` (`{report}`)")
        lines = [ln for ln in (found.text or "").splitlines() if ln.startswith("E ")][:MAX_ERROR_LINES]
        for line in lines or [found.get("message") or ""]:
            out.append(f"  - `{_clean(line)}`")
    if len(failing) > MAX_FAILURES:
        out.append(f"... and {len(failing) - MAX_FAILURES} more (see the JUnit artifact)")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    print(summarise(argv[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
