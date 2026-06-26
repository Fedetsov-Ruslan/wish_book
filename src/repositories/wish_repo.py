from datetime import datetime
from typing import List, Optional

import asyncpg

from src.schemas.wish import Wish
from src.services.crypto import decrypt, encrypt


def _row_to_wish(row: asyncpg.Record) -> Wish:
    return Wish(
        id=row["id"],
        user_id=row["user_id"],
        title=decrypt(row["title"]),  # decrypt on every read
        deadline=row["deadline"],
        deadline_date=row["deadline_date"],  # datetime | None (asyncpg returns native datetime)
        visibility=row["visibility"],
        is_completed=row["is_completed"],
        is_hidden=row["is_hidden"],
        created_at=str(row["created_at"]),
    )


_SELECT = (
    "SELECT id, user_id, title, deadline, deadline_date, "
    "visibility, is_completed, is_hidden, created_at "
    "FROM wishes"
)


class WishRepository:
    def __init__(self, db: asyncpg.Connection) -> None:
        self.db = db

    async def create(
        self,
        user_id: int,
        title: str,
        deadline: str,
        deadline_date: Optional[datetime],
        visibility: str,
    ) -> Wish:
        wish_id = await self.db.fetchval(
            "INSERT INTO wishes (user_id, title, deadline, deadline_date, visibility) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            user_id,
            encrypt(title),  # encrypt on write
            deadline,
            deadline_date,
            visibility,
        )
        wish = await self.get_by_id(wish_id)
        assert wish is not None
        return wish

    async def get_by_id(self, wish_id: int) -> Optional[Wish]:
        row = await self.db.fetchrow(f"{_SELECT} WHERE id = $1", wish_id)
        return _row_to_wish(row) if row else None

    async def get_my_wishes(self, user_id: int) -> List[Wish]:
        rows = await self.db.fetch(
            f"{_SELECT} WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
        return [_row_to_wish(r) for r in rows]

    async def get_partner_wishes(self, partner_user_id: int) -> List[Wish]:
        """Active shared visible wishes: not completed, not hidden, not expired."""
        rows = await self.db.fetch(
            f"{_SELECT} "
            "WHERE user_id = $1 "
            "  AND visibility    = 'shared' "
            "  AND is_hidden     = FALSE "
            "  AND is_completed  = FALSE "
            "  AND (deadline_date IS NULL OR deadline_date > NOW()) "
            "ORDER BY deadline_date ASC NULLS LAST",
            partner_user_id,
        )
        return [_row_to_wish(r) for r in rows]

    async def update_title(self, wish_id: int, title: str) -> None:
        await self.db.execute(
            "UPDATE wishes SET title = $1 WHERE id = $2", encrypt(title), wish_id
        )

    async def update_visibility(self, wish_id: int, visibility: str) -> None:
        await self.db.execute(
            "UPDATE wishes SET visibility = $1 WHERE id = $2", visibility, wish_id
        )

    async def update_deadline(self, wish_id: int, deadline: str, deadline_date: datetime) -> None:
        await self.db.execute(
            "UPDATE wishes SET deadline = $1, deadline_date = $2 WHERE id = $3",
            deadline,
            deadline_date,
            wish_id,
        )

    async def toggle_completed(self, wish_id: int) -> None:
        await self.db.execute(
            "UPDATE wishes SET is_completed = NOT is_completed WHERE id = $1", wish_id
        )

    async def toggle_hidden(self, wish_id: int) -> None:
        await self.db.execute(
            "UPDATE wishes SET is_hidden = NOT is_hidden WHERE id = $1", wish_id
        )

    async def delete(self, wish_id: int) -> None:
        await self.db.execute("DELETE FROM wishes WHERE id = $1", wish_id)
