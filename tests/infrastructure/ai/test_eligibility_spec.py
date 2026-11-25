"""M4 as a specification: the gateway's side of retrieval eligibility and
citation authorisation (docs/m4-retrieval-eligibility-design.md, section 3).

Every test here pins behaviour M4-B must add and is a strict xfail: it fails
today for the reason in its marker, and when M4-B makes it pass the strict
marker turns that into a failure, so the marker is removed in the same commit.
Nothing in test_assistant_gateway.py is changed or weakened.

The seams these tests use are the ones the design names:

- ``eligible_allow_list(actor)`` -> the caller's list of ``(asset_id,
  run_number, attempt)``, computed by one backend query before the call;
- ``eligible_sources(actor, triples)`` -> the subset of those triples eligible
  for the caller *now*, asked again after the response;
- ``MAX_ALLOWED`` -> the shared limit on the list (design 3.5).
"""

import json
import time

import httpx
import pytest

from app.domain.ai.assistant import AIActor, AIAssistantError
from app.infrastructure.ai import assistant_gateway
from app.infrastructure.ai.assistant_gateway import HttpAIAssistantGateway
from app.infrastructure.security.service_signature import (
    HEADER_RESPONSE_SIGNATURE,
    HEADER_RESPONSE_TIMESTAMP,
    ServiceKeys,
    canonical_response,
    compute_signature,
    sha256_hex,
)

TENANT = "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c"
ACTOR = AIActor(
    tenant_id=TENANT,
    user_id="0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d",
    membership_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    role="student",
    permission="ai.use",
    correlation_id="corr-7",
)
KEYS = ServiceKeys(current="test-backend-to-ai-secret-for-eligibility-spec-01")
RESPONSE_KEYS = ServiceKeys(current="test-ai-to-backend-secret-for-eligibility-spec-02")
A1 = ("asset-1", 1, 1)
A2 = ("asset-2", 3, 2)
M4B = "M4-B phase 3 (design section 7)"


def strict(reason: str):
    return pytest.mark.xfail(strict=True, reason=f"{reason}: {M4B}")


class Nonces:
    def __init__(self) -> None:
        self.claimed: set[tuple[str, str, str]] = set()

    async def claim(self, receiver: str, sender: str, request_id: str) -> bool:
        key = (receiver, sender, request_id)
        fresh = key not in self.claimed
        self.claimed.add(key)
        return fresh


def _signed(request: httpx.Request, response: httpx.Response) -> httpx.Response:
    timestamp = str(int(time.time()))
    canonical = canonical_response(
        service="ai-service",
        request_id=request.headers["x-build-request-id"],
        nonce=json.loads(request.content)["response_nonce"],
        timestamp=timestamp,
        body_sha256=sha256_hex(response.content),
    )
    headers = {
        **response.headers,
        HEADER_RESPONSE_TIMESTAMP: timestamp,
        HEADER_RESPONSE_SIGNATURE: compute_signature(RESPONSE_KEYS.current, canonical),
    }
    return httpx.Response(response.status_code, content=response.content, headers=headers)


def src(triple: tuple[str, int, int]) -> dict:
    return {"asset_id": triple[0], "run_number": triple[1], "attempt": triple[2]}


def reply(sources: list, **data) -> httpx.Response:
    body = {"answer": "A", "context_used": [], "memory_used": "", **data}
    return httpx.Response(200, json={"success": True, "data": body, "message": "", "sources_used": sources})


async def everything_readable(actor, asset_ids):
    return set(asset_ids)


def gateway(handler, **kwargs) -> HttpAIAssistantGateway:
    async def signing(request: httpx.Request) -> httpx.Response:
        return _signed(request, await handler(request))

    kwargs.setdefault("readable_sources", everything_readable)
    return HttpAIAssistantGateway(
        base_url="http://ai-service.internal",
        client=httpx.AsyncClient(transport=httpx.MockTransport(signing)),
        keys=KEYS,
        response_keys=RESPONSE_KEYS,
        nonce_store=Nonces(),
        **kwargs,
    )


