import logging

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from src.config import config
from src.repositories.user_repo import UserRepository
from src.schemas.api import MeResponse, PairRequest, PartnerInfo, RegisterRequest
from src.webapp.auth import get_tg_id
from src.webapp.deps import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["users"])


@router.get("/meta/config")
async def meta_config(request: Request) -> dict:
    """Public, unauthenticated — the frontend needs this before it has any initData."""
    return {"bot_username": request.app.state.bot_username, "webapp_url": config.WEBAPP_URL}


async def _me_response(user_repo: UserRepository, tg_id: int) -> MeResponse:
    user = await user_repo.get_by_tg_id(tg_id)
    if not user:
        return MeResponse(registered=False)

    partner = None
    if user.partner_tg_id:
        partner_user = await user_repo.get_by_tg_id(user.partner_tg_id)
        if partner_user:
            partner = PartnerInfo(tg_id=partner_user.tg_id, name=partner_user.name)

    return MeResponse(registered=True, name=user.name, partner=partner)


async def _link_partners(user_repo: UserRepository, tg_id: int, partner_tg_id: int) -> None:
    """Bidirectionally set partner_tg_id on both sides."""
    await user_repo.update_partner(tg_id, partner_tg_id)
    await user_repo.update_partner(partner_tg_id, tg_id)


@router.get("/me", response_model=MeResponse)
async def get_me(
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> MeResponse:
    return await _me_response(UserRepository(db), tg_id)


@router.post("/register", response_model=MeResponse)
async def register(
    body: RegisterRequest,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> MeResponse:
    user_repo = UserRepository(db)

    if await user_repo.get_by_tg_id(tg_id):
        raise HTTPException(status_code=409, detail="Already registered")

    invited_by = body.invited_by if body.invited_by != tg_id else None
    inviter = await user_repo.get_by_tg_id(invited_by) if invited_by else None

    await user_repo.create(
        tg_id=tg_id,
        name=body.name,
        partner_tg_id=inviter.tg_id if inviter else None,
    )
    if inviter:
        # The inviter's own row already points at their own invite link's
        # owner (themself), not at us yet — link their side back.
        await user_repo.update_partner(inviter.tg_id, tg_id)

    return await _me_response(user_repo, tg_id)


@router.post("/pair", response_model=MeResponse)
async def pair(
    body: PairRequest,
    tg_id: int = Depends(get_tg_id),
    db: asyncpg.Connection = Depends(get_db),
) -> MeResponse:
    if body.partner_tg_id == tg_id:
        raise HTTPException(status_code=400, detail="Cannot pair with yourself")

    user_repo = UserRepository(db)
    if not await user_repo.get_by_tg_id(tg_id):
        raise HTTPException(status_code=404, detail="Register first")

    partner = await user_repo.get_by_tg_id(body.partner_tg_id)
    if not partner:
        raise HTTPException(
            status_code=404,
            detail="Partner hasn't opened the app yet — ask them to open it first",
        )

    await _link_partners(user_repo, tg_id, body.partner_tg_id)
    return await _me_response(user_repo, tg_id)
