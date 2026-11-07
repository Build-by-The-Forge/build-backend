"""Record a tenant authority's written authorization for operator
classification (M3-D PR 5), or revoke one.

    python -m scripts.record_content_authority --tenant futa --recorded-by ops@example.com \\
        --authority-name "Dr A. Example" --authority-role Registrar \\
        --granted-at 2026-11-05 --covers "Existing lecture notes in the staff sources" \\
        --document-reference REG/2026/014 [--expires-at 2026-12-31]

    python -m scripts.record_content_authority --tenant futa --recorded-by ops@example.com --revoke <id>

The record holds who gave the authorization, their role, when, what it
covers and a reference to the document; classify_content checks it on every
run. Prints the authorization's id. Exit codes: 0 done, 1 refused, 2 usage.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.infrastructure.db.models.content import ContentAuthorityAuthorizationModel
from app.infrastructure.db.models.tenant_core import TenantModel
from app.infrastructure.identity.models import UserModel


class Refused(Exception):
    pass


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="record_content_authority", description=__doc__.split("\n\n")[0])
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--recorded-by", required=True, help="the email of the account recording it")
    parser.add_argument("--revoke", help="revoke this authorization instead of recording one")
    parser.add_argument("--authority-name")
    parser.add_argument("--authority-role")
    parser.add_argument("--granted-at", type=_date)
    parser.add_argument("--covers")
    parser.add_argument("--document-reference")
    parser.add_argument("--expires-at", type=_date)
    return parser


async def run(args: argparse.Namespace) -> str:
    async with SessionLocal() as session:
        async with session.begin():
            tenant_id = await session.scalar(select(TenantModel.id).where(TenantModel.slug == args.tenant))
            user_id = await session.scalar(select(UserModel.id).where(UserModel.email == args.recorded_by.strip().lower()))
            if tenant_id is None or user_id is None:
                raise Refused("unknown tenant or account")
            if args.revoke:
                result = await session.execute(
                    update(ContentAuthorityAuthorizationModel)
                    .where(
                        ContentAuthorityAuthorizationModel.id == args.revoke,
                        ContentAuthorityAuthorizationModel.tenant_id == tenant_id,
                        ContentAuthorityAuthorizationModel.revoked_at.is_(None),
                    )
                    .values(revoked_at=datetime.now(timezone.utc), revoked_by=user_id)
                )
                if result.rowcount != 1:
                    raise Refused("no current authorization with that id in this tenant")
                return args.revoke
            required = ("authority_name", "authority_role", "granted_at", "covers", "document_reference")
            missing = [name for name in required if not getattr(args, name)]
            if missing:
                raise Refused("missing " + ", ".join("--" + name.replace("_", "-") for name in missing))
            authorization_id = str(uuid4())
            session.add(
                ContentAuthorityAuthorizationModel(
                    id=authorization_id,
                    tenant_id=tenant_id,
                    authority_name=args.authority_name,
                    authority_role=args.authority_role,
                    granted_at=args.granted_at,
                    covers=args.covers,
                    document_reference=args.document_reference,
                    expires_at=args.expires_at,
                    recorded_by=user_id,
                )
            )
            return authorization_id


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if settings.app_environment == "testing":
        print("refusing to run with APP_ENVIRONMENT=testing (in-memory database)")
        return 2
    try:
        authorization_id = asyncio.run(run(args))
    except Refused as exc:
        print(f"refused: {exc}")
        return 1
    print(("revoked " if args.revoke else "recorded ") + authorization_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
