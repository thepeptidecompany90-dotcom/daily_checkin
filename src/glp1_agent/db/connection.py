import asyncpg


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url)
