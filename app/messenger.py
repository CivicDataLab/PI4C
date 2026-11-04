"""Channel-neutral message types shared by the Telegram and WhatsApp adapters.

The conversation flow only talks to a Messenger, so adding or switching a channel means
writing one adapter: parse its inbound payloads into Incoming, and implement these sends.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Every outbound message, normalised, when DRY_RUN is on (simulator and tests read this):
# {"channel", "to", "kind": text|buttons|list|location_request, "body",
#  "options": [{"id", "title", "description"}], "payload": <raw API payload>}
OUTBOX: list[dict] = []


@dataclass
class Incoming:
    key: str  # unique per delivery, used to drop retries
    user_id: str  # channel-prefixed: "tg:<chat id>" or "wa:<phone>"
    channel: str  # telegram | whatsapp
    type: str  # text | reply | location | image | unsupported (voice notes, stickers, files...)
    text: str | None = None
    reply_id: str | None = None
    reply_title: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    location_address: str | None = None
    media_id: str | None = None
    mime_type: str | None = None
    caption: str | None = None
    profile_name: str | None = None
    callback_id: str | None = None  # Telegram button taps must be acknowledged
    raw: dict = field(default_factory=dict, repr=False)


class Messenger(Protocol):
    channel: str

    def send_text(self, user_id: str, body: str) -> None: ...

    def send_buttons(self, user_id: str, body: str, buttons: list[tuple[str, str]]) -> None: ...

    def send_list(
        self, user_id: str, body: str, button: str, section_title: str, rows: list[tuple[str, str, str]]
    ) -> None: ...

    def send_location_request(
        self, user_id: str, body: str, current_label: str, choose_label: str, type_label: str
    ) -> None:
        """Offer 'share my current/live location', 'choose a place on the map' and 'type the place name'."""
        ...

    def download_media(self, media_id: str, dest_dir: Path) -> Path | None: ...

    def acknowledge(self, msg: Incoming) -> None: ...


def record(channel: str, to: str, kind: str, body: str, options: list[dict], payload: dict) -> None:
    OUTBOX.append({"channel": channel, "to": to, "kind": kind, "body": body, "options": options, "payload": payload})


def options_from(rows: list[tuple]) -> list[dict]:
    return [{"id": r[0], "title": r[1], "description": r[2] if len(r) > 2 else ""} for r in rows]
