import pytest

from app.domain.curriculum.audit import (
    BenchmarkAuditAction,
    BenchmarkAuditLog,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCurriculum,
    BenchmarkStatus,
)


def test_benchmark_governance_lifecycle_full_flow() -> None:
    curriculum = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-100",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
    )
    assert curriculum.status == BenchmarkStatus.CANDIDATE

    # Direct submission before validation fails
    with pytest.raises(ValueError, match="only validated benchmarks can be submitted for review"):
        curriculum.submit_for_review()

    # 1. Validate
    curriculum.mark_validated()
    assert curriculum.status == BenchmarkStatus.VALIDATED

    # Direct activation from VALIDATED must now fail (governance enforcement)
    with pytest.raises(ValueError, match="only approved benchmarks can be activated"):
        curriculum.activate()

    # 2. Submit for review
    curriculum.submit_for_review(
        diff_fingerprint="abc123" * 10,
        notes="Review requested for national rollout.",
    )
    assert curriculum.status == BenchmarkStatus.UNDER_REVIEW
    assert curriculum.review_fingerprint == "abc123" * 10

    # Direct activation from UNDER_REVIEW fails
    with pytest.raises(ValueError, match="only approved benchmarks can be activated"):
        curriculum.activate()

    # 3. Approve
    curriculum.approve(
        reviewer_id="reviewer-1",
        reason="Curriculum conforms to NUC standards.",
    )
    assert curriculum.status == BenchmarkStatus.APPROVED

    # 4. Activate
    curriculum.activate(activated_by="admin-1")
    assert curriculum.status == BenchmarkStatus.ACTIVE

    # 5. Supersede
    curriculum.supersede()
    assert curriculum.status == BenchmarkStatus.SUPERSEDED


def test_benchmark_governance_rejection_and_revision_flow() -> None:
    curriculum = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-100",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
    )
    curriculum.mark_validated()
    curriculum.submit_for_review()
    assert curriculum.status == BenchmarkStatus.UNDER_REVIEW

    # Reject
    curriculum.reject(
        reviewer_id="reviewer-2",
        reason="Credit units insufficient in level 200.",
    )
    assert curriculum.status == BenchmarkStatus.REJECTED

    # Cannot activate rejected
    with pytest.raises(ValueError, match="only approved benchmarks can be activated"):
        curriculum.activate()

    # Revise back to candidate
    curriculum.revise_to_candidate()
    assert curriculum.status == BenchmarkStatus.CANDIDATE


def test_benchmark_audit_log_creation() -> None:
    log = BenchmarkAuditLog.create(
        curriculum_id="bmcurr-123",
        action=BenchmarkAuditAction.APPROVE,
        actor_id="user-456",
        actor_email="regulator@nuc.edu.ng",
        previous_status="under_review",
        new_status="approved",
        reason="Approved national standard",
        diff_fingerprint="a" * 64,
    )
    assert log.id.startswith("bmaudit-")
    assert log.curriculum_id == "bmcurr-123"
    assert log.action == BenchmarkAuditAction.APPROVE
    assert log.actor_email == "regulator@nuc.edu.ng"
    assert log.diff_fingerprint == "a" * 64