def with_policy(allow, eligible=None):
    """The M4 seams, passed only through keyword arguments the design names."""

    async def allow_list(actor):
        return list(allow)

    async def eligible_now(actor, triples):
        return set(triples) & set(allow) if eligible is None else eligible(set(triples))

    return {"eligible_allow_list": allow_list, "eligible_sources": eligible_now}


class Capture:
    def __init__(self, sources: list | None = None, **data) -> None:
        self.bodies: list[dict] = []
        self._sources = [src(A1)] if sources is None else sources
        self._data = data

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        return reply(self._sources, **self._data)


# --- Property 2, 3, 4, 5: the list the call carries ----------------------------------------


@strict("the request carries no allow-list today")
async def test_the_call_carries_the_eligible_triples_sorted():
    seen = Capture()
    await gateway(seen, **with_policy([A2, A1])).chat(ACTOR, "hi")
    assert seen.bodies[0]["allowed"] == [src(A1), src(A2)]


@strict("an empty list still reaches the AI service today")
async def test_an_empty_allow_list_makes_no_call_and_is_the_not_covered_reply():
    seen = Capture()
    result = await gateway(seen, **with_policy([])).chat(ACTOR, "hi")
    assert seen.bodies == []
    assert result.grounded is False


@strict("there is no allow-list to be unreadable")
async def test_an_allow_list_that_cannot_be_read_makes_no_call():
    seen = Capture()

    async def broken(actor):
        raise RuntimeError("database down")

    with pytest.raises(AIAssistantError) as raised:
        await gateway(seen, eligible_allow_list=broken, eligible_sources=lambda a, t: None).chat(ACTOR, "hi")
    assert raised.value.unavailable and seen.bodies == []


@strict("MAX_ALLOWED does not exist")
@pytest.mark.parametrize("size,calls", [(5000, 1), (5001, 0)])
async def test_the_shared_allow_list_limit_is_never_exceeded_or_truncated(size, calls):
    seen = Capture(sources=[])
    triples = [(f"asset-{i:05d}", 1, 1) for i in range(size)]
    g = gateway(seen, **with_policy(triples))
    assert assistant_gateway.MAX_ALLOWED == 5000
    if calls:
        await g.chat(ACTOR, "hi")
        assert len(seen.bodies[0]["allowed"]) == 5000
    else:
        with pytest.raises(AIAssistantError) as raised:
            await g.chat(ACTOR, "hi")
        assert raised.value.unavailable
    assert len(seen.bodies) == calls  # never a partial list


# --- Property 5 and 3: the post-generation check is on the exact version ---------------------


@strict("the check compares asset ids only; a superseded run passes")
async def test_a_source_from_a_superseded_run_withholds_the_answer_though_the_asset_is_readable():
    current = ("asset-1", 2, 1)  # the asset was reprocessed: run 2 is current

    async def handler(request):
        return reply([src(("asset-1", 1, 1))])  # the AI service answered from run 1

    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **with_policy([current])).chat(ACTOR, "hi")
    assert raised.value.error_code == "ANSWER_WITHHELD"


@strict("a source outside the request's own list is not detected")
async def test_a_source_the_request_did_not_allow_withholds_the_answer_even_if_eligible_now():
    allow = [A1]

    async def handler(request):
        return reply([src(A1), src(A2)])

    policy = with_policy(allow, eligible=lambda triples: triples)  # A2 is eligible *now*
    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **policy).chat(ACTOR, "hi")
    assert raised.value.error_code == "ANSWER_WITHHELD"


