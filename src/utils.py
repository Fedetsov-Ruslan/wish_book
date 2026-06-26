import asyncio
import logging

from aiogram.types import Message

logger = logging.getLogger(__name__)


def delete_after(message: Message, delay: float = 5.0) -> None:
    """Schedule a message for deletion after `delay` seconds (fire-and-forget)."""
    asyncio.create_task(_do_delete(message, delay))


async def safe_delete(message: Message) -> None:
    """Delete a message immediately, ignoring errors (e.g. already deleted)."""
    try:
        await message.delete()
    except Exception:
        pass


async def _do_delete(message: Message, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass
