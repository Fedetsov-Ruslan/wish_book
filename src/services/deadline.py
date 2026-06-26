from datetime import datetime, timedelta, timezone

# How long each deadline label stays "active"
DEADLINE_DELTAS: dict[str, timedelta] = {
    "today":     timedelta(days=1),
    "week":      timedelta(weeks=1),
    "month":     timedelta(days=30),
    "half_year": timedelta(days=183),
    "year":      timedelta(days=365),
    "someday":   timedelta(days=365),   # treated the same as "year"
}


def compute_deadline_date(deadline: str) -> datetime:
    """Return the UTC datetime when a wish with the given deadline label expires."""
    delta = DEADLINE_DELTAS.get(deadline, timedelta(days=365))
    return datetime.now(timezone.utc) + delta
