"""The shared list parameters: their limits, defaults and refusals."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.pagination import Page, PageRequest
from app.main import app as real_app


def _client() -> TestClient:
    subject = FastAPI()
    for kind, handler in real_app.exception_handlers.items():
        if kind is not Exception:
            subject.add_exception_handler(kind, handler)

    @subject.get("/items")
    async def items(page: Page):
        return {"limit": page.limit, "offset": page.offset}

    return TestClient(subject)


def test_the_defaults_are_the_contracts():
    assert _client().get("/items").json() == {"limit": 50, "offset": 0}


@pytest.mark.parametrize("query,limit,offset", [("limit=1", 1, 0), ("limit=100", 100, 0), ("offset=7", 50, 7)])
def test_values_at_the_limits_are_accepted(query, limit, offset):
    assert _client().get(f"/items?{query}").json() == {"limit": limit, "offset": offset}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "offset=-1", "limit=x", "offset=x", "limit=1.5"])
def test_values_outside_the_limits_are_a_validation_failure(query):
    response = _client().get(f"/items?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_the_meta_is_the_contracts_shape():
    assert PageRequest(limit=2, offset=4).meta(9) == {"total": 9, "limit": 2, "offset": 4}


@pytest.mark.parametrize(
    "limit,offset,expected",
    [(2, 0, [1, 2]), (2, 2, [3, 4]), (2, 4, [5]), (2, 5, []), (2, 99, []), (100, 0, [1, 2, 3, 4, 5])],
)
def test_slicing_a_list_already_in_memory(limit, offset, expected):
    assert PageRequest(limit=limit, offset=offset).slice([1, 2, 3, 4, 5]) == expected
