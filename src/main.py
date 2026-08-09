import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from starlette.responses import Response

from src.api import users, wishes
from src.config import config
from src.database import create_pool, init_db
from src.services import storage
from src.services.scheduler import NotificationScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class NoCacheStaticFiles(StaticFiles):
    """
    Forces revalidation on every request (Cache-Control: no-cache) instead of
    Starlette's default of no explicit header at all.

    Without this, browsers/WebViews apply heuristic caching and can serve a
    stale index.html/app.js/style.css for a long time after a deploy without
    ever re-asking the server — this is exactly what happened when the Mini
    App kept showing old design changes after a rebuild. `no-cache` (not
    `no-store`) still lets the client send a conditional GET and get a cheap
    304 back when the file genuinely hasn't changed, via the ETag Starlette
    already computes from the file's mtime/size.
    """

    def file_response(self, *args: object, **kwargs: object) -> Response:
        response = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool: asyncpg.Pool = await create_pool()
    await init_db(pool)
    await storage.ensure_bucket()

    redis: Redis = Redis.from_url(config.REDIS_URL, decode_responses=True)
    bot = Bot(token=config.BOT_TOKEN)

    # No polling/webhook anymore — the bot only (a) sends the delayed partner
    # notifications and (b) exposes a persistent Menu Button that opens the
    # Mini App directly. Setting the button is idempotent, safe to redo on
    # every startup.
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=config.WEBAPP_URL))
    )
    me = await bot.get_me()

    scheduler = NotificationScheduler(
        redis=redis,
        bot=bot,
        delay_seconds=config.NOTIFICATION_DELAY_SECONDS,
    )
    await scheduler.restore()

    app.state.pool = pool
    app.state.redis = redis
    app.state.bot = bot
    app.state.scheduler = scheduler
    app.state.bot_username = me.username

    logger.info("WishBook API started")
    try:
        yield
    finally:
        await pool.close()
        await redis.aclose()
        await bot.session.close()
        logger.info("WishBook API stopped")


app = FastAPI(title="WishBook", lifespan=lifespan)
app.include_router(users.router)
app.include_router(wishes.router)

# Mounted last so it doesn't shadow the /api/* routes above.
app.mount("/", NoCacheStaticFiles(directory="static", html=True), name="static")
