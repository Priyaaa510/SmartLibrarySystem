"""Single source of "now" so business rules (due dates, fines, hold expiry) are testable."""

from datetime import date, datetime, timezone


def today() -> date:
    return date.today()


def now() -> datetime:
    return datetime.now(timezone.utc)
