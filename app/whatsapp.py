"""WhatsApp Cloud API adapter (not the active channel yet; Telegram is).

Payload shapes follow https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import hashlib
import hmac
import logging
import mimetypes
from pathlib import Path

import httpx

from app.config import Settings
from app.messenger import Incoming, options_from, record

log = logging.getLogger(__name__)

# Cloud API limits (the Telugu strings are kept within these; see tests/test_units.py)
BUTTON_TITLE_MAX = 20
LIST_BUTTON_MAX = 20
ROW_TITLE_MAX = 24
ROW_DESC_MAX = 72
SECTION_TITLE_MAX = 24
BODY_MAX = 1024


def parse_webhook(body: dict) -> list[Incoming]:
    """Extract user messages; delivery/read status callbacks are ignored."""
    out = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                out.append(_parse_message(m, names.get(m.get("from"))))
    return out


def _parse_message(m: dict, profile_name: str | None) -> Incoming:
    kind = m.get("type")
    msg = Incoming(
        key=f"wa:{m['id']}", user_id=f"wa:{m['from']}", channel="whatsapp", type="unsupported",
        profile_name=profile_name, raw=m,
    )
    if kind == "text":
        msg.type = "text"
        msg.text = m.get("text", {}).get("body", "").strip()
    elif kind == "interactive":
        inter = m.get("interactive", {})
        reply = inter.get("button_reply") or inter.get("list_reply")
        if reply:
            msg.type = "reply"
            msg.reply_id = reply.get("id")
            msg.reply_title = reply.get("title")
    elif kind == "button":  # quick-reply on a template message
        msg.type = "reply"
        msg.reply_id = m.get("button", {}).get("payload")
        msg.reply_title = m.get("button", {}).get("text")
    elif kind == "location":
        loc = m.get("location", {})
        msg.type = "location"
        msg.latitude = float(loc["latitude"])
        msg.longitude = float(loc["longitude"])
        msg.location_name = loc.get("name")
        msg.location_address = loc.get("address")
    elif kind == "image":
        media = m.get(kind, {})
        msg.type = kind
        msg.media_id = media.get("id")
        msg.mime_type = media.get("mime_type")
        msg.caption = (media.get("caption") or "").strip() or None
    return msg


def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class WhatsAppClient:
    channel = "whatsapp"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base = f"https://graph.facebook.com/{settings.wa_graph_version}"

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.settings.wa_access_token}"}

    def _send(self, user_id: str, kind: str, body: str, options: list[dict], payload: dict) -> None:
        full = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": user_id.removeprefix("wa:"), **payload}
        if self.settings.dry_run:
            record(self.channel, user_id, kind, body, options, full)
            return
        r = httpx.post(
            f"{self.base}/{self.settings.wa_phone_number_id}/messages", json=full, headers=self._auth, timeout=15
        )
        if r.is_error:
            log.error("WhatsApp send failed %s: %s", r.status_code, r.text)
        r.raise_for_status()

    def send_text(self, user_id: str, body: str) -> None:
        self._send(user_id, "text", body, [], {"type": "text", "text": {"body": _clip(body, 4096), "preview_url": False}})

    def send_buttons(self, user_id: str, body: str, buttons: list[tuple[str, str]]) -> None:
        if not 1 <= len(buttons) <= 3:
            raise ValueError("WhatsApp reply buttons: 1–3 allowed")
        action = {
            "buttons": [
                {"type": "reply", "reply": {"id": bid, "title": _clip(title, BUTTON_TITLE_MAX)}} for bid, title in buttons
            ]
        }
        payload = {"type": "interactive", "interactive": {"type": "button", "body": {"text": _clip(body, BODY_MAX)}, "action": action}}
        self._send(user_id, "buttons", body, options_from(buttons), payload)

    def send_list(
        self, user_id: str, body: str, button: str, section_title: str, rows: list[tuple[str, str, str]]
    ) -> None:
        if not 1 <= len(rows) <= 10:
            raise ValueError("WhatsApp list: 1–10 rows allowed")
        section = {
            "title": _clip(section_title, SECTION_TITLE_MAX),
            "rows": [
                {"id": rid, "title": _clip(title, ROW_TITLE_MAX), **({"description": _clip(desc, ROW_DESC_MAX)} if desc else {})}
                for rid, title, desc in rows
            ],
        }
        action = {"button": _clip(button, LIST_BUTTON_MAX), "sections": [section]}
        payload = {"type": "interactive", "interactive": {"type": "list", "body": {"text": _clip(body, BODY_MAX)}, "action": action}}
        self._send(user_id, "list", body, options_from(rows), payload)

    def send_location_request(
        self, user_id: str, body: str, current_label: str, choose_label: str, type_label: str
    ) -> None:
        """WhatsApp draws its own 'Send location' button, whose picker offers both current location
        and a dropped pin, so the labels are unused; residents can still type a place name."""
        payload = {
            "type": "interactive",
            "interactive": {"type": "location_request_message", "body": {"text": _clip(body, BODY_MAX)}, "action": {"name": "send_location"}},
        }
        self._send(user_id, "location_request", body, [], payload)

    def acknowledge(self, msg: Incoming) -> None:
        pass

    def download_media(self, media_id: str, dest_dir: Path) -> Path | None:
        if self.settings.dry_run:
            return None
        meta = httpx.get(f"{self.base}/{media_id}", headers=self._auth, timeout=15)
        meta.raise_for_status()
        info = meta.json()
        content = httpx.get(info["url"], headers=self._auth, timeout=60)
        content.raise_for_status()
        mime = (info.get("mime_type") or "").split(";")[0].strip()
        ext = mimetypes.guess_extension(mime) or ".bin"
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{media_id}{ext}"
        path.write_bytes(content.content)
        return path
