"""THROWAWAY: proves a failing pytest step stays red with the summary and artifact steps green. Never merged."""


def test_deliberate_failure_in_the_test_job():
    assert 1 == 2, "deliberate"
