import asyncio
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def apply_migrations(
    conn: asyncpg.Connection | asyncpg.Pool, verbose: bool = False
) -> None:
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if verbose:
            print(f"applying {migration.name}")
        await conn.execute(migration.read_text())


async def _main() -> None:
    from glp1_agent.config import Settings

    settings = Settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        await apply_migrations(conn, verbose=True)
    finally:
        await conn.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(_main())
