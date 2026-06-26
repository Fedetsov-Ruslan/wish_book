import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.kbds.wish_kb import (
    EditDeadlineCD,
    WishActionCD,
    WishSelectCD,
    delete_confirm_kb,
    edit_deadline_kb,
    my_wish_kb,
    wish_list_kb,
)
from src.repositories.user_repo import UserRepository
from src.repositories.wish_repo import WishRepository
from src.services.deadline import compute_deadline_date
from src.services.scheduler import NotificationScheduler
from src.states.wish_states import EditWishStates
from src.templates.messages import grouped_wish_display, wish_card
from src.utils import delete_after, safe_delete

router = Router()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_id(db: asyncpg.Connection, tg_id: int) -> int | None:
    repo = UserRepository(db)
    user = await repo.get_by_tg_id(tg_id)
    return user.id if user else None


async def _show_list(target: Message | CallbackQuery, db: asyncpg.Connection, edit: bool = False) -> None:
    """Render the grouped wish list into a message."""
    tg_id = target.from_user.id
    user_id = await _get_user_id(db, tg_id)
    if not user_id:
        text, kb = "Вы не зарегистрированы.", None
    else:
        wish_repo = WishRepository(db)
        wishes = await wish_repo.get_my_wishes(user_id)
        text, ordered = grouped_wish_display(wishes, mine=True)
        kb = wish_list_kb(ordered, is_mine=True)

    msg = target.message if isinstance(target, CallbackQuery) else target
    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


async def _render_wish(
    wish_repo: WishRepository,
    user_id: int,
    wish_id: int,
) -> tuple[str, object] | None:
    wishes = await wish_repo.get_my_wishes(user_id)
    if not wishes:
        return None
    ids = [w.id for w in wishes]
    try:
        idx = ids.index(wish_id)
    except ValueError:
        idx = 0
    wish = wishes[idx]
    text = wish_card(wish, idx + 1, len(wishes), mine=True)
    kb = my_wish_kb(wish.id, wish.is_completed, wish.visibility)
    return text, kb


# ── Entry: "📋 Мои желания" ───────────────────────────────────────────────────

@router.message(F.text == "📋 Мои желания")
async def show_my_wishes(
    message: Message, state: FSMContext, db: asyncpg.Connection
) -> None:
    await state.clear()
    await _show_list(message, db, edit=False)


# ── Back to list (from detail view) ──────────────────────────────────────────

@router.callback_query(F.data == "my_wishes_list")
async def cb_my_wishes_list(call: CallbackQuery, db: asyncpg.Connection) -> None:
    await _show_list(call, db, edit=True)
    await call.answer()


# ── Open a specific wish (detail view) ───────────────────────────────────────

@router.callback_query(WishSelectCD.filter(F.is_mine == 1))
async def open_my_wish(
    call: CallbackQuery, callback_data: WishSelectCD, db: asyncpg.Connection
) -> None:
    user_id = await _get_user_id(db, call.from_user.id)
    wish_repo = WishRepository(db)
    result = await _render_wish(wish_repo, user_id, callback_data.wish_id)
    if result:
        text, kb = result
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


# ── Edit title ────────────────────────────────────────────────────────────────

@router.callback_query(WishActionCD.filter(F.action == "edit"))
async def wish_edit_start(
    call: CallbackQuery, callback_data: WishActionCD, state: FSMContext
) -> None:
    await state.set_state(EditWishStates.new_title)
    await call.message.edit_reply_markup(reply_markup=None)
    sent = await call.message.answer(
        "✏️ Введите новый текст желания:\n<i>(/cancel — отмена)</i>",
        parse_mode="HTML",
    )
    await state.update_data(
        editing_wish_id=callback_data.wish_id,
        edit_prompt_msg_id=sent.message_id,
    )
    await call.answer()


