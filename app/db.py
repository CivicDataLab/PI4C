from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# SQLite only for now. DATABASE_URL may point at another SQLite file (the tests do this).
if not settings.database_url.startswith("sqlite"):
    raise RuntimeError("DATABASE_URL must be a sqlite:/// URL; only SQLite is supported for now")
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401  registers tables

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    from app.audit import ensure_secrets

    with SessionLocal() as db:
        ensure_secrets(db)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
