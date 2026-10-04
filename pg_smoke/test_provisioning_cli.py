import asyncio
import os
import sys
from uuid import uuid4

import httpx
import pytest
from app.db.session import SessionLocal
from app.main import app
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "Owner-Passphrase-2026"


async def _cli(*args: str, password: str | None = PASSWORD) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.provision_tenant",
        *args,
        *(["--owner-password-stdin"] if password is not None else []),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "APP_ENVIRONMENT": "development"},
    )
    out, _ = await process.communicate(f"{password}\n".encode() if password is not None else None)
    return process.returncode, out.decode()


async def test_provisioned_owner_can_sign_in_and_act_as_owner():
    slug, email = f"futa-{uuid4().hex[:10]}", f"owner-{uuid4().hex[:10]}@futa.edu.ng"
    args = ("--name", "Federal University of Technology, Akure", "--slug", slug, "--owner-email", email)

    code, out = await _cli(*args)
    assert code == 0, out
    assert "tenant" in out and "created" in out and PASSWORD not in out
    code, again = await _cli(*args, password=None)
    assert code == 0 and "owner membership: unchanged" in again, again

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
        login = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}", "X-Tenant-Slug": slug}
        context = await client.get("/identity/tenant-context", headers=headers)
    assert context.status_code == 200 and context.json()["data"]["role"] == "owner"

    async with SessionLocal() as session:
        events = (
            (
                await session.execute(
                    text(
                        "select event_type || '.' || action from security_events se "
                        "join users u on u.id = se.user_id where u.email = :email order by se.created_at"
                    ),
                    {"email": email},
                )
            )
            .scalars()
            .all()
        )
        counts = (
            await session.execute(
                text(
                    "select (select count(*) from tenants where slug = :slug), "
                    "(select count(*) from memberships m join tenants t on t.id = m.tenant_id where t.slug = :slug)"
                ),
                {"slug": slug},
            )
        ).one()
    assert events == ["account.provisioned", "membership.owner_granted"]
    assert tuple(counts) == (1, 1)


async def test_concurrent_runs_never_duplicate():
    slug, email = f"futa-{uuid4().hex[:10]}", f"owner-{uuid4().hex[:10]}@futa.edu.ng"
    args = ("--name", "Concurrent University", "--slug", slug, "--owner-email", email)

    results = await asyncio.gather(*[_cli(*args) for _ in range(3)])

    assert any(code == 0 for code, _ in results), results
    assert all(code in (0, 1) and "Traceback" not in out for code, out in results), results
    async with SessionLocal() as session:
        counts = (
            await session.execute(
                text(
                    "select (select count(*) from tenants where slug = :slug), "
                    "(select count(*) from users where email = :email), "
                    "(select count(*) from memberships m join tenants t on t.id = m.tenant_id where t.slug = :slug)"
                ),
                {"slug": slug, "email": email},
            )
        ).one()
    assert tuple(counts) == (1, 1, 1)


async def test_refusals_exit_with_1_and_change_nothing():
    slug = f"futa-{uuid4().hex[:10]}"

    code, out = await _cli(
        "--name", "No Password", "--slug", slug, "--owner-email", f"x-{uuid4().hex[:8]}@futa.edu.ng", password=None
    )

    assert code == 1 and "password is required" in out
    async with SessionLocal() as session:
        assert (await session.execute(text("select count(*) from tenants where slug = :s"), {"s": slug})).scalar_one() == 0
