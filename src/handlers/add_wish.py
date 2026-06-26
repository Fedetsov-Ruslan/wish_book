import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.kbds.menu_kb import main_menu_kb
from src.kbds.wish_kb import (
    DeadlineCD,
    VisibilityCD,
    confirm_kb,
    deadline_kb,
    visibility_kb,
)
from src.repositories.user_repo import UserRepository
from src.repositories.wish_repo import WishRepository
from src.services.deadline import compute_deadline_date
from src.services.scheduler import NotificationScheduler
from src.states.wish_states import AddWishStates
from src.templates.messages import deadline_label, wish_confirmation
from src.utils import delete_after, safe_delete

router = Router()


# ── Entry point ───────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Добавить")
async def add_wish_start(message: Message, state: FSMContext, db: asyncpg.Connection) -> None:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Введите /start")
        return

    partner_name = "Партнёр"
    if user.partner_tg_id:
        partner = await user_repo.get_by_tg_id(user.partner_tg_id)
        if partner:
            partner_name = partner.name

    await state.set_state(AddWishStates.title)
    await state.update_data(user_id=user.id, partner_name=partner_name)

    sent = await message.answer("💭 Введите ваше желание:")
    await state.update_data(prompt_msg_id=sent.message_id, chat_id=message.chat.id)


# ── Step 1: capture title ─────────────────────────────────────────────────────

@router.message(AddWishStates.title)
async def add_wish_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Пожалуйста, введите текст желания.")
        return

    data = await state.get_data()
    await state.update_data(title=title)
    await state.set_state(AddWishStates.deadline)

    # Clean up: delete user text + original prompt (only if it's a separate message)
    await safe_delete(message)
    wizard_msg_id = data.get("wizard_msg_id")
    if not wizard_msg_id and data.get("prompt_msg_id"):
        try:
            await message.bot.delete_message(message.chat.id, data["prompt_msg_id"])
        except Exception:
            pass

    wizard_text = f"💭 <b>Желание:</b> {title}\n\n📅 Выберите срок:"
    if wizard_msg_id:
        # Went back from deadline — edit the existing wizard message
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=wizard_msg_id,
                text=wizard_text,
                parse_mode="HTML",
                reply_markup=deadline_kb(),
            )
        except Exception:
            sent = await message.answer(wizard_text, parse_mode="HTML", reply_markup=deadline_kb())
            await state.update_data(wizard_msg_id=sent.message_id, chat_id=message.chat.id)
    else:
        sent = await message.answer(wizard_text, parse_mode="HTML", reply_markup=deadline_kb())
        await state.update_data(wizard_msg_id=sent.message_id, chat_id=message.chat.id)


# ── Back: deadline → title ────────────────────────────────────────────────────

@router.callback_query(F.data == "add_back:deadline")
async def add_back_to_title(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddWishStates.title)
    data = await state.get_data()
    prev_title = data.get("title", "")

    hint = f'\n\nТекущее: <i>{prev_title}</i>' if prev_title else ""
    await call.message.edit_text(f"💭 Введите ваше желание:{hint}", parse_mode="HTML")
    # wizard_msg_id stays the same — this message IS the wizard
    await call.answer()


# ── Step 2: choose deadline ───────────────────────────────────────────────────

@router.callback_query(DeadlineCD.filter(), AddWishStates.deadline)
async def add_wish_deadline(
    call: CallbackQuery,
    callback_data: DeadlineCD,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    partner_name: str = data.get("partner_name", "Партнёр")

    await state.update_data(deadline=callback_data.value)
    await state.set_state(AddWishStates.visibility)

    await call.message.edit_text(
        f"💭 <b>Желание:</b> {data['title']}\n"
        f"📅 <b>Срок:</b> {deadline_label(callback_data.value)}\n\n"
        "👁 Для кого это желание?",
        parse_mode="HTML",
        reply_markup=visibility_kb(partner_name),
    )
    await call.answer()


# ── Back: visibility → deadline ───────────────────────────────────────────────

@router.callback_query(F.data == "add_back:visibility")
async def add_back_to_deadline(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddWishStates.deadline)
    data = await state.get_data()

    await call.message.edit_text(
        f"💭 <b>Желание:</b> {data.get('title', '')}\n\n📅 Выберите срок:",
        parse_mode="HTML",
        reply_markup=deadline_kb(),
    )
    await call.answer()


# ── Step 3: choose visibility ─────────────────────────────────────────────────

@router.callback_query(VisibilityCD.filter(), AddWishStates.visibility)
async def add_wish_visibility(
    call: CallbackQuery,
    callback_data: VisibilityCD,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    partner_name: str = data.get("partner_name", "Партнёр")

    await state.update_data(visibility=callback_data.value)
    await state.set_state(AddWishStates.confirm)

    await call.message.edit_text(
        wish_confirmation(
            title=data["title"],
            deadline=data["deadline"],
            visibility=callback_data.value,
            partner_name=partner_name,
        ),
        parse_mode="HTML",
        reply_markup=confirm_kb(),
    )
    await call.answer()


# ── Back: confirm → visibility ────────────────────────────────────────────────

@router.callback_query(F.data == "add_back:confirm")
async def add_back_to_visibility(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddWishStates.visibility)
    data = await state.get_data()
    partner_name: str = data.get("partner_name", "Партнёр")

    await call.message.edit_text(
        f"💭 <b>Желание:</b> {data.get('title', '')}\n"
        f"📅 <b>Срок:</b> {deadline_label(data.get('deadline', ''))}\n\n"
        "👁 Для кого это желание?",
        parse_mode="HTML",
        reply_markup=visibility_kb(partner_name),
    )
    await call.answer()


# ── Step 4: confirm and save ──────────────────────────────────────────────────

@router.callback_query(F.data == "wish_confirm", AddWishStates.confirm)
async def add_wish_confirm(
    call: CallbackQuery,
    state: FSMContext,
    db: asyncpg.Connection,
    scheduler: NotificationScheduler,
) -> None:
    data = await state.get_data()
    wish_repo = WishRepository(db)
    user_repo = UserRepository(db)

    wish = await wish_repo.create(
        user_id=data["user_id"],
        title=data["title"],
        deadline=data["deadline"],
        deadline_date=compute_deadline_date(data["deadline"]),
        visibility=data["visibility"],
    )

    await state.clear()

    user = await user_repo.get_by_tg_id(call.from_user.id)
    partner_name = "Партнёр"
    partner_tg_id = user.partner_tg_id if user else None
    if user and user.partner_tg_id:
        partner = await user_repo.get_by_tg_id(user.partner_tg_id)
        if partner:
            partner_name = partner.name

    # Schedule delayed notification if the wish is shared
    if data["visibility"] == "shared" and partner_tg_id and user and wish:
        await scheduler.schedule(
            wish_id=wish.id,
            user_id=user.id,
            partner_tg_id=partner_tg_id,
            author_name=user.name,
        )

    # Edit wizard message to success, then schedule its deletion
    await call.message.edit_text("✅ Желание добавлено! 🎉")
    delete_after(call.message, 4)

    await call.message.answer("🏠 Главное меню", reply_markup=main_menu_kb(partner_name))
    await call.answer()
