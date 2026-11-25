"""THROWAWAY: the same, in the postgres-gate's pg_smoke step. Never merged."""


def test_deliberate_failure_in_pg_smoke():
    assert "a" == "b", "deliberate"
