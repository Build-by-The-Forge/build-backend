"""Migration 0033 on real PostgreSQL (M3-F): the conversation tables' rules.

The database itself keeps a conversation's rows in one tenant, with the
application bypassed: every composite reference is tested with another
tenant's row, every constraint with the value it must refuse, and the
turn-key shape with NULL, since a composite foreign key with a NULL part
checks nothing.
"""

import pytest

from pg_smoke.test_migration_0030 import _id, _refused, _run, _scalar, _world

pytestmark = pytest.mark.asyncio(loop_scope="session")

SHA = "ab" * 32
CONVERSATION = "INSERT INTO conversations (id, tenant_id, user_id) VALUES (:id, :t, :u)"
MESSAGE = (
    "INSERT INTO conversation_messages (id, tenant_id, conversation_id, seq, role, content, grounded, redacted)"
    " VALUES (:id, :t, :c, :seq, :role, :content, :grounded, :redacted)"
)
CITATION = (
    "INSERT INTO conversation_citations (id, tenant_id, message_id, number, source_id, asset_id, title,"
    " page_start, page_end, excerpt) VALUES (:id, :t, :m, :n, :s, :a, 'Notes', :ps, :pe, :x)"
)
SOURCE = (
    "INSERT INTO conversation_message_sources (tenant_id, message_id, asset_id, run_number, attempt)"
    " VALUES (:t, :m, :a, :run, :att)"
)
KEY = (
    "INSERT INTO conversation_turn_keys (id, tenant_id, conversation_id, idempotency_key, question_sha256, state,"
    " generation, lease_expires_at, student_message_id, assistant_message_id)"
    " VALUES (:id, :t, :c, :k, :sha, :state, :gen, now() + interval '1 minute', :sm, :am)"
)


async def _conversation(w: dict[str, str]) -> str:
    conversation = _id()
    await _run(CONVERSATION, id=conversation, t=w["tenant"], u=w["user"])
    return conversation


async def _message(
    w: dict[str, str],
    conversation: str,
    seq: int,
    role: str = "student",
    *,
    content: str = "What is osmosis?",
    grounded: bool | None = None,
    redacted: bool = False,
    tenant: str | None = None,
) -> str:
    message = _id()
    await _run(
        MESSAGE,
        id=message,
        t=tenant or w["tenant"],
        c=conversation,
        seq=seq,
        role=role,
        content=content,
        grounded=grounded,
        redacted=redacted,
    )
    return message


async def _answer(w: dict[str, str], conversation: str, seq: int = 2) -> str:
    return await _message(w, conversation, seq, "assistant", content="Water moves [1].", grounded=True)


def _citation_params(w, message, **over) -> dict:
    params = dict(id=_id(), t=w["tenant"], m=message, n=1, s=w["source"], a=w["asset"], ps=3, pe=4, x="Osmosis is...")
    return params | over


def _key_params(w, conversation, **over) -> dict:
    params = dict(id=_id(), t=w["tenant"], c=conversation, k=_id(), sha=SHA, state="pending", gen=1, sm=None, am=None)
    return params | over


# --- conversations ----------------------------------------------------------------------


async def test_a_conversation_is_valid_with_a_null_title_and_expiry_and_refuses_bad_ones():
    w = await _world()
    conversation = await _conversation(w)
    assert (
        await _scalar("SELECT status || ':' || coalesce(title, '-') FROM conversations WHERE id = :c", c=conversation)
        == "active:-"
    )

    for column, value in (("title", "   "), ("status", "archived")):
        await _refused(
            f"INSERT INTO conversations (id, tenant_id, user_id, {column}) VALUES (:id, :t, :u, :v)",
            id=_id(),
            t=w["tenant"],
            u=w["user"],
            v=value,
        )
    await _refused(  # expires before it was created
        "INSERT INTO conversations (id, tenant_id, user_id, created_at, expires_at)"
        " VALUES (:id, :t, :u, now(), now() - interval '1 day')",
        id=_id(),
        t=w["tenant"],
        u=w["user"],
    )
    await _refused(  # the title is cut at 80 characters before it is stored
        "INSERT INTO conversations (id, tenant_id, user_id, title) VALUES (:id, :t, :u, :v)",
        id=_id(),
        t=w["tenant"],
        u=w["user"],
        v="x" * 81,
    )


async def test_a_conversation_names_a_real_tenant_and_user():
    w = await _world()
    await _refused(CONVERSATION, id=_id(), t=_id(), u=w["user"])
    await _refused(CONVERSATION, id=_id(), t=w["tenant"], u=_id())


# --- messages ---------------------------------------------------------------------------


