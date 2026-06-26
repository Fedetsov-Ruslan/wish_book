from typing import Any, Awaitable, Callable, Dict

import asyncpg
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services.scheduler import NotificationScheduler


class DbMiddleware(BaseMiddleware):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with self.pool.acquire() as conn:
            data["db"] = conn
            return await handler(event, data)


class SchedulerMiddleware(BaseMiddleware):
    def __init__(self, scheduler: NotificationScheduler) -> None:
        self.scheduler = scheduler

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["scheduler"] = self.scheduler
        return await handler(event, data)
