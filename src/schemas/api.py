from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.schemas.wish import Wish

Visibility = Literal["private", "shared"]

# (value, label) — same set the old inline keyboards offered; also doubles as
# the allowed set of `deadline` values.
DEADLINE_OPTIONS: list[tuple[str, str]] = [
    ("today", "Сегодня"),
    ("week", "На неделе"),
    ("month", "В течении месяца"),
    ("half_year", "В течении полугода"),
    ("year", "В течении года"),
    ("someday", "Как нибудь"),
]
DEADLINE_LABELS: dict[str, str] = dict(DEADLINE_OPTIONS)
DEADLINE_VALUES: set[str] = {value for value, _ in DEADLINE_OPTIONS}


class PartnerInfo(BaseModel):
    tg_id: int
    name: str


class MeResponse(BaseModel):
    registered: bool
    name: Optional[str] = None
    partner: Optional[PartnerInfo] = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    invited_by: Optional[int] = None


class PairRequest(BaseModel):
    partner_tg_id: int


class WishCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    deadline: str
    visibility: Visibility


class WishUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    deadline: Optional[str] = None


class WishResponse(BaseModel):
    id: int
    title: str
    deadline: str
    deadline_label: str
    deadline_date: Optional[str] = None
    visibility: Visibility
    is_completed: bool
    is_expired: bool
    created_at: str
    attachment_url: Optional[str] = None

    @classmethod
    def from_wish(cls, wish: Wish) -> "WishResponse":
        return cls(
            id=wish.id,
            title=wish.title,
            deadline=wish.deadline,
            deadline_label=DEADLINE_LABELS.get(wish.deadline, wish.deadline),
            deadline_date=wish.deadline_date.isoformat() if wish.deadline_date else None,
            visibility=wish.visibility,  # type: ignore[arg-type]
            is_completed=wish.is_completed,
            is_expired=wish.is_expired,
            created_at=wish.created_at,
            # Our own proxy URL, never the raw MinIO object key.
            attachment_url=f"/api/wishes/{wish.id}/attachment" if wish.attachment_key else None,
        )


class DeadlineOption(BaseModel):
    value: str
    label: str
