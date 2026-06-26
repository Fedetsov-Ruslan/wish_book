"""
Delayed notification scheduler backed by Redis.

Redis key : notify:{user_id}:{wish_id}
Redis value: JSON { wish_id, user_id, partner_tg_id, author_name, send_at }
TTL        : delay + 1 h (safety net if the process crashes mid-task)

Call ``await scheduler.restore()`` once at startup to recreate asyncio
tasks for any pending keys that survived an application restart.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from redis.asyncio import Redis

from src.services.notification import notify_partner_new_wish

logger = logging.getLogger(__name__)

_KEY_PREFIX = "notify"


class NotificationScheduler:
    def __init__(self, redis: Redis, bot: Bot, delay_seconds: int) -> None:
        self.redis = redis
        self.bot = bot
        self.delay = delay_seconds
        self._tasks: dict[int, asyncio.Task] = {}  # wish_id → Task
        self._keys: dict[int, str] = {}             # wish_id → Redis key

    # ── Public API ────────────────────────────────────────────────────────

    async def schedule(
        self,
        wish_id: int,
        user_id: int,
        partner_tg_id: int,
        author_name: str,
    ) -> None:
        """Schedule a notification; cancels any existing one for this wish."""
        await self.cancel(wish_id)

        send_at = datetime.now(timezone.utc) + timedelta(seconds=self.delay)
        redis_key = f"{_KEY_PREFIX}:{user_id}:{wish_id}"

        payload = json.dumps({
            "wish_id": wish_id,
            "user_id": user_id,
            "partner_tg_id": partner_tg_id,
            "author_name": author_name,
            "send_at": send_at.isoformat(),
        })
        await self.redis.set(redis_key, payload, ex=self.delay + 3600)

        self._keys[wish_id] = redis_key
        self._tasks[wish_id] = asyncio.create_task(
            self._run(wish_id, redis_key, partner_tg_id, author_name, self.delay)
        )
        logger.info(
            "Notification scheduled: wish_id=%d in %ds", wish_id, self.delay
        )

    async def cancel(self, wish_id: int) -> None:
        """Cancel and remove any pending notification for this wish."""
        task = self._tasks.pop(wish_id, None)
        if task:
            task.cancel()

        key = self._keys.pop(wish_id, None)
        if key:
            await self.redis.delete(key)
            logger.info("Notification cancelled: wish_id=%d", wish_id)

    async def restore(self) -> None:
        """
        Called once at startup.
        Reads all pending keys from Redis and recreates asyncio tasks
        with the remaining time left to fire.
        """
        keys = await self.redis.keys(f"{_KEY_PREFIX}:*")
        if not keys:
            return

        now = datetime.now(timezone.utc)
        restored = 0

        for key in keys:
            raw = await self.redis.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
                wish_id: int = data["wish_id"]
                partner_tg_id: int = data["partner_tg_id"]
                author_name: str = data["author_name"]
                send_at = datetime.fromisoformat(data["send_at"])
                remaining = max(0.0, (send_at - now).total_seconds())

                self._keys[wish_id] = key
                self._tasks[wish_id] = asyncio.create_task(
                    self._run(
                        wish_id, key, partner_tg_id, author_name, remaining
                    )
                )
                restored += 1
                logger.info(
                    "Restored notification: wish_id=%d remaining=%.1fs",
                    wish_id,
                    remaining,
                )
            except Exception as exc:
                logger.warning(
                    "Could not restore notification from key %s: %s", key, exc
                )

        logger.info(
            "Restored %d pending notification(s) from Redis", restored
        )

    # ── Internal task ─────────────────────────────────────────────────────

    async def _run(
        self,
        wish_id: int,
        redis_key: str,
        partner_tg_id: int,
        author_name: str,
        delay: float,
    ) -> None:
        try:
            await asyncio.sleep(delay)
            await notify_partner_new_wish(self.bot, partner_tg_id, author_name)
            await self.redis.delete(redis_key)
            self._tasks.pop(wish_id, None)
            self._keys.pop(wish_id, None)
            logger.info(
                "Notification sent and cleaned up: wish_id=%d", wish_id
            )
        except asyncio.CancelledError:
            pass  # cancelled via cancel(); Redis key already deleted there
        except Exception as exc:
            logger.error(
                "Notification task failed: wish_id=%d error=%s", wish_id, exc
            )
