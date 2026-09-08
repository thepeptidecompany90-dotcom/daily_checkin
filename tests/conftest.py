import asyncpg
import pytest
import pytest_asyncio
from testcontainers.community.postgres import PostgresContainer

from glp1_agent.db.migrate import apply_migrations


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest_asyncio.fixture(scope="session")
async def db_pool(postgres_container):
    dsn = postgres_container.get_connection_url(driver=None)
    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        await apply_migrations(conn)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def conn(db_pool):
    """A single connection with its own transaction, rolled back after each test.

    Repos only use fetch/fetchrow/fetchval/execute, so a raw Connection is a
    drop-in stand-in for a Pool here — this gives per-test isolation without
    re-running migrations for every test.
    """
    async with db_pool.acquire() as connection:
        tx = connection.transaction()
        await tx.start()
        try:
            yield connection
        finally:
            await tx.rollback()
