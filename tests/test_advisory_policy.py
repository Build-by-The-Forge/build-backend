"""The advisory exception policy (scripts/audit_python_packages.py) without
the network: parsing security/accepted-advisories.txt and judging findings."""

import datetime as dt

import pytest

from scripts.audit_python_packages import ACCEPTED_FILE, Acceptance, Finding, evaluate, parse_accepted

TODAY = dt.date(2026, 10, 13)


def finding(package="python-jose", advisory="CVE-2026-85394", aliases=("GHSA-3qf3-8w2g-rqmx",)):
    return Finding(scope="runtime", package=package, version="3.5.0", advisory=advisory, aliases=aliases, fixes=())


def accepted(advisory="CVE-2026-85394", package="python-jose", review_by=dt.date(2027, 1, 1)):
    return Acceptance(advisory=advisory, package=package, review_by=review_by, reason="assessed")


def test_the_committed_list_parses():
    parse_accepted(ACCEPTED_FILE.read_text(encoding="utf-8"))


def test_an_entry_needs_an_id_package_date_and_reason():
    (entry,) = parse_accepted("# comment\n\nCVE-1 Python_Jose 2027-01-01  # not reachable here\n")
    assert entry == Acceptance("CVE-1", "python-jose", dt.date(2027, 1, 1), "not reachable here")
    for bad in ("CVE-1 python-jose 2027-01-01", "CVE-1 python-jose  # no date", "CVE-1 python-jose 2027-13-01  # bad date"):
        with pytest.raises(ValueError):
            parse_accepted(bad)


def test_an_unaccepted_finding_fails():
    assert evaluate([finding()], [], TODAY) == ([finding()], [], [])


def test_an_acceptance_matches_the_advisory_or_an_alias_for_that_package():
    assert evaluate([finding()], [accepted()], TODAY) == ([], [], [])
    assert evaluate([finding()], [accepted(advisory="GHSA-3qf3-8w2g-rqmx")], TODAY) == ([], [], [])
    other_package = accepted(package="ecdsa")
    assert evaluate([finding()], [other_package], TODAY) == ([finding()], [other_package], [])


def test_a_stale_acceptance_fails():
    assert evaluate([], [accepted()], TODAY) == ([], [accepted()], [])


def test_an_acceptance_past_its_review_date_fails():
    expired = accepted(review_by=dt.date(2026, 10, 12))
    assert evaluate([finding()], [expired], TODAY) == ([], [], [expired])
    on_the_day = accepted(review_by=TODAY)
    assert evaluate([finding()], [on_the_day], TODAY) == ([], [], [])
