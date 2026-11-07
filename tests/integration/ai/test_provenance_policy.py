"""The provenance check asks the same read policy as the content routes
(M3-D PR 4b): an AI answer's sources are checked for the caller exactly as
their content reads would be."""

import pytest

from app.api.ai import readable_sources
from app.application.content.read_policy import may_read
from app.domain.ai.assistant import AIActor
from tests.integration.content.read_policy_world import build_world


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "who,role", [("owner", "student"), ("student", "student"), ("staff", "lecturer"), ("other_student", "student")]
)
async def test_the_provenance_check_is_the_read_policy_for_that_caller(who, role):
    world = await build_world()
    names = {asset: name for name, asset in world.assets.items()}
    readable = await readable_sources(actor(world, who, role), set(world.assets.values()))
    expected = sorted(name for name, doc in world.docs.items() if may_read(doc.facts, world.readers[who]))
    assert sorted(names[i] for i in readable) == expected


@pytest.mark.asyncio
async def test_a_student_answer_citing_unreviewed_staff_material_fails_the_check():
    world = await build_world()
    unclassified = world.assets["unclassified"]
    reviewed = world.assets["institutional, reviewed for the tenant"]
    readable = await readable_sources(actor(world, "student", "student"), {unclassified, reviewed})
    assert readable == {reviewed}
