"""Provision a tenant and its first owner (idempotent).

    python -m scripts.provision_tenant --name "Federal University of Technology, Akure" \\
        --slug futa --owner-email registrar@futa.edu.ng

Runs against the database the backend is configured for (POSTGRES_URL).
A password is needed only when the owner account does not exist yet. It is
never taken as an argument, so it cannot end up in shell history or process
listings: it is prompted for, or read from stdin with --owner-password-stdin.
Exit codes: 0 done (including "already provisioned"), 1 refused, 2 usage.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from app.application.identity.ports.security_events import SecurityEvent
from app.application.tenant.provisioning import (
    ProvisioningError,
    ProvisioningResult,
    provision_tenant,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.infrastructure.identity.security_event_recorder import (
    SQLAlchemySecurityEventRecorder,
)
from app.infrastructure.identity.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.tenant.async_repositories import (
    AsyncSqlAlchemyMembershipRepository,
    AsyncSqlAlchemyTenantRepository,
)
from sqlalchemy.exc import IntegrityError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="provision_tenant", description=__doc__.split("\n\n")[0])
    parser.add_argument("--name", required=True, help="tenant display name")
    parser.add_argument("--slug", required=True, help="tenant slug, e.g. futa")
    parser.add_argument("--owner-email", required=True)
    parser.add_argument(
        "--owner-password-stdin",
        action="store_true",
        help="read the new owner's password from the first line of stdin",
    )
    return parser


def _password(args: argparse.Namespace) -> str | None:
    if args.owner_password_stdin:
        return sys.stdin.readline().rstrip("\r\n") or None
    if sys.stdin.isatty():
        first = getpass.getpass("Owner password (only used if the account is new): ")
        if first and getpass.getpass("Repeat password: ") != first:
            raise ProvisioningError("passwords do not match")
        return first or None
    return None


async def _record(result: ProvisioningResult, slug: str) -> None:
    recorder = SQLAlchemySecurityEventRecorder(SessionLocal)
    meta = {"tenant_id": result.tenant_id, "tenant_slug": slug, "via": "provision_tenant"}
    if result.owner_created:
        await recorder.record(SecurityEvent.ACCOUNT_PROVISIONED, user_id=result.owner_user_id, metadata=meta)
    if result.owner_granted:
        await recorder.record(
            SecurityEvent.TENANT_OWNER_GRANTED,
            user_id=result.owner_user_id,
            metadata={**meta, "membership": result.membership.value},
        )


async def run(args: argparse.Namespace, password: str | None) -> ProvisioningResult:
    async with SessionLocal() as session:
        async with session.begin():
            result = await provision_tenant(
                tenants=AsyncSqlAlchemyTenantRepository(session),
                users=SQLAlchemyUserRepository(session),
                memberships=AsyncSqlAlchemyMembershipRepository(session),
                password_hasher=Argon2PasswordHasher(),
                name=args.name,
                slug=args.slug,
                owner_email=args.owner_email,
                owner_password=password,
            )
    await _record(result, args.slug)
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if settings.app_environment == "testing":
        print("refusing to run with APP_ENVIRONMENT=testing (in-memory database)")
        return 2
    try:
        result = asyncio.run(run(args, _password(args)))
    except ProvisioningError as exc:
        print(f"refused: {exc}")
        return 1
    except IntegrityError:
        # Unique constraints on tenant slug, user email and membership make a
        # concurrent run fail here instead of creating duplicates.
        print("refused: another run changed the same records at the same time; run again")
        return 1
    print(f"tenant {args.slug}: {'created' if result.tenant_created else 'exists'} ({result.tenant_id})")
    print(f"owner {args.owner_email}: {'created' if result.owner_created else 'exists'} ({result.owner_user_id})")
    print(f"owner membership: {result.membership.value}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
