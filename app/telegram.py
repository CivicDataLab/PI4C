"""Telegram Bot API adapter: parse updates, send messages, download media.

https://core.telegram.org/bots/api
"""

import logging
from pathlib import Path

import httpx

from app.config import Settings
from app.messenger import Incoming, options_from, record

log = logging.getLogger(__name__)

API = "https://api.telegram.org"
TEXT_MAX = 4096


def parse_update(update: dict) -> Incoming | None:
    """One Incoming per update; None for updates we ignore (edits, groups, channel posts)."""
    key = f"tg:{update.get('update_id')}"

    if cq := update.get("callback_query"):
        chat = (cq.get("message") or {}).get("chat") or cq["from"]
        return Incoming(
            key=key,
            user_id=f"tg:{chat['id']}",
            channel="telegram",
            type="reply",
            reply_id=cq.get("data"),
            callback_id=cq["id"],
            profile_name=cq["from"].get("first_name"),
            raw=update,
        )

    # edited_message carries live-location updates after the first; the first one is enough
    m = update.get("message")
    if not m or m.get("chat", {}).get("type") != "private":
        return None

    msg = Incoming(
        key=key,
        user_id=f"tg:{m['chat']['id']}",
        channel="telegram",
        type="unsupported",
        profile_name=(m.get("from") or {}).get("first_name"),
        caption=(m.get("caption") or "").strip() or None,
        raw=update,
    )
    doc = m.get("document") or {}
    if loc := m.get("location"):
        venue = m.get("venue") or {}  # a place picked on the map arrives as a venue
        msg.type = "location"
        msg.latitude = float(loc["latitude"])
        msg.longitude = float(loc["longitude"])
        msg.location_name = venue.get("title")
        msg.location_address = venue.get("address")
    elif "text" in m:
        msg.type = "text"
        msg.text = m["text"].strip()
    elif photos := m.get("photo"):
        msg.type = "image"
        msg.media_id = photos[-1]["file_id"]  # largest size
        msg.mime_type = "image/jpeg"
    elif (doc.get("mime_type") or "").startswith("image/"):
        msg.type = "image"
        msg.media_id = doc["file_id"]
        msg.mime_type = doc["mime_type"]
    return msg


def _clip(text: str, limit: int = TEXT_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _chat_id(user_id: str) -> str:
    return user_id.removeprefix("tg:")


class TelegramClient:
    channel = "telegram"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base = f"{API}/bot{settings.telegram_bot_token}"

    def _call(self, method: str, payload: dict, timeout: float = 15) -> dict | list:
        r = httpx.post(f"{self.base}/{method}", json=payload, timeout=timeout)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.is_error or not data.get("ok"):
            log.error("Telegram %s failed %s: %s", method, r.status_code, r.text[:500])
            r.raise_for_status()
            raise RuntimeError(data.get("description", "Telegram API error"))
        return data["result"]

    def _send(
        self, user_id: str, kind: str, body: str, options: list[dict], reply_markup: dict, text: str | None = None
    ) -> None:
        """`body` is the flow's prompt (recorded in dry run); `text` is what Telegram shows, if different."""
        payload = {"chat_id": _chat_id(user_id), "text": _clip(text or body), "reply_markup": reply_markup}
        if self.settings.dry_run:
            record(self.channel, user_id, kind, body, options, payload)
            return
        self._call("sendMessage", payload)

    def send_text(self, user_id: str, body: str) -> None:
        # Also clears the "Send location" keyboard if it is still showing
        self._send(user_id, "text", body, [], {"remove_keyboard": True})

    def send_buttons(self, user_id: str, body: str, buttons: list[tuple[str, str]]) -> None:
        # One button per row: large targets, read in order by screen readers
        keyboard = [[{"text": title, "callback_data": bid}] for bid, title in buttons]
        self._send(user_id, "buttons", body, options_from(buttons), {"inline_keyboard": keyboard})

    def send_list(
        self, user_id: str, body: str, button: str, section_title: str, rows: list[tuple[str, str, str]]
    ) -> None:
        # Telegram buttons can't carry descriptions, so they go in the message as a numbered list.
        # Colon, not a dash: screen readers read a colon as a pause but often say "em dash" aloud
        lines = [f"{i}. {title}" + (f": {desc}" if desc else "") for i, (_, title, desc) in enumerate(rows, 1)]
        keyboard = [[{"text": f"{i}. {title}", "callback_data": rid}] for i, (rid, title, _) in enumerate(rows, 1)]
        text = f"{body}\n\n" + "\n".join(lines)
        self._send(user_id, "list", body, options_from(rows), {"inline_keyboard": keyboard}, text=text)

    def send_location_request(
        self, user_id: str, body: str, current_label: str, choose_label: str, type_label: str
    ) -> None:
        # The first button makes Telegram send the device's location; the others are plain text
        # buttons, since bots can't open the map picker (the flow replies with how to use
        # Attach → Location, or asks for the place name)
        keyboard = {
            "keyboard": [
                [{"text": current_label, "request_location": True}],
                [{"text": choose_label}],
                [{"text": type_label}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
        options = options_from([("loc:current", current_label), ("loc:choose", choose_label), ("loc:type", type_label)])
        self._send(user_id, "location_request", body, options, keyboard)

    def acknowledge(self, msg: Incoming) -> None:
        """Stop the loading spinner on a tapped inline button."""
        if msg.callback_id and not self.settings.dry_run:
            try:
                self._call("answerCallbackQuery", {"callback_query_id": msg.callback_id})
            except Exception:
                log.warning("answerCallbackQuery failed", exc_info=True)

    def download_media(self, media_id: str, dest_dir: Path) -> Path | None:
        if self.settings.dry_run:
            return None
        info = self._call("getFile", {"file_id": media_id})
        file_path = info["file_path"]
        r = httpx.get(f"{API}/file/bot{self.settings.telegram_bot_token}/{file_path}", timeout=60)
        r.raise_for_status()
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{media_id[-24:]}{Path(file_path).suffix or '.bin'}"
        path.write_bytes(r.content)
        return path

    # --- setup helpers (used by app.telegram_cli) -------------------------------------------

    def get_me(self) -> dict:
        return self._call("getMe", {})

    def set_webhook(self, url: str, secret: str | None) -> None:
        payload = {"url": url, "allowed_updates": ["message", "callback_query"], "drop_pending_updates": True}
        if secret:
            payload["secret_token"] = secret
        self._call("setWebhook", payload)

    def set_profile(self, description: str, short_description: str, commands: list[tuple[str, str]], language_code: str = "") -> None:
        """Bot description, profile 'About' text and command menu. language_code "" is the default
        shown to everyone whose Telegram app language has no specific version."""
        lang = {"language_code": language_code} if language_code else {}
        self._call("setMyDescription", {"description": description, **lang})
        self._call("setMyShortDescription", {"short_description": short_description, **lang})
        self._call("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in commands], **lang})

    def get_profile(self, language_code: str = "") -> dict:
        lang = {"language_code": language_code} if language_code else {}
        return {
            "description": self._call("getMyDescription", lang)["description"],
            "short_description": self._call("getMyShortDescription", lang)["short_description"],
            "commands": [c["command"] for c in self._call("getMyCommands", lang)],
        }

    def delete_webhook(self) -> None:
        self._call("deleteWebhook", {"drop_pending_updates": False})

    def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict]:
        payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 10)
