import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="pi4c-test-"))
# Set TEST_DATABASE_URL to run against Postgres; its tables are dropped first, so use a throwaway database
_pg_url = os.environ.get("TEST_DATABASE_URL")
os.environ.update(
    {
        "DATABASE_URL": _pg_url or f"sqlite:///{(_tmp / 'test.db').as_posix()}",
        "MEDIA_DIR": str(_tmp / "media"),
        "DRY_RUN": "true",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_WEBHOOK_SECRET": "",
        "WA_APP_SECRET": "",
        "WA_VERIFY_TOKEN": "verify-me",
        "API_KEYS": "reader:read:read-key,writer:write:write-key",
        "CORS_ORIGINS": "https://dashboard.example",
        "OPENROUTER_API_KEY": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import fake_inbound as F  # noqa: E402
from app.main import app  # noqa: E402
from app.messenger import OUTBOX  # noqa: E402

READ = {"X-API-Key": "read-key"}
WRITE = {"X-API-Key": "write-key"}


@pytest.fixture(scope="session")
def client():
    if _pg_url:
        from app import models  # noqa: F401  registers tables
        from app.db import Base, engine

        Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_outbox():
    OUTBOX.clear()
    yield


def send(client, payload) -> None:
    assert client.post("/telegram/webhook", json=payload).status_code == 200


def last() -> dict:
    return OUTBOX[-1]


def kind(msg: dict) -> str:
    return msg["kind"]


def body(msg: dict) -> str:
    return msg["body"]


def report_from_ack(client) -> dict:
    ref = next(body(m) for m in reversed(OUTBOX) if "PI4C-" in body(m)).split("PI4C-")[1][:6]
    r = client.get(f"/api/v1/reports/{int(ref)}", headers=READ)
    assert r.status_code == 200
    return r.json()


def start(client, chat_id, lang="te") -> None:
    """/start, then pick a language; leaves the resident at the category menu."""
    send(client, F.text(chat_id, "/start"))
    assert kind(last()) == "buttons" and last()["options"][0]["id"] == "lang:te"
    send(client, F.reply(chat_id, f"lang:{lang}"))
    assert kind(last()) == "buttons" and last()["options"][0]["id"] == "cat:accessibility"


def walk_to_readback(client, chat_id, *, category="accessibility", sub="footpath", lat=13.0827, lon=80.2707,
                     description="ఫుట్‌పాత్‌పై పెద్ద గుంత, వీల్‌చైర్ వెళ్లలేకపోతోంది", affected="self", lang="te"):
    start(client, chat_id, lang)
    send(client, F.reply(chat_id, f"cat:{category}"))
    assert kind(last()) == "location_request"
    send(client, F.location(chat_id, lat, lon, name="Bus stand"))
    assert kind(last()) == "list"
    send(client, F.reply(chat_id, f"sub:{sub}"))
    assert kind(last()) == "text"
    send(client, F.text(chat_id, description))
    assert kind(last()) == "buttons"  # photo
    send(client, F.reply(chat_id, "photo:skip"))
    send(client, F.reply(chat_id, f"aff:{affected}"))
    assert kind(last()) == "buttons"
    assert "Bus stand" in body(last())
