"""Test setup: every test runs against a freshly seeded PostgreSQL test database."""

from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings

if not settings.test_database_url:
    raise RuntimeError("Set TEST_DATABASE_URL in backend/.env to run the tests")
if settings.test_database_url == settings.database_url:
    raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL (tests wipe it)")

settings.database_url = settings.test_database_url
settings.run_scheduler = False
settings.seed_demo_data = False
settings.bcrypt_rounds = 4

from sqlalchemy import text  # noqa: E402

from app import clock  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
TABLES = ", ".join(t.name for t in Base.metadata.sorted_tables)


@pytest.fixture(autouse=True)
def fresh_db() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        seed(db)
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def staff(client: TestClient) -> dict[str, str]:
    return _login(client, "librarian@library.com", "librarian123")


@pytest.fixture
def admin(client: TestClient) -> dict[str, str]:
    return _login(client, "admin@library.com", "admin123")


@pytest.fixture
def login(client: TestClient) -> Callable[[str, str], dict[str, str]]:
    return lambda email, password="member123": _login(client, email, password)


@pytest.fixture
def travel(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], date]:
    """Move the library clock `days` into the future."""

    def go(days: int) -> date:
        target = date.today() + timedelta(days=days)
        monkeypatch.setattr(clock, "today", lambda: target)
        monkeypatch.setattr(
            clock, "now", lambda: datetime.combine(target, time(12), tzinfo=timezone.utc)
        )
        return target

    return go
