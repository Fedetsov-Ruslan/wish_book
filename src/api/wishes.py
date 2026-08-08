import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from src.repositories.user_repo import UserRepository
from src.repositories.wish_repo import WishRepository
from src.schemas.api import (
    DEADLINE_OPTIONS,
    DEADLINE_VALUES,
    DeadlineOption,
    WishCreateRequest,
    WishResponse,
    WishUpdateRequest,
)
from src.services.deadline import compute_deadline_date
from src.services.scheduler import NotificationScheduler
from src.webapp.auth import get_tg_id
from src.webapp.deps import get_db, get_scheduler

router = APIRouter(prefix="/api", tags=["wishes"])


def _check_deadline(deadline: str) -> None:
    if deadline not in DEADLINE_VALUES:
        raise HTTPException(status_code=422, detail=f"Unknown deadline value: {deadline!r}")


async def _require_user_id(db: asyncpg.Connection, tg_id: int) -> int:
    user = await UserRepository(db).get_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="Register first")
    return user.id


@router.get("/meta/deadline-options", response_model=list[DeadlineOption])
async def deadline_options() -> list[DeadlineOption]:
    return [DeadlineOption(value=value, label=label) for value, label in DEADLINE_OPTIONS]


@router.get("/wishes/mine", response_model=list[WishResponse])
async def list_my_wishes(
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> list[WishResponse]:
    user_id = await _require_user_id(db, tg_id)
    wishes = await WishRepository(db).get_my_wishes(user_id)
    return [WishResponse.from_wish(w) for w in wishes]


@router.get("/wishes/partner", response_model=list[WishResponse])
async def list_partner_wishes(
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> list[WishResponse]:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="Register first")
    if not user.partner_tg_id:
        return []

    partner = await user_repo.get_by_tg_id(user.partner_tg_id)
    if not partner:
        return []

    wishes = await WishRepository(db).get_partner_wishes(partner.id)
    return [WishResponse.from_wish(w) for w in wishes]


@router.post("/wishes", response_model=WishResponse, status_code=201)
async def create_wish(
    body: WishCreateRequest,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
    scheduler: NotificationScheduler = Depends(get_scheduler),
) -> WishResponse:
    _check_deadline(body.deadline)

    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="Register first")

    wish = await WishRepository(db).create(
        user_id=user.id,
        title=body.title,
        deadline=body.deadline,
        deadline_date=compute_deadline_date(body.deadline),
        visibility=body.visibility,
    )

    if body.visibility == "shared" and user.partner_tg_id:
        await scheduler.schedule(
            wish_id=wish.id,
            user_id=user.id,
            partner_tg_id=user.partner_tg_id,
            author_name=user.name,
        )

    return WishResponse.from_wish(wish)


@router.patch("/wishes/{wish_id}", response_model=WishResponse)
async def update_wish(
    wish_id: int,
    body: WishUpdateRequest,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> WishResponse:
    user_id = await _require_user_id(db, tg_id)
    wish_repo = WishRepository(db)

    if body.title is not None:
        if not await wish_repo.update_title(wish_id, user_id, body.title):
            raise HTTPException(status_code=404, detail="Wish not found")

    if body.deadline is not None:
        _check_deadline(body.deadline)
        new_date = compute_deadline_date(body.deadline)
        if not await wish_repo.update_deadline(wish_id, user_id, body.deadline, new_date):
            raise HTTPException(status_code=404, detail="Wish not found")

    wish = await wish_repo.get_owned(wish_id, user_id)
    if not wish:
        raise HTTPException(status_code=404, detail="Wish not found")
    return WishResponse.from_wish(wish)


@router.post("/wishes/{wish_id}/complete", response_model=WishResponse)
async def toggle_complete(
    wish_id: int,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> WishResponse:
    user_id = await _require_user_id(db, tg_id)
    wish_repo = WishRepository(db)

    if not await wish_repo.toggle_completed(wish_id, user_id):
        raise HTTPException(status_code=404, detail="Wish not found")

    wish = await wish_repo.get_owned(wish_id, user_id)
    assert wish is not None
    return WishResponse.from_wish(wish)


@router.post("/wishes/{wish_id}/visibility", response_model=WishResponse)
async def toggle_visibility(
    wish_id: int,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
    scheduler: NotificationScheduler = Depends(get_scheduler),
) -> WishResponse:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="Register first")

    wish_repo = WishRepository(db)
    wish = await wish_repo.get_owned(wish_id, user.id)
    if not wish:
        raise HTTPException(status_code=404, detail="Wish not found")

    new_visibility = "private" if wish.visibility == "shared" else "shared"
    await wish_repo.update_visibility(wish_id, user.id, new_visibility)

    if new_visibility == "shared" and user.partner_tg_id:
        await scheduler.schedule(
            wish_id=wish_id,
            user_id=user.id,
            partner_tg_id=user.partner_tg_id,
            author_name=user.name,
        )
    else:
        await scheduler.cancel(wish_id)

    updated = await wish_repo.get_owned(wish_id, user.id)
    assert updated is not None
    return WishResponse.from_wish(updated)


@router.delete("/wishes/{wish_id}", status_code=204)
async def delete_wish(
    wish_id: int,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
    scheduler: NotificationScheduler = Depends(get_scheduler),
) -> None:
    user_id = await _require_user_id(db, tg_id)
    if not await WishRepository(db).delete(wish_id, user_id):
        raise HTTPException(status_code=404, detail="Wish not found")
    await scheduler.cancel(wish_id)
