"""C22 completed (P3-5): an uploaded document becomes retrievable evidence.

A lecturer uploads a document with its own text, ingestion takes it to
`ready`, and a student's natural question (no marker, no keywords copied
from a heading) retrieves the expected passage: a top-5 result that
contains the expected span, comes from that uploaded asset and cites its
page. Some chunk of the document is not enough; the evidence must be the
passage that answers the question. Another tenant asking the same
question gets nothing from it.
"""

import uuid

from boundary.conftest import (
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


def retrieve_as(ai, tenant, question: str) -> list[dict]:
    student = tenant.members["student"]
    raw = jbytes({"query": question})
    context = user_context(tenant.tenant_id, student.user_id, ["ai.use"], membership_id=student.membership_id, role="student")
    response = ai.post(RETRIEVE, content=raw, headers=to_ai("POST", RETRIEVE, raw, context))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_c22_a_question_retrieves_the_expected_passage_of_the_uploaded_document(ai, backend, tenant_a, tenant_b):
    asset = create_asset(backend, tenant_a, pdf_document(uuid.uuid4().hex, BODY))
    job = create_job_for(backend, tenant_a, asset)
    dispatched = backend.post(f"/content/jobs/{job['id']}/dispatch", headers=tenant_a.h("lecturer"))
    assert dispatched.status_code == 200, dispatched.text
    final = wait_for_status(backend, tenant_a, job["id"], {"ready", "failed"}, timeout=READY_TIMEOUT)
    assert final["status"] == "ready", final

    results = retrieve_as(ai, tenant_a, QUESTION)[:5]

    source = f"asset:{asset['id']}"
    evidence = [r for r in results if r["provenance"]["source_uri"] == source and EXPECTED_SPAN in r["text"]]
    assert evidence, [(r["provenance"], r["text"][:80]) for r in results]
    assert evidence[0]["provenance"]["page_number"] == 1

    others = retrieve_as(ai, tenant_b, QUESTION)
    assert not [r for r in others if r["provenance"]["source_uri"] == source or EXPECTED_SPAN in r["text"]]
