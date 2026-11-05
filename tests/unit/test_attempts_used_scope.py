"""attempts_used is counted for the assessments asked about, never the whole
history (M3-E decision 5)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.infrastructure.assessment.repositories import SqlAlchemyAttemptRepository


@pytest.mark.asyncio
async def test_attempts_used_is_counted_only_for_the_assessments_asked_about():
    # M3-E decision 5: one grouped query restricted to the page's ids, and none
    # at all for an empty page.
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    repository = SqlAlchemyAttemptRepository(session)

    assert await repository.counts_by_assessment("user", "tenant", []) == {}
    session.execute.assert_not_awaited()

    await repository.counts_by_assessment("user", "tenant", ["a1", "a2"])
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect())).lower()
    assert "assessment_attempts.assessment_id in" in sql
    assert "group by assessment_attempts.assessment_id" in sql
