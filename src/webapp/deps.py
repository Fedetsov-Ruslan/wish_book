from typing import AsyncIterator

import asyncpg
from fastapi import Request

from src.services.scheduler import NotificationScheduler


async def get_db(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a pooled connection for the lifetime of one request."""
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        yield conn


def get_scheduler(request: Request) -> NotificationScheduler:
    return request.app.state.scheduler
