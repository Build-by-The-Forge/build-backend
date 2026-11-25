"""M4 as a specification: which document versions may be used in an answer
(docs/m4-retrieval-eligibility-design.md, sections 3.1 and 3.9).

Strict xfails: each fails today for the reason in its marker, and when M4-B
makes it pass the strict marker turns that into a failure, so the marker is
removed in the same commit. No existing test is changed.

``app.application.content.eligibility.may_use(facts, reader, run_number,
attempt)`` is the pure rule E1 to E7; M4-B phase 1 adds the SQL form and a
test that the two agree on every row below, as test_read_policy.py does for
``may_read``.
"""

from dataclasses import replace

import pytest
from sqlalchemy import select, update

from app.api.ai import readable_sources
from app.application.content.read_policy import Reader
from app.db.session import SessionLocal
from app.domain.ai.assistant import AIActor
from app.infrastructure.db.models.content import ContentAssetModel, ContentSourceModel

from tests.integration.content.read_policy_world import build_world

M4B = "M4-B phase 1 (design section 7)"
T = "tenant-1"
STUDENT = Reader(T, "student", manages_shared=False)
OWNER = Reader(T, "owner", manages_shared=False)


def base() -> dict:
    """Institutional, reviewed for the tenant with AI use permitted, scanned
    clean, its latest job ready at run 2, attempt 1, in an active source."""
    return dict(
        tenant_id=T,
        status="active",
        source_status="active",
        ownership_class="institutional",
        owner_user_id=None,
        published=False,
        reviewed_for_students=True,
        ai_use_permitted=True,
        scan_verdict="accepted",
        latest_job_status="ready",
        latest_run_number=2,
        latest_attempt=1,
    )


# name, changes to base, reader, entry run, entry attempt, eligible?
CASES = [
    ("the current ready version", {}, STUDENT, 2, 1, True),
    ("an older run of a reprocessed document", {}, STUDENT, 1, 1, False),
    ("an older attempt of the current run", {"latest_attempt": 2}, STUDENT, 2, 1, False),
    ("the current attempt after a retry", {"latest_attempt": 2}, STUDENT, 2, 2, True),
    ("a reprocess queued", {"latest_job_status": "queued"}, STUDENT, 2, 1, False),
    ("a reprocess processing", {"latest_job_status": "processing"}, STUDENT, 2, 1, False),
    ("the latest job failed, chunks left behind", {"latest_job_status": "failed"}, STUDENT, 2, 1, False),
    ("no job at all", {"latest_job_status": None}, STUDENT, 2, 1, False),
    ("quarantined by the scan", {"scan_verdict": "quarantined"}, STUDENT, 2, 1, False),
    ("rejected by the scan", {"scan_verdict": "rejected"}, STUDENT, 2, 1, False),
    ("no scan verdict recorded", {"scan_verdict": None}, STUDENT, 2, 1, False),
    ("asset revoked", {"status": "revoked"}, STUDENT, 2, 1, False),
    ("asset deleted", {"status": "deleted"}, STUDENT, 2, 1, False),
    ("its source revoked", {"source_status": "revoked"}, STUDENT, 2, 1, False),
    ("its source status unknown", {"source_status": None}, STUDENT, 2, 1, False),
    ("another tenant's document", {"tenant_id": "tenant-2"}, STUDENT, 2, 1, False),
    ("not reviewed for students", {"reviewed_for_students": False}, STUDENT, 2, 1, False),
    ("reviewed, but AI use not permitted", {"ai_use_permitted": False}, STUDENT, 2, 1, False),
    ("unclassified", {"ownership_class": "unclassified", "reviewed_for_students": False}, STUDENT, 2, 1, False),
    ("an unknown ownership class", {"ownership_class": "mystery"}, STUDENT, 2, 1, False),
    ("the owner's own personal document", {"ownership_class": "personal", "owner_user_id": "owner"}, OWNER, 2, 1, True),
    (
        "the owner's own personal document, quarantined",
        {"ownership_class": "personal", "owner_user_id": "owner", "scan_verdict": "quarantined"},
        OWNER,
        2,
        1,
        False,
    ),
    (
        "another student's unpublished personal document",
        {"ownership_class": "personal", "owner_user_id": "owner"},
        STUDENT,
        2,
        1,
        False,
    ),
    (
        "another student's PUBLISHED personal document: readable, never usable",
        {"ownership_class": "personal", "owner_user_id": "owner", "published": True},
        STUDENT,
        2,
        1,
        False,
    ),
]


@pytest.mark.xfail(strict=True, reason=f"the rule does not exist yet: {M4B}")
@pytest.mark.parametrize("name,changes,reader,run,attempt,expected", CASES, ids=[c[0] for c in CASES])
def test_the_eligibility_rule_over_every_state_combination(name, changes, reader, run, attempt, expected):
    from app.application.content.eligibility import EligibilityFacts, may_use

    facts = EligibilityFacts(**{**base(), **changes})
    assert may_use(facts, reader, run, attempt) is expected


@pytest.mark.xfail(strict=True, reason=f"the rule does not exist yet: {M4B}")
def test_a_fact_the_rule_does_not_know_is_not_eligible():
    from app.application.content.eligibility import EligibilityFacts, may_use

    assert may_use(replace(EligibilityFacts(**base()), latest_run_number=None), STUDENT, 2, 1) is False


def actor(world, who: str, role: str) -> AIActor:
    reader = world.readers[who]
    return AIActor(
        tenant_id=reader.tenant_id,
        user_id=reader.user_id,
        membership_id="m",
        role=role,
        permission="ai.use",
        correlation_id="c",
    )


@pytest.mark.xfail(
    strict=True,
    reason="D1: revoking a source leaves its documents readable, in every provenance check and in retrieval (design 2.1)",
)
async def test_a_document_whose_source_was_revoked_is_not_readable_for_a_provenance_check():
    world = await build_world()
    asset = world.assets["institutional, reviewed for the tenant"]
    async with SessionLocal() as session:
        source_id = (
            await session.execute(select(ContentAssetModel.source_id).where(ContentAssetModel.id == asset))
        ).scalar_one()
        await session.execute(update(ContentSourceModel).where(ContentSourceModel.id == source_id).values(status="revoked"))
        await session.commit()

    readable = await readable_sources(actor(world, "student", "student"), {asset})

    assert readable == set()
