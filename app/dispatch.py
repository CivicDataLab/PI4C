"""Hand one inbound message to the conversation flow: dedupe, lock per resident, run."""

import logging
import threading
import time
from collections import defaultdict

from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import SessionLocal
from app.flow import Conversation, sweep_media
from app.messenger import Incoming, Messenger
from app.models import InboundMessage

log = logging.getLogger(__name__)

# One lock per resident so two quick messages can't race on the same session state
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()

SWEEP_EVERY_S = 3600
_last_sweep = 0.0  # 0 → the first message after startup sweeps


def process_incoming(msg: Incoming, messenger: Messenger) -> None:
    messenger.acknowledge(msg)
    with _locks_guard:
        lock = _locks[msg.user_id]
    with lock, SessionLocal() as db:
        try:
            db.add(InboundMessage(key=msg.key))
            db.commit()
        except IntegrityError:
            db.rollback()
            log.info("duplicate delivery %s ignored", msg.key)
            return
        try:
            Conversation(db, messenger, get_settings()).handle(msg)
        except Exception:
            db.rollback()
            log.exception("failed to handle message %s", msg.key)
    _maybe_sweep_media()


def _maybe_sweep_media() -> None:
    """At most hourly, delete photo folders left by conversations that were abandoned."""
    global _last_sweep
    with _locks_guard:
        if _last_sweep and time.monotonic() - _last_sweep < SWEEP_EVERY_S:
            return
        _last_sweep = time.monotonic()
    try:
        with SessionLocal() as db:
            sweep_media(db, get_settings())
    except Exception:
        log.exception("media sweep failed")
