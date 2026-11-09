from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'pi4c.db').as_posix()}"
    data_dir: Path = BASE_DIR / "data"
    media_dir: Path = BASE_DIR / "data" / "media"

    # Capture outbound messages instead of calling Telegram. Set only by the tests (tests/conftest.py);
    # deliberately not in .env.example, since a server with it on would never reply to residents.
    dry_run: bool = False

    # Telegram (active channel)
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Read API: "name:scope:key,..."
    api_keys: str = ""

    session_timeout_min: int = 30

    # Place search for typed place names (public OpenStreetMap Nominatim)
    place_search_timeout_s: float = 8.0

    # Clustering: join the nearest open cluster within radius; within strict radius it's a confident match
    cluster_radius_m: float = 50.0
    cluster_strict_radius_m: float = 20.0
    cluster_window_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
