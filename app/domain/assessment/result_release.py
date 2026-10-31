from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ResultRelease:
    """Staff released an assessment's results. Final: there is no way to withdraw it."""

    assessment_id: str
    tenant_id: str
    released_by: str | None
    released_at: datetime
