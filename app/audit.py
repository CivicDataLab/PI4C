import hashlib
import hmac
import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AppSecret, InteractionLog

REPORTER_HASH_SECRET = "reporter_hash"


def log_event(
    db: Session,
    interaction_id: str,
    stage: str,
    direction: str = "system",
    payload: dict | None = None,
    report_id: int | None = None,
) -> None:
    db.add(
        InteractionLog(
            interaction_id=interaction_id,
            stage=stage,
            direction=direction,
            payload=payload,
            report_id=report_id,
        )
    )


def reporter_hash(db: Session, user_id: str) -> str:
    """Pseudonymous reporter ID: the same resident always gets the same value, and it can't be
    turned back into the chat ID without the secret, which is generated once and kept in the database."""
    secret = _get_or_create_secret(db, REPORTER_HASH_SECRET).encode()
    return hmac.new(secret, user_id.encode(), hashlib.sha256).hexdigest()[:32]


def ensure_secrets(db: Session) -> None:
    """Create the app's secrets on first start, so they exist before any report is written.
    Two processes starting together (poll + API) may race; the loser just reads the winner's value."""
    try:
        _get_or_create_secret(db, REPORTER_HASH_SECRET)
        db.commit()
    except IntegrityError:
        db.rollback()


def _get_or_create_secret(db: Session, name: str) -> str:
    row = db.get(AppSecret, name)
    if row is None:
        row = AppSecret(name=name, value=secrets.token_urlsafe(32))
        db.add(row)
        db.flush()
    return row.value
