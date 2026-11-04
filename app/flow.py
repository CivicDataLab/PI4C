"""Conversation state machine for the reporting flow (channel-neutral; Telegram today).

LANGUAGE → MENU → LOCATION → SUBCATEGORY → DESCRIBE → PHOTO → AFFECTED → READBACK → DONE

READBACK can branch to EDIT, which jumps to one step and then returns straight to READBACK.
Every prompt with options also accepts the option's number ("1", "2"...) or exact title typed
as text, for residents who find tapping buttons hard.
"""

import logging
import uuid
from datetime import timedelta
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, geo, i18n, pipeline, taxonomy
from app.config import Settings
from app.models import ChatSession, Media, MediaFile, Report, utcnow
from app.messenger import Incoming, Messenger

log = logging.getLogger(__name__)


class State(StrEnum):
    START = "START"
    LANGUAGE = "LANGUAGE"
    MENU = "MENU"
    SUBCATEGORY = "SUBCATEGORY"
    DESCRIBE = "DESCRIBE"
    LOCATION = "LOCATION"
    PHOTO = "PHOTO"
    AFFECTED = "AFFECTED"
    READBACK = "READBACK"
    EDIT = "EDIT"
    DONE = "DONE"


RESET_WORDS = {"hi", "hello", "menu", "start", "restart", "/start", "/menu", "నమస్కారం", "మెనూ", "హాయ్"}
CANCEL_WORDS = {"cancel", "stop", "/cancel", "రద్దు"}
LANGUAGE_WORDS = {"/language", "language", "భాష"}
MAX_PHOTOS = 3

EDIT_TARGETS = {
    "category": State.MENU,
    "description": State.DESCRIBE,
    "location": State.LOCATION,
    "photo": State.PHOTO,
    "affected": State.AFFECTED,
}


