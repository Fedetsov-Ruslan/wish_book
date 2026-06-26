from typing import List

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.schemas.wish import Wish
from src.templates.messages import wish_status_icon

DEADLINE_OPTIONS: list[tuple[str, str]] = [
    ("today",     "Сегодня"),
    ("week",      "На неделе"),
    ("month",     "В течении месяца"),
    ("half_year", "В течении полугода"),
    ("year",      "В течении года"),
    ("someday",   "Как нибудь"),
]


# ── Callback data ─────────────────────────────────────────────────────────────

class DeadlineCD(CallbackData, prefix="dl"):
    value: str


class VisibilityCD(CallbackData, prefix="vis"):
    value: str  # 'private' | 'shared'


class WishActionCD(CallbackData, prefix="wa"):
    action: str  # edit | deadline | complete | delete | delete_confirm | hidden | back
    wish_id: int


class WishSelectCD(CallbackData, prefix="wsel"):
    wish_id: int
    is_mine: int  # 1 = own wish, 0 = partner's wish


class EditDeadlineCD(CallbackData, prefix="ewd"):
    value: str
    wish_id: int


# ── Add-wish wizard ───────────────────────────────────────────────────────────

def deadline_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for value, label in DEADLINE_OPTIONS:
        b.button(text=label, callback_data=DeadlineCD(value=value))
    b.button(text="← Назад", callback_data="add_back:deadline")
    b.button(text="🏠 Меню", callback_data="go_menu")
    b.adjust(2, 2, 2, 2)
    return b.as_markup()


def visibility_kb(partner_name: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="👤 Для себя", callback_data=VisibilityCD(value="private"))
    b.button(text=f"💑 Для {partner_name}", callback_data=VisibilityCD(value="shared"))
    b.button(text="← Назад", callback_data="add_back:visibility")
    b.button(text="🏠 Меню", callback_data="go_menu")
    b.adjust(2, 2)
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="wish_confirm")
    b.button(text="← Назад", callback_data="add_back:confirm")
    b.button(text="🏠 Меню", callback_data="go_menu")
    b.adjust(1)
    return b.as_markup()


# ── Grouped list view ─────────────────────────────────────────────────────────

def wish_list_kb(ordered_wishes: List[Wish], is_mine: bool) -> InlineKeyboardMarkup:
    """One button per wish (in display order), then 🏠 Меню alone."""
    b = InlineKeyboardBuilder()
    for wish in ordered_wishes:
        icon = wish_status_icon(wish)
        title = (wish.title[:22] + "…") if len(wish.title) > 23 else wish.title
        b.button(
            text=f"{icon} {title}",
            callback_data=WishSelectCD(wish_id=wish.id, is_mine=int(is_mine)),
        )
    b.button(text="🏠 Меню", callback_data="go_menu")

    # Two wish-buttons per row, menu button alone at the end
    n = len(ordered_wishes)
    rows: list[int] = []
    for i in range(0, n, 2):
        rows.append(min(2, n - i))
    rows.append(1)
    b.adjust(*rows)
    return b.as_markup()


# ── Individual wish detail — own wishes ───────────────────────────────────────

def my_wish_kb(
    wish_id: int,
    is_completed: bool,
    visibility: str,  # 'private' | 'shared'
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Изменить",  callback_data=WishActionCD(action="edit",     wish_id=wish_id))
    b.button(text="📅 Срок",      callback_data=WishActionCD(action="deadline", wish_id=wish_id))

    complete_label = "↩️ Не выполнено" if is_completed else "✅ Выполнено"
    b.button(text=complete_label, callback_data=WishActionCD(action="complete", wish_id=wish_id))
    b.button(text="🗑 Удалить",   callback_data=WishActionCD(action="delete",   wish_id=wish_id))

    vis_label = "👁 Показать партнёру" if visibility == "private" else "🙈 Скрыть от партнёра"
    b.button(text=vis_label, callback_data=WishActionCD(action="hidden", wish_id=wish_id))

    b.button(text="← К списку", callback_data="my_wishes_list")
    b.button(text="🏠 Меню",    callback_data="go_menu")
    b.adjust(2, 2, 1, 2)
    return b.as_markup()


def edit_deadline_kb(wish_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for value, label in DEADLINE_OPTIONS:
        b.button(text=label, callback_data=EditDeadlineCD(value=value, wish_id=wish_id))
    b.button(text="← Назад", callback_data=WishActionCD(action="back", wish_id=wish_id))
    b.button(text="🏠 Меню",  callback_data="go_menu")
    b.adjust(2, 2, 2, 2)
    return b.as_markup()


def delete_confirm_kb(wish_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=WishActionCD(action="delete_confirm", wish_id=wish_id))
    b.button(text="← Назад",       callback_data=WishActionCD(action="back",           wish_id=wish_id))
    b.adjust(2)
    return b.as_markup()


# ── Individual wish detail — partner's wish (read-only) ───────────────────────

def partner_wish_detail_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="← К списку", callback_data="partner_wishes_list")
    b.button(text="🏠 Меню",    callback_data="go_menu")
    b.adjust(2)
    return b.as_markup()
