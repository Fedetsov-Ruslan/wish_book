import asyncpg

from src.config import config


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=config.postgres_dsn,
        min_size=2,
        max_size=10,
    )


async def init_db(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                tg_id         BIGINT UNIQUE NOT NULL,
                name          TEXT   NOT NULL,
                partner_tg_id BIGINT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wishes (
                id            SERIAL PRIMARY KEY,
                user_id       INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title         TEXT        NOT NULL,
                deadline      TEXT        NOT NULL,
                deadline_date TIMESTAMPTZ,
                visibility    TEXT        NOT NULL DEFAULT 'private',
                is_completed  BOOLEAN     NOT NULL DEFAULT FALSE,
                is_hidden     BOOLEAN     NOT NULL DEFAULT FALSE,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Safe migration: add the column to existing tables if it was created before this change
        await conn.execute("""
            ALTER TABLE wishes ADD COLUMN IF NOT EXISTS
                deadline_date TIMESTAMPTZ
        """)

        # Safe migration: MinIO object key for an optional image/GIF attachment
        await conn.execute("""
            ALTER TABLE wishes ADD COLUMN IF NOT EXISTS
                attachment_key TEXT
        """)