class Conversation:
    def __init__(self, db: Session, messenger: Messenger, settings: Settings):
        self.db = db
        self.messenger = messenger
        self.settings = settings
        self.M = i18n.messages(None)

    def handle(self, msg: Incoming) -> None:
        s = self._session(msg.user_id)
        audit.log_event(self.db, s.interaction_id, f"inbound:{s.state}", "in", _summarise(msg))
        word = (msg.text or "").strip().casefold() if msg.type == "text" else ""
        self.M = i18n.messages(s.language)

        if s.state not in (State.START, State.DONE) and self._expired(s):
            audit.log_event(self.db, s.interaction_id, "expired")
            self._restart(s, State.MENU if s.language else State.LANGUAGE)
            self._send_text(s, self.M.EXPIRED)
            self._prompt(s)
        elif word in LANGUAGE_WORDS or word == "/start" or (not s.language and s.state != State.LANGUAGE):
            # /start always offers the language choice; so does the very first message
            self._restart(s, State.LANGUAGE)
            self._prompt(s)
        elif s.state in (State.START, State.DONE) or word in RESET_WORDS:
            self._restart(s, State.MENU)
            self._prompt(s)
        elif word in CANCEL_WORDS:
            self._cancel(s)
        else:
            getattr(self, f"_on_{s.state.lower()}")(s, msg)

        s.updated_at = utcnow()
        self.db.commit()

    # --- state handlers -------------------------------------------------------------------

    def _on_language(self, s: ChatSession, msg: Incoming) -> None:
        lang = self._choice(s, msg, "lang")
        if lang not in i18n.MESSAGES:
            return self._prompt(s)
        s.language = lang
        self.M = i18n.messages(lang)
        audit.log_event(self.db, s.interaction_id, "language", payload={"language": lang})
        self._goto(s, State.MENU)

    def _on_menu(self, s: ChatSession, msg: Incoming) -> None:
        cat = self._choice(s, msg, "cat")
        if not taxonomy.category(cat):
            return self._prompt(s, self.M.CHOOSE_FROM_BUTTONS)
        self._set(s, category=cat, subcategory=None)
        # Editing the category only re-asks the sub-category; a new report asks where first
        self._goto(s, State.SUBCATEGORY if s.data.get("editing") else State.LOCATION)

    def _on_subcategory(self, s: ChatSession, msg: Incoming) -> None:
        sub = self._choice(s, msg, "sub")
        if not taxonomy.subcategory(s.data.get("category"), sub):
            return self._prompt(s, self.M.CHOOSE_FROM_BUTTONS)
        self._set(s, subcategory=sub)
        self._next(s, State.DESCRIBE)

    def _on_describe(self, s: ChatSession, msg: Incoming) -> None:
        # Typed text only: voice notes and other files get DESCRIBE_RETRY
        if msg.type == "text" and msg.text:
            self._set(s, description_raw=msg.text, description_type="text")
        elif msg.type == "image":
            self._store_media(s, msg, "image")
            if not msg.caption:
                return self._send_text(s, self.M.PHOTO_SAVED_DESCRIBE)
            self._set(s, description_raw=msg.caption, description_type="text")
        else:
            return self._send_text(s, self.M.DESCRIBE_RETRY)
        # A photo sent with a caption here already covers the photo step
        self._next(s, State.AFFECTED if self._photo_count(s) else State.PHOTO)

    def _on_location(self, s: ChatSession, msg: Incoming) -> None:
        if msg.type != "location":
            if self._choice(s, msg, "loc") == "choose":
                # Bots can't open Telegram's map picker; explain the attach → Location route
                return self._prompt(s, self.M.CHOOSE_ON_MAP)
            self._set(s, location_attempts=s.data.get("location_attempts", 0) + 1)
            return self._prompt(s, self.M.LOCATION_RETRY)
        self._set(
            s,
            latitude=msg.latitude,
            longitude=msg.longitude,
            location_name=msg.location_name,
            location_address=msg.location_address,
        )
        self._send_text(s, self.M.LOCATION_RECEIVED)
        self._next(s, State.SUBCATEGORY)

    def _on_photo(self, s: ChatSession, msg: Incoming) -> None:
        if msg.type == "image":
            if self._photo_count(s) >= MAX_PHOTOS:
                self._replace_media(s, "image")
            self._store_media(s, msg, "image")
        elif self._choice(s, msg, "photo") == "skip":
            if s.data.get("editing"):
                self._replace_media(s, "image")  # "No photo" during edit removes earlier photos
        else:
            return self._prompt(s, self.M.PHOTO_RETRY)
        self._next(s, State.AFFECTED)

    def _on_affected(self, s: ChatSession, msg: Incoming) -> None:
        value = self._choice(s, msg, "aff")
        if value not in dict(self.M.AFFECTED_OPTIONS):
            return self._prompt(s, self.M.CHOOSE_FROM_BUTTONS)
        self._set(s, affected=value)
        self._goto(s, State.READBACK)

    def _on_readback(self, s: ChatSession, msg: Incoming) -> None:
        action = self._choice(s, msg, "rb")
        if action == "confirm":
            self._submit(s)
        elif action == "edit":
            self._goto(s, State.EDIT)
        elif action == "cancel":
            self._cancel(s)
        else:
            self._prompt(s, self.M.CHOOSE_FROM_BUTTONS)

    def _on_edit(self, s: ChatSession, msg: Incoming) -> None:
        target = EDIT_TARGETS.get(self._choice(s, msg, "edit") or "")
        if not target:
            return self._prompt(s, self.M.CHOOSE_FROM_BUTTONS)
        self._set(s, editing=True, edit_count=s.data.get("edit_count", 0) + 1)
        audit.log_event(self.db, s.interaction_id, "edit", payload={"target": target.value})
        self._goto(s, target)

    # --- transitions ----------------------------------------------------------------------

    def _goto(self, s: ChatSession, state: State) -> None:
        s.state = state
        self._prompt(s)

    def _next(self, s: ChatSession, default: State) -> None:
        """Advance to the next step, or back to read-back if this step was an edit."""
        self._goto(s, State.READBACK if s.data.get("editing") else default)

    def _restart(self, s: ChatSession, state: State) -> None:
        s.interaction_id = str(uuid.uuid4())
        s.state = state
        s.data = {}
        audit.log_event(self.db, s.interaction_id, "session_start")

    def _cancel(self, s: ChatSession) -> None:
        audit.log_event(self.db, s.interaction_id, "cancelled", payload={"at": s.state})
        self._send_text(s, self.M.CANCELLED)
        s.state = State.DONE
        s.data = {}

    def _submit(self, s: ChatSession) -> None:
        d = s.data
        affected = d["affected"]
        report = Report(
            interaction_id=s.interaction_id,
            channel=self.messenger.channel,
            language=s.language or i18n.DEFAULT_LANGUAGE,
            category=d["category"],
            subcategory=d["subcategory"],
            barrier_type=d["subcategory"],
            municipal_subject=(taxonomy.subcategory(d["category"], d["subcategory"]) or {}).get("municipal_subject"),
            description_raw=d.get("description_raw"),
            description_type=d.get("description_type", "text"),
            latitude=d["latitude"],
            longitude=d["longitude"],
            location_name=d.get("location_name"),
            location_address=d.get("location_address"),
            location_route="shared_location",
            ward=geo.find_ward(d["latitude"], d["longitude"]),
            affected=affected,
            pwd_marker=affected in ("self", "caregiver") or d["category"] == "accessibility",
            readback_outcome="edited" if d.get("edit_count") else "confirmed",
            edit_count=d.get("edit_count", 0),
            reporter_hash=audit.reporter_hash(s.user_id),
            status="new",
        )
        report.media = [_media_row(m) for m in d.get("media", [])]
        self.db.add(report)
        self.db.flush()
        audit.log_event(self.db, s.interaction_id, "submitted", payload={"ref": report.ref}, report_id=report.id)

        self._send_text(s, self.M.submitted(report.ref))
        s.state = State.DONE
        s.data = {}
        self.db.commit()

        # Acknowledge first; classification and clustering must never block the resident
        pipeline.process_report(self.db, report, self.settings)

    # --- prompts --------------------------------------------------------------------------

    def _prompt(self, s: ChatSession, lead: str | None = None) -> None:
        prefix = f"{lead}\n\n" if lead else ""
        d = s.data
        lang = s.language
        match s.state:
            case State.LANGUAGE:
                self._send_buttons(s, i18n.CHOOSE_LANGUAGE, [(f"lang:{v}", t) for v, t in i18n.LANGUAGE_OPTIONS])
            case State.MENU:
                body = self.M.CHOOSE_CATEGORY if d.get("editing") else self.M.WELCOME
                options = [(f"cat:{c['id']}", i18n.label(c, lang)) for c in taxonomy.categories()]
                self._send_buttons(s, prefix + body, options)
            case State.SUBCATEGORY:
                cat = taxonomy.category(d["category"])
                rows = [(f"sub:{x['id']}", i18n.label(x, lang), i18n.label(x, lang, "description")) for x in cat["subcategories"]]
                self._send_list(s, prefix + self.M.CHOOSE_SUBCATEGORY, i18n.label(cat, lang), rows)
            case State.DESCRIBE:
                self._send_text(s, prefix + self.M.DESCRIBE)
            case State.LOCATION:
                self._send_location_request(s, lead or self.M.LOCATION)
            case State.PHOTO:
                self._send_buttons(s, prefix + self.M.PHOTO, [("photo:skip", self.M.BTN_NO_PHOTO)])
            case State.AFFECTED:
                self._send_buttons(s, prefix + self.M.AFFECTED, [(f"aff:{v}", t) for v, t in self.M.AFFECTED_OPTIONS])
            case State.READBACK:
                options = [("rb:confirm", self.M.BTN_CONFIRM), ("rb:edit", self.M.BTN_EDIT), ("rb:cancel", self.M.BTN_CANCEL)]
                self._send_buttons(s, prefix + self._readback_body(s), options)
            case State.EDIT:
                rows = [(f"edit:{v}", t, "") for v, t in self.M.EDIT_OPTIONS]
                self._send_list(s, prefix + self.M.EDIT, self.M.EDIT_SECTION, rows)

    def _readback_body(self, s: ChatSession) -> str:
        d = s.data
        cat = taxonomy.category(d["category"])
        sub = taxonomy.subcategory(d["category"], d["subcategory"])
        text = d.get("description_raw") or ""
        description = text if len(text) <= 300 else text[:299] + "…"
        location = d.get("location_name") or d.get("location_address") or f"{d['latitude']:.5f}, {d['longitude']:.5f}"
        return self.M.readback(
            category=i18n.label(cat, s.language),
            subcategory=i18n.label(sub, s.language),
            description=description,
            location=location,
            photos=self._photo_count(s),
            affected=dict(self.M.AFFECTED_OPTIONS)[d["affected"]],
        )

    # --- sending (records the options offered so typed numbers can be mapped back) --------

    def _send_text(self, s: ChatSession, body: str) -> None:
        self.messenger.send_text(s.user_id, body)
        self._log_out(s, "text")

    def _send_buttons(self, s: ChatSession, body: str, options: list[tuple[str, str]]) -> None:
        self._set(s, _options=options)
        self.messenger.send_buttons(s.user_id, body, options)
        self._log_out(s, "buttons")

    def _send_list(self, s: ChatSession, body: str, section: str, rows: list[tuple[str, str, str]]) -> None:
        self._set(s, _options=[(rid, title) for rid, title, _ in rows])
        self.messenger.send_list(s.user_id, body, self.M.LIST_BUTTON, section, rows)
        self._log_out(s, "list")

    def _send_location_request(self, s: ChatSession, body: str) -> None:
        # Recorded so a typed "1"/"2" or the "Choose a location" button text maps back to an option
        self._set(s, _options=[("loc:current", self.M.BTN_SEND_LOCATION), ("loc:choose", self.M.BTN_CHOOSE_LOCATION)])
        self.messenger.send_location_request(s.user_id, body, self.M.BTN_SEND_LOCATION, self.M.BTN_CHOOSE_LOCATION)
        self._log_out(s, "location_request")

    def _log_out(self, s: ChatSession, kind: str) -> None:
        audit.log_event(self.db, s.interaction_id, f"prompt:{s.state}", "out", {"kind": kind})

    # --- helpers --------------------------------------------------------------------------

    def _session(self, user_id: str) -> ChatSession:
        s = self.db.scalar(select(ChatSession).where(ChatSession.user_id == user_id))
        if s is None:
            s = ChatSession(user_id=user_id, interaction_id=str(uuid.uuid4()), state=State.START, data={})
            self.db.add(s)
            self.db.flush()
        return s

    def _expired(self, s: ChatSession) -> bool:
        return utcnow() - s.updated_at > timedelta(minutes=self.settings.session_timeout_min)

    def _set(self, s: ChatSession, **values) -> None:
        # Reassign so SQLAlchemy notices the JSON change
        s.data = {**s.data, **values}

    def _choice(self, s: ChatSession, msg: Incoming, prefix: str) -> str | None:
        option_id = None
        if msg.type == "reply":
            option_id = msg.reply_id
        elif msg.type == "text" and msg.text:
            options = s.data.get("_options", [])
            typed = msg.text.strip()
            if typed.isdigit() and 1 <= int(typed) <= len(options):
                option_id = options[int(typed) - 1][0]
            else:
                option_id = next((oid for oid, title in options if title.casefold() == typed.casefold()), None)
        if option_id and option_id.startswith(prefix + ":"):
            return option_id.split(":", 1)[1]
        return None

    def _photo_count(self, s: ChatSession) -> int:
        return sum(1 for m in s.data.get("media", []) if m["kind"] == "image")

    def _replace_media(self, s: ChatSession, kind: str) -> None:
        self._set(s, media=[m for m in s.data.get("media", []) if m["kind"] != kind])

    def _store_media(self, s: ChatSession, msg: Incoming, kind: str) -> None:
        path = None
        try:
            path = self.messenger.download_media(msg.media_id, self.settings.media_dir / s.interaction_id)
        except Exception:
            log.exception("media download failed for %s", msg.media_id)
        item = {
            "kind": kind,
            "file_id": msg.media_id,
            "mime_type": msg.mime_type,
            "path": str(path) if path else None,
            "caption": msg.caption,
        }
        self._set(s, media=[*s.data.get("media", []), item])


def _media_row(item: dict) -> Media:
    """Media record for a submitted report, with the downloaded file's bytes stored in the database.
    Files sit in media_dir only while the conversation is open (they can't go in the session JSON)."""
    media = Media(**item)
    if item.get("path") and Path(item["path"]).is_file():
        media.file = MediaFile.from_bytes(Path(item["path"]).read_bytes())
    return media


def _summarise(msg: Incoming) -> dict:
    """Log payload without the chat/phone ID."""
    out = {"type": msg.type, "key": msg.key}
    for key in ("text", "reply_id", "latitude", "longitude", "media_id", "caption"):
        if getattr(msg, key) is not None:
            out[key] = getattr(msg, key)
    return out
