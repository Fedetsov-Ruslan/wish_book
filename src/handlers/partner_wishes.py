import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.kbds.wish_kb import WishSelectCD, partner_wish_detail_kb, wish_list_kb
from src.repositories.user_repo import UserRepository
from src.repositories.wish_repo import WishRepository
from src.templates.messages import grouped_wish_display, wish_card

router = Router()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_partner(db: asyncpg.Connection, tg_id: int):
    """Return (current_user, partner) or (user, None) if partner not found."""
    repo = UserRepository(db)
    user = await repo.get_by_tg_id(tg_id)
    if not user or not user.partner_tg_id:
        return user, None
    partner = await repo.get_by_tg_id(user.partner_tg_id)
    return user, partner


async def _show_list(target: Message | CallbackQuery, db: asyncpg.Connection, edit: bool = False) -> None:
    tg_id = target.from_user.id
    _, partner = await _get_partner(db, tg_id)
    msg = target.message if isinstance(target, CallbackQuery) else target

    if not partner:
        text = "👥 Партнёр ещё не зарегистрировался в боте."
        if edit:
            await msg.edit_text(text)
        else:
            await msg.answer(text)
        return

    wish_repo = WishRepository(db)
    wishes = await wish_repo.get_partner_wishes(partner.id)
    text, ordered = grouped_wish_display(wishes, mine=False)
    # Replace header to include partner name
    text = text.replace("💝 Желания партнёра", f"💝 Желания {partner.name}", 1)
    kb = wish_list_kb(ordered, is_mine=False)

    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


# ── Entry: "💝 <Partner name>" ────────────────────────────────────────────────

@router.message(F.text.startswith("💝 "))
async def show_partner_wishes(
    message: Message, state: FSMContext, db: asyncpg.Connection
) -> None:
    await state.clear()
    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Введите /start")
        return
    if not user.partner_tg_id:
        await message.answer(
            "👥 У вас пока нет партнёра.\n\n"
            "Пройдите регистрацию заново, переслав сообщение партнёра (/start)."
        )
        return

    await _show_list(message, db, edit=False)


# ── Back to partner list ──────────────────────────────────────────────────────

@router.callback_query(F.data == "partner_wishes_list")
async def cb_partner_wishes_list(call: CallbackQuery, db: asyncpg.Connection) -> None:
    await _show_list(call, db, edit=True)
    await call.answer()


# ── Open a specific wish (read-only detail) ───────────────────────────────────

@router.callback_query(WishSelectCD.filter(F.is_mine == 0))
async def open_partner_wish(
    call: CallbackQuery, callback_data: WishSelectCD, db: asyncpg.Connection
) -> None:
    _, partner = await _get_partner(db, call.from_user.id)
    if not partner:
        await call.answer("Партнёр не найден")
        return

    wish_repo = WishRepository(db)
    wishes = await wish_repo.get_partner_wishes(partner.id)
    ids = [w.id for w in wishes]
    try:
        idx = ids.index(callback_data.wish_id)
    except ValueError:
        await call.answer("Желание не найдено")
        return

    wish = wishes[idx]
    text = wish_card(wish, idx + 1, len(wishes), mine=False)
    await call.message.edit_text(
        text, parse_mode="HTML", reply_markup=partner_wish_detail_kb()
    )
    await call.answer()
