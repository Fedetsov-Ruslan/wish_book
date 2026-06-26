import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

logger = logging.getLogger(__name__)


async def notify_partner_new_wish(bot: Bot, partner_tg_id: int, author_name: str) -> None:
    """
    Send a notification to the partner when a new shared wish is created.
    Does NOT reveal the wish content — partner should open the bot to see it.
    Silently ignores errors (partner blocked the bot, hasn't started it, etc.).
    """
    try:
        await bot.send_message(
            chat_id=partner_tg_id,
            text=(
                f"🔔 У <b>{author_name}</b> появилось новое желание!\n\n"
                "Открой раздел с желаниями партнёра, чтобы посмотреть 👀"
            ),
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        # Partner blocked the bot or hasn't started it yet
        logger.debug("Could not notify partner %d: bot blocked or not started", partner_tg_id)
    except Exception as e:
        logger.warning("Failed to notify partner %d: %s", partner_tg_id, e)
