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
        attachment_key=row["attachment_key"],
    )


_SELECT = (
    "SELECT id, user_id, title, deadline, deadline_date, "
    "visibility, is_completed, is_hidden, created_at, attachment_key "
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

    async def get_owned(self, wish_id: int, user_id: int) -> Optional[Wish]:
        """Like get_by_id, but only returns the row if it belongs to user_id.

        Use this (never get_by_id) when the caller is a specific user acting
        on a wish_id that came from client input (callback_data) — wish_id is
        a sequential int and callback_data is not authenticated, so every
        read/write reachable from a handler must be scoped to the acting
        user's own rows.
        """
        row = await self.db.fetchrow(
            f"{_SELECT} WHERE id = $1 AND user_id = $2", wish_id, user_id
        )
        return _row_to_wish(row) if row else None

    async def get_my_wishes(self, user_id: int) -> List[Wish]:
        rows = await self.db.fetch(
            f"{_SELECT} WHERE user_id = $1 ORDER BY is_completed ASC, created_at DESC",
            user_id,
        )
        return [_row_to_wish(r) for r in rows]

    async def get_visible_to_partner(self, wish_id: int, partner_user_id: int) -> Optional[Wish]:
        """Single-row version of get_partner_wishes's predicate.

        Used to authorize attachment downloads for a partner without
        fetching+scanning the whole list for one id.
        """
        row = await self.db.fetchrow(
            f"{_SELECT} "
            "WHERE id = $1 "
            "  AND user_id = $2 "
            "  AND visibility    = 'shared' "
            "  AND is_hidden     = FALSE "
            "  AND is_completed  = FALSE "
            "  AND (deadline_date IS NULL OR deadline_date > NOW())",
            wish_id,
            partner_user_id,
        )
        return _row_to_wish(row) if row else None

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

    # All mutating methods below take `user_id` and scope the query to it
    # (WHERE id = $1 AND user_id = $2 ... RETURNING id). They return True
    # only if a row actually matched — i.e. the wish exists AND belongs to
    # that user. wish_id alone is never sufficient to authorize a write.

    async def update_title(self, wish_id: int, user_id: int, title: str) -> bool:
        result = await self.db.fetchval(
            "UPDATE wishes SET title = $1 WHERE id = $2 AND user_id = $3 RETURNING id",
            encrypt(title),
            wish_id,
            user_id,
        )
        return result is not None

    async def update_visibility(self, wish_id: int, user_id: int, visibility: str) -> bool:
        result = await self.db.fetchval(
            "UPDATE wishes SET visibility = $1 WHERE id = $2 AND user_id = $3 RETURNING id",
            visibility,
            wish_id,
            user_id,
        )
        return result is not None

    async def update_deadline(
        self, wish_id: int, user_id: int, deadline: str, deadline_date: datetime
    ) -> bool:
        result = await self.db.fetchval(
            "UPDATE wishes SET deadline = $1, deadline_date = $2 "
            "WHERE id = $3 AND user_id = $4 RETURNING id",
            deadline,
            deadline_date,
            wish_id,
            user_id,
        )
        return result is not None

    async def toggle_completed(self, wish_id: int, user_id: int) -> bool:
        result = await self.db.fetchval(
            "UPDATE wishes SET is_completed = NOT is_completed "
            "WHERE id = $1 AND user_id = $2 RETURNING id",
            wish_id,
            user_id,
        )
        return result is not None

    async def toggle_hidden(self, wish_id: int, user_id: int) -> bool:
        result = await self.db.fetchval(
            "UPDATE wishes SET is_hidden = NOT is_hidden "
            "WHERE id = $1 AND user_id = $2 RETURNING id",
            wish_id,
            user_id,
        )
        return result is not None

    async def set_attachment(self, wish_id: int, user_id: int, key: Optional[str]) -> bool:
        result = await self.db.fetchval(
            "UPDATE wishes SET attachment_key = $1 WHERE id = $2 AND user_id = $3 RETURNING id",
            key,
            wish_id,
            user_id,
        )
        return result is not None

    async def delete(self, wish_id: int, user_id: int) -> tuple[bool, Optional[str]]:
        """Returns (deleted, attachment_key).

        Uses fetchrow (not fetchval) deliberately: a deleted wish with no
        attachment has attachment_key IS NULL, which is just as falsy as "no
        row matched" — fetchval alone can't tell those two cases apart, so
        the caller needs the explicit (bool, key) pair to know whether to
        clean up a MinIO object.
        """
        row = await self.db.fetchrow(
            "DELETE FROM wishes WHERE id = $1 AND user_id = $2 RETURNING attachment_key",
            wish_id,
            user_id,
        )
        if row is None:
            return False, None
        return True, row["attachment_key"]
