from dataclasses import dataclass


@dataclass(slots=True)
class StartAttemptCommand:
    assessment_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class GetAttemptCommand:
    attempt_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class ListMyAttemptsCommand:
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class SubmitAttemptCommand:
    attempt_id: str
    tenant_id: str
    user_id: str
