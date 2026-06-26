import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.kbds.menu_kb import main_menu_kb
from src.repositories.user_repo import UserRepository
from src.states.reg_states import RegStates
from src.utils import delete_after, safe_delete

router = Router()


def _confirm_partner_kb(partner_tg_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, это мой партнёр",
            callback_data=f"reg_confirm:{partner_tg_id}:yes",
        ),
        InlineKeyboardButton(
            text="❌ Нет, другой человек",
            callback_data=f"reg_confirm:{partner_tg_id}:no",
        ),
    )
    return builder.as_markup()


# ── Step 1: name ──────────────────────────────────────────────────────────────

@router.message(RegStates.name)
async def reg_name(
    message: Message, state: FSMContext, db: asyncpg.Connection
) -> None:
    name = (message.text or "").strip()
    if not name:
        err = await message.answer("Пожалуйста, введите имя текстом.")
        delete_after(err, 5)
        await safe_delete(message)
        return

    await safe_delete(message)
    await state.update_data(name=name)

    user_repo = UserRepository(db)
    waiting = await user_repo.find_waiting_for(message.from_user.id)

    if waiting:
        # Someone already registered with us as their partner — confirm shortcut
        await state.update_data(pending_partner_tg_id=waiting.tg_id)
        await state.set_state(RegStates.confirm_partner)
        await message.answer(
            f"Приятно познакомиться, <b>{name}</b>! 🎉\n\n"
            f"Похоже, <b>{waiting.name}</b> уже указал вас как партнёра.\n"
            "Это ваш партнёр?",
            parse_mode="HTML",
            reply_markup=_confirm_partner_kb(waiting.tg_id),
        )
    else:
        await state.set_state(RegStates.partner)
        await message.answer(
            f"Приятно познакомиться, <b>{name}</b>! 🎉\n\n"
            "Теперь <b>перешлите любое сообщение</b> от вашего партнёра, "
            "чтобы связать аккаунты.\n\n"
            "⚠️ <i>Если получите ошибку, попросите партнёра изменить настройку:\n"
            "Settings → Privacy → Forwarded Messages → My Contacts или Everyone</i>",
            parse_mode="HTML",
        )


# ── Step 2a: confirm pre-linked partner ───────────────────────────────────────

@router.callback_query(
    RegStates.confirm_partner, F.data.startswith("reg_confirm:")
)
async def reg_confirm_partner(
    call: CallbackQuery, state: FSMContext, db: asyncpg.Connection
) -> None:
    _, raw_id, answer = call.data.split(":")
    partner_tg_id = int(raw_id)

    if answer == "no":
        # Partner rejected — fall back to the forward-message flow
        await state.set_state(RegStates.partner)
        await call.message.edit_text(
            "Хорошо! Тогда <b>перешлите любое сообщение</b> от вашего "
            "партнёра, чтобы связать аккаунты.\n\n"
            "⚠️ <i>Если получите ошибку, попросите партнёра изменить "
            "настройку:\n"
            "Settings → Privacy → Forwarded Messages → "
            "My Contacts или Everyone</i>",
            parse_mode="HTML",
        )
        await call.answer()
        return

    # answer == "yes" — confirmed
    data = await state.get_data()
    name: str = data["name"]

    user_repo = UserRepository(db)
    partner = await user_repo.get_by_tg_id(partner_tg_id)

    await user_repo.create(
        tg_id=call.from_user.id,
        name=name,
        partner_tg_id=partner_tg_id,
    )
    # Link back to the partner who was waiting
    await user_repo.update_partner(partner_tg_id, call.from_user.id)

    await state.clear()

    partner_name = partner.name if partner else "Партнёр"
    await call.message.edit_text(
        f"✅ Регистрация завершена!\n"
        f"Вы связаны с <b>{partner_name}</b>! 🎉",
        parse_mode="HTML",
    )
    await call.message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu_kb(partner_name),
    )
    await call.answer()


# ── Step 2b: forward partner's message ───────────────────────────────────────

@router.message(RegStates.partner)
async def reg_partner(
    message: Message, state: FSMContext, db: asyncpg.Connection
) -> None:
    if not message.forward_from:
        await safe_delete(message)
        err = await message.answer(
            "❌ <b>Не удалось получить Telegram ID партнёра.</b>\n\n"
            "Возможные причины:\n"
            "• Партнёр запретил пересылку сообщений\n\n"
            "Попросите партнёра разрешить пересылку:\n"
            "<i>Settings → Privacy and Security → Forwarded Messages → "
            "My Contacts или Everyone</i>\n\n"
            "После этого перешлите его сообщение снова.",
            parse_mode="HTML",
        )
        delete_after(err, 10)
        return

    partner_tg_id = message.forward_from.id

    if partner_tg_id == message.from_user.id:
        await safe_delete(message)
        err = await message.answer(
            "❌ Вы переслали своё собственное сообщение.\n"
            "Пожалуйста, перешлите сообщение от вашего <b>партнёра</b>.",
            parse_mode="HTML",
        )
        delete_after(err, 6)
        return

    await safe_delete(message)

    data = await state.get_data()
    name: str = data["name"]

    user_repo = UserRepository(db)

    await user_repo.create(
        tg_id=message.from_user.id,
        name=name,
        partner_tg_id=partner_tg_id,
    )

    partner = await user_repo.get_by_tg_id(partner_tg_id)

    if partner:
        # Partner already registered — link both directions
        await user_repo.update_partner(partner_tg_id, message.from_user.id)
        await state.clear()
        await message.answer(
            f"✅ Регистрация завершена!\n"
            f"Вы связаны с <b>{partner.name}</b>! 🎉",
            parse_mode="HTML",
            reply_markup=main_menu_kb(partner.name),
        )
    else:
        # Check if someone already forwarded OUR message and is waiting
        waiting = await user_repo.find_waiting_for(message.from_user.id)
        if waiting:
            await user_repo.update_partner(waiting.tg_id, message.from_user.id)
            await state.clear()
            await message.answer(
                f"✅ Регистрация завершена!\n"
                f"Вы связаны с <b>{waiting.name}</b>! 🎉",
                parse_mode="HTML",
                reply_markup=main_menu_kb(waiting.name),
            )
        else:
            await state.clear()
            await message.answer(
                "✅ Регистрация завершена!\n\n"
                "⏳ Ожидаем регистрации вашего партнёра.\n"
                "Как только он зарегистрируется — связь установится "
                "автоматически.",
                parse_mode="HTML",
                reply_markup=main_menu_kb("Партнёр"),
            )
