from typing import Optional

import asyncpg

from src.schemas.user import User


def _row_to_user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        tg_id=row["tg_id"],
        name=row["name"],
        partner_tg_id=row["partner_tg_id"],
        created_at=str(row["created_at"]),
    )


class UserRepository:
    def __init__(self, db: asyncpg.Connection) -> None:
        self.db = db

    async def get_by_tg_id(self, tg_id: int) -> Optional[User]:
        row = await self.db.fetchrow(
            "SELECT id, tg_id, name, partner_tg_id, created_at FROM users WHERE tg_id = $1",
            tg_id,
        )
        return _row_to_user(row) if row else None

    async def create(
        self,
        tg_id: int,
        name: str,
        partner_tg_id: Optional[int] = None,
    ) -> User:
        await self.db.execute(
            "INSERT INTO users (tg_id, name, partner_tg_id) VALUES ($1, $2, $3)",
            tg_id,
            name,
            partner_tg_id,
        )
        user = await self.get_by_tg_id(tg_id)
        assert user is not None
        return user

    async def update_partner(self, tg_id: int, partner_tg_id: int) -> None:
        await self.db.execute(
            "UPDATE users SET partner_tg_id = $1 WHERE tg_id = $2",
            partner_tg_id,
            tg_id,
        )
