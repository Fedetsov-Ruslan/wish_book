from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Wish:
    id: int
    user_id: int
    title: str
    deadline: str
    deadline_date: Optional[datetime]   # UTC timestamp when wish becomes inactive
    visibility: str                     # 'private' | 'shared'
    is_completed: bool
    is_hidden: bool
    created_at: str

    @property
    def is_expired(self) -> bool:
        """True when the deadline has passed and the wish is not yet completed."""
        if self.is_completed or self.deadline_date is None:
            return False
        return self.deadline_date < datetime.now(timezone.utc)
