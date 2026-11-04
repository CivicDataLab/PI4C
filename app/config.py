from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'pi4c.db').as_posix()}"
    data_dir: Path = BASE_DIR / "data"
    media_dir: Path = BASE_DIR / "data" / "media"

    # Capture outbound messages instead of calling Telegram/WhatsApp (simulator, tests)
    dry_run: bool = False

    # Telegram (active channel)
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # WhatsApp Cloud API (kept for later)
    wa_phone_number_id: str = ""
    wa_access_token: str = ""
    wa_verify_token: str = "change-me"
    wa_app_secret: str = ""
    wa_graph_version: str = "v23.0"

    # Classifier: OpenRouter Decisions API; rules-only when key or model is blank
    openrouter_api_key: str = ""
    openrouter_model: str = "typesafe/jev-1.14"
    openrouter_timeout_s: float = 30.0
    classify_min_confidence: float = 0.6

    # Read API: "name:scope:key,..."
    api_keys: str = ""
    # Web dashboards on other sites allowed to call the API from the browser: "https://a.example,https://b.example"
    # ("*" = any). Not needed for server-side tools (Power BI, Grafana, Metabase, scripts).
    cors_origins: str = ""
    reporter_hash_secret: str = "change-me"

    session_timeout_min: int = 30

    # Clustering: join the nearest open cluster within radius; within strict radius it's a confident match
    cluster_radius_m: float = 50.0
    cluster_strict_radius_m: float = 20.0
    cluster_window_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
