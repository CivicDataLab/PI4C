import hashlib
import hmac

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import InteractionLog


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


def reporter_hash(user_id: str) -> str:
    secret = get_settings().reporter_hash_secret.encode()
    return hmac.new(secret, user_id.encode(), hashlib.sha256).hexdigest()[:32]
