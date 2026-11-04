"""Build Telegram Bot API updates for the simulator and tests."""

import itertools
import time

_ids = itertools.count(int(time.time() * 1000))


def _user(chat_id) -> dict:
    return {"id": int(chat_id), "is_bot": False, "first_name": "Test"}


def _message(chat_id, **fields) -> dict:
    n = next(_ids)
    return {
        "update_id": n,
        "message": {
            "message_id": n,
            "date": int(time.time()),
            "chat": {"id": int(chat_id), "type": "private", "first_name": "Test"},
            "from": _user(chat_id),
            **fields,
        },
    }


def text(chat_id, body: str) -> dict:
    return _message(chat_id, text=body)


def reply(chat_id, data: str, title: str = "") -> dict:
    """An inline-keyboard button tap (callback_query)."""
    n = next(_ids)
    return {
        "update_id": n,
        "callback_query": {
            "id": str(n),
            "from": _user(chat_id),
            "chat_instance": "0",
            "message": {"message_id": n, "date": int(time.time()), "chat": {"id": int(chat_id), "type": "private"}},
            "data": data,
        },
    }


def location(chat_id, lat: float, lon: float, name: str | None = None, address: str | None = None) -> dict:
    fields = {"location": {"latitude": lat, "longitude": lon}}
    if name:  # a place picked on the map comes as a venue
        fields["venue"] = {"location": fields["location"], "title": name, "address": address or ""}
    return _message(chat_id, **fields)


def image(chat_id, file_id: str = "fake-photo", caption: str | None = None) -> dict:
    fields = {"photo": [{"file_id": f"{file_id}-small", "width": 90, "height": 90}, {"file_id": file_id, "width": 1280, "height": 960}]}
    if caption:
        fields["caption"] = caption
    return _message(chat_id, **fields)


def audio(chat_id, file_id: str = "fake-voice") -> dict:
    return _message(chat_id, voice={"file_id": file_id, "duration": 4, "mime_type": "audio/ogg"})
