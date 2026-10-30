"""C22 completed (P3-5): an uploaded document becomes retrievable evidence.

A lecturer uploads a document with its own text, ingestion takes it to
`ready`, and a student's natural question (no marker, no keywords copied
from a heading) retrieves the expected passage: a top-5 result that
contains the expected span, comes from that uploaded asset and cites its
page. Some chunk of the document is not enough; the evidence must be the
passage that answers the question. Another tenant asking the same
question gets nothing from it.
"""

import asyncio
import uuid

import asyncpg

from boundary.conftest import (
    AI_APP_DSN,
    create_asset,
    create_job_for,
    jbytes,
    pdf_document,
    to_ai,
    user_context,
    wait_for_status,
)

RETRIEVE = "/v1/ai/retrieve"
READY_TIMEOUT = 180
BODY = [
    "The charge of the electron was first measured by Robert Millikan.",
    "In his oil drop experiment, tiny charged drops of oil were held",
    "still between two plates by balancing gravity with an electric force.",
    "Every drop carried a whole-number multiple of one smallest charge.",
]
QUESTION = "How was the charge of the electron first measured?"
EXPECTED_SPAN = "first measured by Robert Millikan"


def retrieve_as(ai, tenant, role: str, question: str) -> list[dict]:
    member = tenant.members[role]
    raw = jbytes({"query": question})
    context = user_context(tenant.tenant_id, member.user_id, ["ai.use"], membership_id=member.membership_id, role=role)
    response = ai.post(RETRIEVE, content=raw, headers=to_ai("POST", RETRIEVE, raw, context))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_c22_automatic_worker_ingestion_is_retrievable_only_by_the_right_tenant(ai, backend, tenant_a, tenant_b):
    asset = create_asset(backend, tenant_a, pdf_document(uuid.uuid4().hex, BODY))
    job = create_job_for(backend, tenant_a, asset)
    final = wait_for_status(backend, tenant_a, job["id"], {"ready", "failed"}, timeout=READY_TIMEOUT)
    assert final["status"] == "ready", final

    # Ready only after the deciding attempt's durable index commit: the
    # asset's chunks all belong to the job's own run and attempt, and the
    # fence names that attempt.
    async def index_state():
        connection = await asyncpg.connect(AI_APP_DSN)
        try:
            chunks = await connection.fetch(
                "SELECT run_number, attempt, count(*) AS n FROM document_chunks"
                " WHERE tenant_id = $1 AND asset_id = $2 GROUP BY run_number, attempt",
                tenant_a.tenant_id,
                asset["id"],
            )
            fenced = await connection.fetchrow(
                "SELECT run_number, attempt FROM ingestion_fences WHERE tenant_id = $1 AND asset_id = $2",
                tenant_a.tenant_id,
                asset["id"],
            )
        finally:
            await connection.close()
        return {(r["run_number"], r["attempt"]): r["n"] for r in chunks}, fenced

    chunks, fenced = asyncio.run(index_state())
    attempt = (final["run_number"], final["attempt_count"])
    assert set(chunks) == {attempt} and chunks[attempt] == final["metrics"]["indexed_chunks"], (chunks, final)
    assert fenced is not None and (fenced["run_number"], fenced["attempt"]) == attempt, (fenced, final)

    results = retrieve_as(ai, tenant_a, "student", QUESTION)[:5]

    source = f"asset:{asset['id']}"
    evidence = [r for r in results if r["provenance"]["source_uri"] == source and EXPECTED_SPAN in r["text"]]
    assert evidence, [(r["provenance"], r["text"][:80]) for r in results]
    assert evidence[0]["provenance"]["page_number"] == 1

    others = retrieve_as(ai, tenant_b, "lecturer", QUESTION)
    assert not [r for r in others if r["provenance"]["source_uri"] == source or EXPECTED_SPAN in r["text"]]