async def test_a_message_belongs_to_a_conversation_of_its_own_tenant():
    w, other = await _world(), await _world()
    conversation = await _conversation(w)
    await _message(w, conversation, 1)
    await _refused(
        MESSAGE, id=_id(), t=other["tenant"], c=conversation, seq=2, role="student", content="x", grounded=None, redacted=False
    )
    await _refused(MESSAGE, id=_id(), t=w["tenant"], c=_id(), seq=1, role="student", content="x", grounded=None, redacted=False)


async def test_messages_are_ordered_by_a_unique_positive_sequence():
    w = await _world()
    conversation = await _conversation(w)
    await _message(w, conversation, 1)
    await _refused(
        MESSAGE, id=_id(), t=w["tenant"], c=conversation, seq=1, role="student", content="x", grounded=None, redacted=False
    )
    await _refused(
        MESSAGE, id=_id(), t=w["tenant"], c=conversation, seq=0, role="student", content="x", grounded=None, redacted=False
    )
    # The same number is free in another conversation.
    await _message(w, await _conversation(w), 1)


@pytest.mark.parametrize(
    "role,content,grounded,redacted",
    [
        ("teacher", "x", None, False),  # an unknown role
        ("student", "", None, False),  # no text
        ("student", "x", True, False),  # a student's message is not grounded or not
        ("student", "x", False, False),
        ("student", "x", None, True),  # and is never redacted
        ("assistant", "x", None, False),  # an answer always says whether it was grounded
    ],
)
async def test_a_message_has_the_shape_of_its_role(role, content, grounded, redacted):
    w = await _world()
    conversation = await _conversation(w)
    await _refused(
        MESSAGE, id=_id(), t=w["tenant"], c=conversation, seq=1, role=role, content=content, grounded=grounded, redacted=redacted
    )


async def test_an_answer_can_be_grounded_ungrounded_or_redacted():
    w = await _world()
    conversation = await _conversation(w)
    await _message(w, conversation, 1)
    await _message(w, conversation, 2, "assistant", content="Water moves [1].", grounded=True)
    await _message(w, conversation, 3, "assistant", content="Not covered.", grounded=False)
    await _message(w, conversation, 4, "assistant", content="Notice.", grounded=True, redacted=True)


# --- citations --------------------------------------------------------------------------


async def test_a_citation_is_valid_and_its_pages_may_be_unknown():
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _run(CITATION, **_citation_params(w, message))
    await _run(CITATION, **_citation_params(w, message, n=2, ps=None, pe=None))


async def test_a_citation_names_a_message_and_a_document_of_its_own_tenant():
    w, other = await _world(), await _world()
    message = await _answer(w, await _conversation(w))
    await _refused(CITATION, **_citation_params(w, message, t=other["tenant"]))  # the message is another tenant's
    await _refused(CITATION, **_citation_params(w, message, a=other["asset"]))  # the document is another tenant's
    await _refused(CITATION, **_citation_params(w, message, a=_id()))
    await _refused(CITATION, **_citation_params(w, message, s=_id()))  # no such source
    await _refused(CITATION, **_citation_params(w, _id()))


@pytest.mark.parametrize(
    "over",
    [
        {"x": ""},  # an excerpt is the cited passage, never empty
        {"x": "x" * 501},  # and at most 500 characters
        {"n": 0},
        {"ps": -1},
        {"ps": 5, "pe": 4},  # pages never run backwards
    ],
)
async def test_a_citation_refuses_a_bad_excerpt_number_or_pages(over):
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _refused(CITATION, **_citation_params(w, message, **over))


async def test_the_excerpt_may_hold_exactly_500_characters_and_a_number_once_per_answer():
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _run(CITATION, **_citation_params(w, message, x="x" * 500))
    await _refused(CITATION, **_citation_params(w, message))  # number 1 again


async def test_a_cited_document_cannot_be_deleted_from_under_its_citation():
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _run(CITATION, **_citation_params(w, message))
    await _refused("DELETE FROM content_assets WHERE id = :a", a=w["asset"])


# --- every source of an answer ----------------------------------------------------------


async def test_every_source_an_answer_used_is_kept_once_per_version():
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _run(SOURCE, t=w["tenant"], m=message, a=w["asset"], run=1, att=1)
    await _run(SOURCE, t=w["tenant"], m=message, a=w["asset"], run=2, att=1)  # a reprocessed version
    await _refused(SOURCE, t=w["tenant"], m=message, a=w["asset"], run=1, att=1)
    assert await _scalar("SELECT count(*) FROM conversation_message_sources WHERE message_id = :m", m=message) == 2


