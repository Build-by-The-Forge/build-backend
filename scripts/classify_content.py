"""Classify existing documents as institutional, by a tenant's written
authority, while staff workflows are paused (M3-D PR 5).

    python -m scripts.classify_content --tenant futa --operator-email ops@example.com \\
        --authorization <id> --decisions decisions.json [--apply] [--report report.json]

A dry run is the default: it checks the authority and the operator, judges
every decision, prints what would change, writes the report and changes
nothing. ``--apply`` records each decision in its own transaction. The
decisions file is a JSON list, one object per document:

    {"asset_id": "...", "evidence_reference": "REG/2026/014 item 3",
     "rights_basis": "lecturer_provided", "audience": "tenant",
     "redistribution": "tenant_only", "ai_use": "permitted"}

Exit codes: 0 every decision recorded (or would be), 1 some refused or the
run refused, 2 usage. Classification only queues a scope assignment: a
document becomes retrievable when the AI service acknowledges it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.application.content.classification import ClassificationRefused, ClassificationService, Decision, RunReport
from app.core.config import settings
from app.db.session import SessionLocal
from app.infrastructure.content.classification_store import classification_store
from app.infrastructure.db.models.tenant_core import TenantModel
from app.infrastructure.identity.models import UserModel

FIELDS = ("asset_id", "evidence_reference", "rights_basis", "audience", "redistribution", "ai_use")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="classify_content", description=__doc__.split("\n\n")[0])
    parser.add_argument("--tenant", required=True, help="the tenant's slug: one tenant per run, never all")
    parser.add_argument("--operator-email", required=True, help="the operator, a content manager in the tenant")
    parser.add_argument("--authorization", required=True, help="the id of the tenant authority's written authorization")
    parser.add_argument("--decisions", required=True, type=Path, help="JSON list of per-document decisions")
    parser.add_argument("--apply", action="store_true", help="record the decisions (default: dry run)")
    parser.add_argument("--report", type=Path, help="where to write the run's report (JSON)")
    return parser


def load_decisions(path: Path) -> list[Decision]:
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("the decisions file must be a JSON list")
    decisions = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != set(FIELDS):
            raise ValueError(f"decision {index} must have exactly these fields: {', '.join(FIELDS)}")
        if not all(isinstance(item[name], str) for name in FIELDS):
            raise ValueError(f"decision {index}: every field is a string")
        decisions.append(Decision(**{name: item[name] for name in FIELDS}))
    return decisions


async def _ids(tenant_slug: str, operator_email: str) -> tuple[str | None, str | None]:
    async with SessionLocal() as session:
        tenant_id = await session.scalar(select(TenantModel.id).where(TenantModel.slug == tenant_slug))
        user_id = await session.scalar(select(UserModel.id).where(UserModel.email == operator_email.strip().lower()))
    return tenant_id, user_id


async def run(args: argparse.Namespace) -> RunReport:
    tenant_id, operator_id = await _ids(args.tenant, args.operator_email)
    if tenant_id is None:
        raise ClassificationRefused("UNKNOWN_TENANT", "no tenant with that slug")
    if operator_id is None:
        raise ClassificationRefused("UNKNOWN_OPERATOR", "no account with that email")
    service = ClassificationService(classification_store, settings.content_classification_max_per_run)
    return await service.run(
        tenant_id=tenant_id,
        operator_user_id=operator_id,
        authorization_id=args.authorization,
        decisions=load_decisions(args.decisions),
        apply=args.apply,
    )


def report_json(report: RunReport) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": report.tenant_id,
        "authorization_id": report.authorization_id,
        "operator_user_id": report.operator_user_id,
        "applied": report.applied,
        "run_id": report.run_id,
        "counts": report.counts(),
        "outcomes": [asdict(outcome) for outcome in report.outcomes],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if settings.app_environment == "testing":
        print("refusing to run with APP_ENVIRONMENT=testing (in-memory database)")
        return 2
    try:
        report = asyncio.run(run(args))
    except (ValueError, OSError) as exc:
        print(f"refused: {exc}")
        return 2
    except ClassificationRefused as exc:
        print(f"refused ({exc.code}): {exc}")
        return 1
    body = report_json(report)
    print(("applied" if report.applied else "dry run, nothing changed") + f": {body['counts']}")
    for outcome in report.outcomes:
        print(f"  {outcome.asset_id}: {outcome.result}" + (f" ({outcome.reason})" if outcome.reason else ""))
    if args.report:
        args.report.write_text(json.dumps(body, indent=2), encoding="utf-8")
        print(f"report written to {args.report}")
    return 1 if body["counts"].get("refused") else 0


if __name__ == "__main__":
    sys.exit(main())