@strict("eligibility is not asked again after the response")
async def test_eligibility_is_evaluated_again_after_the_response_not_reused():
    states = iter([{A1}, set()])  # eligible when the call left, gone when it returned

    async def eligible_now(actor, triples):
        return set(triples) & next(states)

    async def allow_list(actor):
        return [A1]

    g = gateway(Capture(), eligible_allow_list=allow_list, eligible_sources=eligible_now)
    with pytest.raises(AIAssistantError) as raised:
        await g.chat(ACTOR, "hi")
    assert raised.value.error_code == "ANSWER_WITHHELD"


@strict("the check receives asset ids, not exact versions")
async def test_the_check_is_asked_about_exactly_the_triples_that_were_used():
    asked: list[set] = []

    async def eligible_now(actor, triples):
        asked.append(set(triples))
        return set(triples)

    async def allow_list(actor):
        return [A1, A2]

    handler = Capture(sources=[src(A1), src(A2)])
    await gateway(handler, eligible_allow_list=allow_list, eligible_sources=eligible_now).chat(ACTOR, "hi")
    assert asked == [{A1, A2}]


@strict("a check that cannot run is not the eligibility check")
async def test_an_eligibility_check_that_cannot_run_withholds_the_answer():
    async def failing(actor, triples):
        raise RuntimeError("database down")

    async def allow_list(actor):
        return [A1]

    with pytest.raises(AIAssistantError) as raised:
        await gateway(Capture(), eligible_allow_list=allow_list, eligible_sources=failing).chat(ACTOR, "hi")
    assert raised.value.error_code == "ANSWER_WITHHELD"


# --- Property 7: citations are validated against the evidence retrieved --------------------


def cite(number: int, triple=A1, **extra) -> dict:
    return {
        "number": number,
        "chunk_id": f"chunk-{number}",
        "document_id": triple[0],
        "run_number": triple[1],
        "attempt": triple[2],
        "page_start": 4,
        "page_end": 5,
        "excerpt": "Osmosis is the diffusion of water.",
        **extra,
    }


def grounded(text: str, citations: list[dict], sources=None, **extra) -> Capture:
    return Capture(sources=sources, answer=text, grounded=True, citations=citations, **extra)


@strict("citations are discarded today")
async def test_a_citation_naming_a_version_that_was_not_retrieved_withholds_the_answer():
    handler = grounded("Osmosis [1].", [cite(1, A2)], sources=[src(A1)])
    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **with_policy([A1, A2])).chat(ACTOR, "hi")
    assert raised.value.error_code == "ANSWER_WITHHELD"


@strict("citations are not read, so a dangling marker is not noticed")
async def test_a_marker_with_no_citation_is_a_broken_response():
    handler = grounded("Osmosis [1] and diffusion [2].", [cite(1)])
    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **with_policy([A1])).chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE"


@strict("citations are not read, so an uncited citation is not noticed")
async def test_a_citation_the_text_never_uses_is_a_broken_response():
    handler = grounded("Osmosis [1].", [cite(1), cite(2)])
    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **with_policy([A1])).chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE"


@strict("grounded is discarded today")
async def test_a_not_grounded_answer_with_citations_is_a_broken_response():
    handler = Capture(answer="Not covered.", grounded=False, citations=[cite(1)])
    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **with_policy([A1])).chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE"


@strict("a grounded answer with no citation is accepted today")
async def test_a_grounded_answer_with_no_citation_is_a_broken_response():
    handler = Capture(answer="Osmosis.", grounded=True, citations=[])
    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, **with_policy([A1])).chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE"


@strict("the answer has no citations, grounded flag or backend-owned metadata")
async def test_the_answer_carries_validated_citations_and_never_an_internal_id():
    handler = grounded("Osmosis [1].", [cite(1)])
    result = await gateway(handler, **with_policy([A1])).chat(ACTOR, "hi")
    assert result.grounded is True
    assert [(c.number, c.asset_id, c.page_start, c.page_end) for c in result.citations] == [(1, "asset-1", 4, 5)]
    assert all(not hasattr(c, "chunk_id") for c in result.citations)
