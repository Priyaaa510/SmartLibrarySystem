from decimal import Decimal
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/smart_library"
    test_database_url: str | None = None
    secret_key: str = "change-me"
    access_token_minutes: int = 60 * 12
    bcrypt_rounds: int = 12
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Library policy defaults (per-tier rules live in the membership_types table)
    hold_pickup_days: int = 3
    due_soon_days: int = 2
    default_fine_per_day: Decimal = Decimal("5")
    lost_book_default_price: Decimal = Decimal("500")
    lost_book_processing_fee: Decimal = Decimal("50")

    seed_demo_data: bool = True
    run_scheduler: bool = True
    scheduler_interval_minutes: int = 60


settings = Settings()
