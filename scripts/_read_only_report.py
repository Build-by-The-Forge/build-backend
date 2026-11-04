"""Shared by the migration 0030 reports: run one query in a read-only
transaction and print its rows. IDs and codes only, never file names, emails
or text a person wrote. Exit codes: 0 nothing found, 1 rows found."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from sqlalchemy import text

from app.db.session import SessionLocal


async def _rows(sql: str) -> Sequence:
    async with SessionLocal() as session, session.begin():
        # The report can't change anything, even by mistake.
        await session.execute(text("SET TRANSACTION READ ONLY"))
        return (await session.execute(text(sql))).all()


def report(title: str, sql: str, columns: Sequence[str]) -> int:
    rows = asyncio.run(_rows(sql))
    if not rows:
        print(f"{title}: none")
        return 0
    print(f"{title}: {len(rows)}")
    print("\t".join(columns))
    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))
    return 1
