"""
Verification of Telegram Mini App ``initData``.

The frontend sends ``Authorization: tma <initData>`` on every request.
``initData`` is signed by Telegram (HMAC-SHA256 keyed by the bot token) and
must be re-verified on every request — it is the *only* source of truth for
"who is calling", never a client-supplied tg_id field. Accepting a raw tg_id
from the client would let anyone impersonate anyone by sending a different
number.

Signature parsing/checking itself is delegated to aiogram's own
``safe_parse_webapp_init_data`` (it implements exactly the algorithm Telegram
documents); this module only adds the FastAPI wiring and a freshness check
that aiogram's helper doesn't do on its own.
"""

import logging
from datetime import datetime, timezone

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException

from src.config import config

logger = logging.getLogger(__name__)

_AUTH_SCHEME = "tma"
_MAX_INIT_DATA_AGE = 24 * 3600  # reject initData older than this (replay window)


def _parse_authorization(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, init_data = authorization.partition(" ")
    if scheme.lower() != _AUTH_SCHEME or not init_data:
        raise HTTPException(status_code=401, detail="Expected 'Authorization: tma <initData>'")
    return init_data


def verify_init_data(authorization: str | None = Header(default=None)) -> WebAppInitData:
    """FastAPI dependency: verify signature + freshness, return the parsed initData."""
    init_data = _parse_authorization(authorization)

    try:
        data = safe_parse_webapp_init_data(config.BOT_TOKEN, init_data)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    age = datetime.now(timezone.utc) - data.auth_date.replace(tzinfo=timezone.utc)
    if age.total_seconds() > _MAX_INIT_DATA_AGE:
        raise HTTPException(status_code=401, detail="initData expired, reopen the app")

    if data.user is None:
        raise HTTPException(status_code=401, detail="initData has no user")

    return data


def get_tg_id(data: WebAppInitData = Depends(verify_init_data)) -> int:
    """FastAPI dependency: the verified tg_id of the caller."""
    return data.user.id  # type: ignore[union-attr]  # verify_init_data guarantees user is set


def get_start_param(data: WebAppInitData = Depends(verify_init_data)) -> str | None:
    """FastAPI dependency: the inviter's tg_id from a `?startapp=` deep link, if present."""
    return data.start_param