@router.message(EditWishStates.new_title)
async def wish_edit_save(
    message: Message, state: FSMContext, db: asyncpg.Connection
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Введите текст желания.")
        return

    data = await state.get_data()
    wish_id: int = data["editing_wish_id"]
    await state.clear()

    if data.get("edit_prompt_msg_id"):
        try:
            await message.bot.delete_message(message.chat.id, data["edit_prompt_msg_id"])
        except Exception:
            pass
    await safe_delete(message)

    wish_repo = WishRepository(db)
    await wish_repo.update_title(wish_id, title)

    user_id = await _get_user_id(db, message.from_user.id)
    result = await _render_wish(wish_repo, user_id, wish_id)
    if result:
        text, kb = result
        notif = await message.answer("✅ Желание обновлено!")
        delete_after(notif, 3)
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        notif = await message.answer("✅ Желание обновлено!")
        delete_after(notif, 3)


# ── Edit deadline ─────────────────────────────────────────────────────────────

@router.callback_query(WishActionCD.filter(F.action == "deadline"))
async def wish_deadline_start(
    call: CallbackQuery, callback_data: WishActionCD
) -> None:
    await call.message.edit_text(
        "📅 Выберите новый срок:",
        reply_markup=edit_deadline_kb(callback_data.wish_id),
    )
    await call.answer()


@router.callback_query(EditDeadlineCD.filter())
async def wish_deadline_save(
    call: CallbackQuery, callback_data: EditDeadlineCD, db: asyncpg.Connection
) -> None:
    wish_repo = WishRepository(db)
    new_deadline_date = compute_deadline_date(callback_data.value)
    await wish_repo.update_deadline(callback_data.wish_id, callback_data.value, new_deadline_date)

    user_id = await _get_user_id(db, call.from_user.id)
    result = await _render_wish(wish_repo, user_id, callback_data.wish_id)
    if result:
        text, kb = result
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer("✅ Срок обновлён!")


# ── Toggle completed ──────────────────────────────────────────────────────────

@router.callback_query(WishActionCD.filter(F.action == "complete"))
async def wish_toggle_complete(
    call: CallbackQuery, callback_data: WishActionCD, db: asyncpg.Connection
) -> None:
    wish_repo = WishRepository(db)
    await wish_repo.toggle_completed(callback_data.wish_id)

    user_id = await _get_user_id(db, call.from_user.id)
    result = await _render_wish(wish_repo, user_id, callback_data.wish_id)
    if result:
        text, kb = result
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

    wish = await wish_repo.get_by_id(callback_data.wish_id)
    status = "выполнено ✅" if (wish and wish.is_completed) else "возвращено в работу"
    await call.answer(f"Желание {status}!")


# ── Toggle visibility (Личное ↔ Общее) ───────────────────────────────────────

@router.callback_query(WishActionCD.filter(F.action == "hidden"))
async def wish_toggle_visibility(
    call: CallbackQuery,
    callback_data: WishActionCD,
    db: asyncpg.Connection,
    scheduler: NotificationScheduler,
) -> None:
    wish_repo = WishRepository(db)
    wish = await wish_repo.get_by_id(callback_data.wish_id)
    if not wish:
        await call.answer("Желание не найдено")
        return

    new_vis = "private" if wish.visibility == "shared" else "shared"
    await wish_repo.update_visibility(callback_data.wish_id, new_vis)

    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(call.from_user.id)

    if new_vis == "shared":
        # private → shared: schedule delayed notification
        if user and user.partner_tg_id:
            await scheduler.schedule(
                wish_id=callback_data.wish_id,
                user_id=user.id,
                partner_tg_id=user.partner_tg_id,
                author_name=user.name,
            )
    else:
        # shared → private: cancel any pending notification
        await scheduler.cancel(callback_data.wish_id)

    user_id = user.id if user else await _get_user_id(db, call.from_user.id)
    result = await _render_wish(wish_repo, user_id, callback_data.wish_id)
    if result:
        text, kb = result
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

    toast = "Желание стало Личным 👤" if new_vis == "private" else "Желание стало Общим 💑"
    await call.answer(toast)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.callback_query(WishActionCD.filter(F.action == "delete"))
async def wish_delete_confirm(
    call: CallbackQuery, callback_data: WishActionCD, db: asyncpg.Connection
) -> None:
    wish_repo = WishRepository(db)
    wish = await wish_repo.get_by_id(callback_data.wish_id)
    title = wish.title if wish else "?"
    await call.message.edit_text(
        f"🗑 Вы точно хотите удалить желание?\n\n<b>«{title}»</b>",
        parse_mode="HTML",
        reply_markup=delete_confirm_kb(callback_data.wish_id),
    )
    await call.answer()


@router.callback_query(WishActionCD.filter(F.action == "delete_confirm"))
async def wish_delete_execute(
    call: CallbackQuery,
    callback_data: WishActionCD,
    db: asyncpg.Connection,
    scheduler: NotificationScheduler,
) -> None:
    # Cancel any pending notification before deleting the wish
    await scheduler.cancel(callback_data.wish_id)

    wish_repo = WishRepository(db)
    await wish_repo.delete(callback_data.wish_id)
    await _show_list(call, db, edit=True)
    await call.answer("✅ Удалено!")


# ── Back from action sub-menus (deadline picker, delete confirm) ──────────────

@router.callback_query(WishActionCD.filter(F.action == "back"))
async def wish_action_back(
    call: CallbackQuery, callback_data: WishActionCD, db: asyncpg.Connection
) -> None:
    user_id = await _get_user_id(db, call.from_user.id)
    wish_repo = WishRepository(db)
    result = await _render_wish(wish_repo, user_id, callback_data.wish_id)
    if result:
        text, kb = result
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()
