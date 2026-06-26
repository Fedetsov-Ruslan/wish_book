from datetime import datetime, timezone
from typing import List

from src.schemas.wish import Wish

DEADLINE_LABELS: dict[str, str] = {
    "today":     "Сегодня",
    "week":      "На неделе",
    "month":     "В течении месяца",
    "half_year": "В течении полугода",
    "year":      "В течении года",
    "someday":   "Как нибудь",
}

# Display order for groups (most urgent first)
DEADLINE_ORDER: list[str] = ["today", "week", "month", "half_year", "year", "someday"]

GROUP_ICONS: dict[str, str] = {
    "today":     "⚡",
    "week":      "📅",
    "month":     "📆",
    "half_year": "🗓",
    "year":      "📅",
    "someday":   "🌟",
}

_MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек"]


def deadline_label(key: str) -> str:
    return DEADLINE_LABELS.get(key, key)


def _fmt_date(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS_RU[dt.month - 1]} {dt.year}"


# ── Individual wish card (detail view) ───────────────────────────────────────

def wish_card(wish: Wish, index: int, total: int, mine: bool = True) -> str:
    if wish.is_completed:
        status = "✅ Выполнено"
    elif wish.is_expired:
        status = "⌛ Просрочено"
    else:
        status = "🔵 Активно"

    text = f"<b>{index} / {total}</b>  {status}\n\n"
    text += f"💭 <b>{wish.title}</b>\n"
    text += f"📅 {deadline_label(wish.deadline)}"

    if wish.deadline_date:
        text += f"  <i>· до {_fmt_date(wish.deadline_date)}</i>"

    text += "\n"

    if mine:
        vis = "👤 Личное" if wish.visibility == "private" else "💑 Общее"
        text += f"👁 {vis}"

    return text


# ── Grouped wish list (overview) ─────────────────────────────────────────────

def wish_status_icon(wish: Wish) -> str:
    if wish.is_completed:
        return "✅"
    if wish.is_expired:
        return "⌛"
    return "🔵"


def grouped_wish_display(
    wishes: List[Wish],
    mine: bool = True,
) -> tuple[str, List[Wish]]:
    """
    Build the grouped list text and return the wishes in display order
    (so the caller can build a matching inline keyboard).

    Returns: (message_text, ordered_wishes)
    """
    if not wishes:
        header = "📋 Ваши желания" if mine else "💝 Желания партнёра"
        return f"{header}\n\n📭 Пока нет желаний.", []

    # Split into groups
    groups: dict[str, list[Wish]] = {k: [] for k in DEADLINE_ORDER}
    completed: list[Wish] = []

    for wish in wishes:
        if wish.is_completed:
            completed.append(wish)
        else:
            groups.setdefault(wish.deadline, []).append(wish)

    # Sort active wishes within each group by deadline_date (soonest first)
    for key in DEADLINE_ORDER:
        groups[key].sort(
            key=lambda w: w.deadline_date or datetime.max.replace(tzinfo=timezone.utc)
        )

    header = "📋 Ваши желания" if mine else "💝 Желания партнёра"
    total = len(wishes)
    lines: list[str] = [f"{header} ({total})\n"]

    ordered: list[Wish] = []

    for key in DEADLINE_ORDER:
        group = groups[key]
        if not group:
            continue
        icon = GROUP_ICONS[key]
        label = DEADLINE_LABELS[key]
        lines.append(f"{icon} <b>{label}</b> ({len(group)})")
        for wish in group:
            status = wish_status_icon(wish)
            lines.append(f"  {status} {wish.title}")
            ordered.append(wish)

    if completed:
        lines.append(f"\n✅ <b>Выполненные</b> ({len(completed)})")
        for wish in completed:
            lines.append(f"  ✅ {wish.title}")
            ordered.append(wish)

    return "\n".join(lines), ordered


# ── Confirmation text (add wish wizard) ──────────────────────────────────────

def wish_confirmation(title: str, deadline: str, visibility: str, partner_name: str) -> str:
    vis = "👤 Только для себя" if visibility == "private" else f"💑 Для {partner_name}"
    return (
        "📝 <b>Подтверждение:</b>\n\n"
        f"💭 <b>Желание:</b> {title}\n"
        f"📅 <b>Срок:</b> {deadline_label(deadline)}\n"
        f"👁 <b>Видимость:</b> {vis}\n\n"
        "Всё верно?"
    )
