import asyncpg
from asyncpg import Pool
from loguru import logger
from bot.config import settings


_pool: Pool | None = None


async def create_pool() -> Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.get_db_dsn(),
        min_size=5,
        max_size=20,
        command_timeout=60,
        server_settings={"application_name": "uzimiznikilar_bot"},
    )
    logger.info("✅ Database pool created")
    return _pool


async def get_pool() -> Pool:
    global _pool
    if _pool is None:
        await create_pool()
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Database pool closed")
