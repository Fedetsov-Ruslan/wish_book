from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb(partner_name: str = "Партнёр") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить")],
            [
                KeyboardButton(text="📋 Мои желания"),
                KeyboardButton(text=f"💝 {partner_name}"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
