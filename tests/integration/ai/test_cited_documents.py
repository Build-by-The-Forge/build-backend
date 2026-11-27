"""The backend's own record of a cited document: its source and its title, read
only within the caller's tenant (M3-F, R1)."""

from uuid import uuid4

from app.infrastructure.content.cited_documents import cited_documents
from tests.integration.test_mobile_contract_drift import seeded_content


async def test_a_tenants_documents_come_back_with_their_source_and_display_name():
    tenant = str(uuid4())
    source_id, asset_id = await seeded_content(tenant)

    assert await cited_documents(tenant, {asset_id}) == {asset_id: (source_id, "notes.pdf")}


async def test_another_tenants_document_and_an_unknown_id_are_absent():
    tenant, other = str(uuid4()), str(uuid4())
    _, asset_id = await seeded_content(tenant)

    assert await cited_documents(other, {asset_id, "no-such-asset"}) == {}
    assert await cited_documents(tenant, {"no-such-asset"}) == {}


async def test_no_ids_is_an_empty_answer_without_a_query():
    assert await cited_documents(str(uuid4()), set()) == {}
