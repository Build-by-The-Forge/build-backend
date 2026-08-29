from dataclasses import dataclass


@dataclass(slots=True)
class SubmitBenchmarkReviewCommand:
    curriculum_id: str
    actor_id: str
    actor_email: str
    notes: str | None = None


@dataclass(slots=True)
class ApproveBenchmarkCommand:
    curriculum_id: str
    reviewer_id: str
    reviewer_email: str
    reason: str


@dataclass(slots=True)
class RejectBenchmarkCommand:
    curriculum_id: str
    reviewer_id: str
    reviewer_email: str
    reason: str


@dataclass(slots=True)
class ReviseBenchmarkCommand:
    curriculum_id: str
    actor_id: str
    actor_email: str
    reason: str | None = None


@dataclass(slots=True)
class GetBenchmarkAuditTrailCommand:
    curriculum_id: str
