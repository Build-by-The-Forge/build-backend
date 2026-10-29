from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DB_LOCK_TIMEOUT = "2s"
DB_STATEMENT_TIMEOUT = "15s"
DB_IDLE_TRANSACTION_TIMEOUT = "15s"


async def set_transaction_timeouts(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('lock_timeout', :value, true)"), {"value": DB_LOCK_TIMEOUT})
    await session.execute(text("SELECT set_config('statement_timeout', :value, true)"), {"value": DB_STATEMENT_TIMEOUT})
    await session.execute(
        text("SELECT set_config('idle_in_transaction_session_timeout', :value, true)"),
        {"value": DB_IDLE_TRANSACTION_TIMEOUT},
    )
