import asyncpg
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.kbds.menu_kb import main_menu_kb
from src.repositories.user_repo import UserRepository

router = Router()


async def _send_menu(target: Message, user_repo: UserRepository, tg_id: int) -> None:
    user = await user_repo.get_by_tg_id(tg_id)
    if not user:
        await target.answer("Вы не зарегистрированы. Введите /start")
        return
    partner_name = "Партнёр"
    if user.partner_tg_id:
        partner = await user_repo.get_by_tg_id(user.partner_tg_id)
        if partner:
            partner_name = partner.name
    await target.answer("🏠 Главное меню", reply_markup=main_menu_kb(partner_name))


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db: asyncpg.Connection) -> None:
    await state.clear()
    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(message.from_user.id)

    if user is None:
        from src.states.reg_states import RegStates

        await state.set_state(RegStates.name)
        await message.answer(
            "👋 Добро пожаловать в <b>WishBook</b>! 🎁\n\n"
            "Давайте познакомимся. Как вас зовут?",
            parse_mode="HTML",
        )
    else:
        partner_name = "Партнёр"
        if user.partner_tg_id:
            partner = await user_repo.get_by_tg_id(user.partner_tg_id)
            if partner:
                partner_name = partner.name
        await message.answer(
            f"👋 С возвращением, <b>{user.name}</b>!",
            parse_mode="HTML",
            reply_markup=main_menu_kb(partner_name),
        )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db: asyncpg.Connection) -> None:
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    user_repo = UserRepository(db)
    await _send_menu(message, user_repo, message.from_user.id)


@router.callback_query(lambda c: c.data == "go_menu")
async def cb_go_menu(call: CallbackQuery, state: FSMContext, db: asyncpg.Connection) -> None:
    await state.clear()
    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(call.from_user.id)
    partner_name = "Партнёр"
    if user and user.partner_tg_id:
        partner = await user_repo.get_by_tg_id(user.partner_tg_id)
        if partner:
            partner_name = partner.name
    # Delete the inline message to keep the chat clean
    try:
        await call.message.delete()
    except Exception:
        await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("🏠 Главное меню", reply_markup=main_menu_kb(partner_name))
    await call.answer()
