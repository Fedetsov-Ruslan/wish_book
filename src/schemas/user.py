from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    tg_id: int
    name: str
    partner_tg_id: Optional[int]
    created_at: str
