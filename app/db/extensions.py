from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

POSTGRES_EXTENSIONS = ("pg_trgm", "fuzzystrmatch", "unaccent")


async def create_postgres_extensions(session: AsyncSession | AsyncConnection):
    for stmt in [
        f"CREATE EXTENSION IF NOT EXISTS {ext};" for ext in POSTGRES_EXTENSIONS
    ]:
        await session.execute(text(stmt))

    await session.commit()
