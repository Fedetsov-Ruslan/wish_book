"""
Delayed notification scheduler backed by Redis.

Redis key : notify:{user_id}:{wish_id}
Redis value: JSON { wish_id, user_id, partner_tg_id, author_name, send_at, status }
TTL        : delay + 1 h (safety net if the process crashes mid-task)

``status`` tracks delivery so a crash or a blocked partner doesn't just
vanish silently:
  pending -> sent      (delivered; key is deleted immediately)
  pending -> blocked   (partner blocked/never started the bot; key kept
                        until TTL for inspection, not retried)
  pending -> failed    (unexpected error sending; key kept until TTL,
                        not retried)

Call ``await scheduler.restore()`` once at startup to recreate asyncio
tasks for any *pending* keys that survived an application restart. Keys
already resolved (sent/blocked/failed) are left alone — they're just the
audit trail until their TTL expires.
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


class NotificationStatus:
    PENDING = "pending"
    SENT = "sent"
    BLOCKED = "blocked"
    FAILED = "failed"


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
            "status": NotificationStatus.PENDING,
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
        skipped_resolved = 0

        for key in keys:
            raw = await self.redis.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)

                # Already resolved before the crash (sent/blocked/failed) —
                # it's just an audit-trail leftover until TTL, not a retry
                # candidate.
                if data.get("status", NotificationStatus.PENDING) != NotificationStatus.PENDING:
                    skipped_resolved += 1
                    continue

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
            "Restored %d pending notification(s) from Redis (%d already resolved)",
            restored,
            skipped_resolved,
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
            status = await notify_partner_new_wish(self.bot, partner_tg_id, author_name)
            await self._resolve(wish_id, redis_key, status)
        except asyncio.CancelledError:
            pass  # cancelled via cancel(); Redis key already deleted there
        except Exception as exc:
            logger.error(
                "Notification task failed unexpectedly: wish_id=%d error=%s", wish_id, exc
            )
            await self._resolve(wish_id, redis_key, NotificationStatus.FAILED)

    async def _resolve(self, wish_id: int, redis_key: str, status: str) -> None:
        """Record the final delivery status and drop the in-memory task handle."""
        self._tasks.pop(wish_id, None)
        self._keys.pop(wish_id, None)

        if status == NotificationStatus.SENT:
            await self.redis.delete(redis_key)
            logger.info("Notification sent and cleaned up: wish_id=%d", wish_id)
            return

        # Not delivered — keep the record (with its existing TTL) so the
        # failure/blocked state is inspectable instead of silently lost.
        raw = await self.redis.get(redis_key)
        if raw:
            data = json.loads(raw)
            data["status"] = status
            ttl = await self.redis.ttl(redis_key)
            await self.redis.set(redis_key, json.dumps(data), ex=ttl if ttl and ttl > 0 else None)
        logger.warning(
            "Notification not delivered: wish_id=%d status=%s", wish_id, status
        )
