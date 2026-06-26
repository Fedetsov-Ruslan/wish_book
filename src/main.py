import asyncio
import logging

import asyncpg
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from redis.asyncio import Redis

from src.config import config
from src.database import create_pool, init_db
from src.handlers import add_wish, common, my_wishes, partner_wishes, registration
from src.middleware import DbMiddleware, SchedulerMiddleware
from src.services.scheduler import NotificationScheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    )

    pool: asyncpg.Pool = await create_pool()
    await init_db(pool)

    redis: Redis = Redis.from_url(config.REDIS_URL, decode_responses=True)

    bot = Bot(token=config.BOT_TOKEN)

    scheduler = NotificationScheduler(
        redis=redis,
        bot=bot,
        delay_seconds=config.NOTIFICATION_DELAY_SECONDS,
    )
    # Recreate background tasks for notifications that survived a restart
    await scheduler.restore()

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbMiddleware(pool))
    dp.update.middleware(SchedulerMiddleware(scheduler))

    dp.include_router(common.router)
    dp.include_router(registration.router)
    dp.include_router(add_wish.router)
    dp.include_router(my_wishes.router)
    dp.include_router(partner_wishes.router)

    logging.info("Starting WishBook bot…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await pool.close()
        await redis.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