async def test_a_source_row_names_a_message_and_a_document_of_its_own_tenant():
    w, other = await _world(), await _world()
    message = await _answer(w, await _conversation(w))
    await _refused(SOURCE, t=other["tenant"], m=message, a=w["asset"], run=1, att=1)
    await _refused(SOURCE, t=w["tenant"], m=message, a=other["asset"], run=1, att=1)
    await _refused(SOURCE, t=w["tenant"], m=message, a=_id(), run=1, att=1)


@pytest.mark.parametrize("run,att", [(0, 1), (1, 0), (-1, 1)])
async def test_a_source_version_starts_at_one(run, att):
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _refused(SOURCE, t=w["tenant"], m=message, a=w["asset"], run=run, att=att)


async def test_a_used_document_cannot_be_deleted_from_under_its_source_row():
    w = await _world()
    message = await _answer(w, await _conversation(w))
    await _run(SOURCE, t=w["tenant"], m=message, a=w["asset"], run=1, att=1)
    await _refused("DELETE FROM content_assets WHERE id = :a", a=w["asset"])


# --- turn keys --------------------------------------------------------------------------


async def test_a_pending_key_names_no_message_and_a_stored_key_names_both_of_its_conversation():
    w = await _world()
    conversation = await _conversation(w)
    await _run(KEY, **_key_params(w, conversation))
    student = await _message(w, conversation, 1)
    answer = await _answer(w, conversation)
    await _run(KEY, **_key_params(w, conversation, state="stored", sm=student, am=answer))


@pytest.mark.parametrize(
    "state,names",
    [
        ("pending", "student"),  # a pending key names no message, with NULL on the other side
        ("pending", "answer"),
        ("pending", "both"),
        ("stored", "none"),  # a stored key names both
        ("stored", "student"),
        ("stored", "answer"),
    ],
)
async def test_the_state_decides_which_messages_a_key_names(state, names):
    w = await _world()
    conversation = await _conversation(w)
    student, answer = await _message(w, conversation, 1), await _answer(w, conversation)
    chosen = {
        "none": (None, None),
        "student": (student, None),
        "answer": (None, answer),
        "both": (student, answer),
    }[names]
    await _refused(KEY, **_key_params(w, conversation, state=state, sm=chosen[0], am=chosen[1]))


async def test_a_stored_key_cannot_name_another_conversations_messages_or_another_tenants():
    w, other = await _world(), await _world()
    conversation, elsewhere = await _conversation(w), await _conversation(w)
    student, answer = await _message(w, elsewhere, 1), await _answer(w, elsewhere)
    await _refused(KEY, **_key_params(w, conversation, state="stored", sm=student, am=answer))
    await _refused(KEY, **_key_params(w, conversation, t=other["tenant"]))  # the conversation is another tenant's


async def test_a_key_is_unique_per_conversation_and_checks_its_hash_and_generation():
    w = await _world()
    conversation = await _conversation(w)
    await _run(KEY, **_key_params(w, conversation, k="key-1"))
    await _refused(KEY, **_key_params(w, conversation, k="key-1"))
    await _run(KEY, **_key_params(w, await _conversation(w), k="key-1"))  # the same key elsewhere is a different send
    for bad in ({"sha": "AB" * 32}, {"sha": "ab" * 31}, {"gen": 0}, {"state": "done"}, {"k": ""}):
        await _refused(KEY, **_key_params(w, conversation, **bad))


# --- removal ----------------------------------------------------------------------------


async def test_deleting_a_conversation_removes_everything_below_it_and_nothing_else():
    w = await _world()
    conversation = await _conversation(w)
    student, answer = await _message(w, conversation, 1), await _answer(w, conversation)
    await _run(CITATION, **_citation_params(w, answer))
    await _run(SOURCE, t=w["tenant"], m=answer, a=w["asset"], run=1, att=1)
    await _run(KEY, **_key_params(w, conversation, state="stored", sm=student, am=answer))

    await _run("DELETE FROM conversations WHERE id = :c", c=conversation)

    for table, column in (
        ("conversation_messages", "conversation_id"),
        ("conversation_turn_keys", "conversation_id"),
    ):
        assert await _scalar(f"SELECT count(*) FROM {table} WHERE {column} = :c", c=conversation) == 0
    for table in ("conversation_citations", "conversation_message_sources"):
        assert await _scalar(f"SELECT count(*) FROM {table} WHERE message_id = :m", m=answer) == 0
    # The document and its source stay: a conversation never owns them.
    assert await _scalar("SELECT count(*) FROM content_assets WHERE id = :a", a=w["asset"]) == 1
