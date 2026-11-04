"""Chat with the bot in the terminal, no phone or bot token needed.

    uv run python -m simulator.chat

Messages go through the real /telegram/webhook handler; outbound messages are captured
(dry run) and printed. Uses its own database at data/simulator.db.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["DRY_RUN"] = "true"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'simulator.db').as_posix()}")
os.environ["API_KEYS"] = "simulator:write:sim-key"

from fastapi.testclient import TestClient  # noqa: E402

from app import fake_inbound as F  # noqa: E402
from app.main import app  # noqa: E402
from app.messenger import OUTBOX  # noqa: E402

API_HEADERS = {"X-API-Key": "sim-key"}
HELP = """Commands:
  <text>                  send a text message (try "hi" or "/start")
  <number>                tap option N of the last buttons/list
  /loc <lat> <lon> [name] share a location (e.g. /loc 13.0827 80.2707 Central Station)
  /photo [caption]        send a photo
  /voice                  send a voice note (the bot should refuse it)
  /reports                show the latest reports from the API
  /user <chat id>         switch to another resident
  /help, /quit"""


def render(msg: dict) -> list[dict]:
    """Print a captured outbound message; return its tappable options."""
    print(f"\nbot> {msg['body']}")
    for i, opt in enumerate(msg["options"], 1):
        extra = f": {opt['description']}" if opt.get("description") else ""
        print(f"     {i}. {opt['title']}{extra}")
    if msg["kind"] == "location_request":
        print("     (option 1 / sharing a location → use /loc <lat> <lon> [name])")
    # Keyboard buttons send their label as text; inline buttons send a callback
    return [{**o, "as_text": msg["kind"] == "location_request"} for o in msg["options"]]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    chat_id = "500000001"
    options: list[dict] = []
    print(HELP)
    with TestClient(app) as client:
        while True:
            try:
                line = input(f"\n[{chat_id}] you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            cmd, _, rest = line.partition(" ")
            if cmd == "/quit":
                break
            if cmd == "/help":
                print(HELP)
                continue
            if cmd == "/user":
                chat_id = rest.strip() or chat_id
                continue
            if cmd == "/reports":
                for rep in client.get("/api/v1/reports?limit=5", headers=API_HEADERS).json().get("items", []):
                    print(
                        f"  {rep['ref']}  {rep['category']}/{rep['barrier_type']}  dept={rep['department_id']}  "
                        f"sev={rep['severity']}  pwd={rep['pwd_marker']}  cluster={rep['cluster_id']}({rep['cluster_match']})  "
                        f"review={rep['needs_review']}  via={rep['classifier']}"
                    )
                continue

            if cmd == "/loc":
                parts = rest.split(maxsplit=2)
                if len(parts) < 2:
                    print("usage: /loc <lat> <lon> [name]")
                    continue
                payload = F.location(chat_id, float(parts[0]), float(parts[1]), name=parts[2] if len(parts) > 2 else None)
            elif cmd == "/photo":
                payload = F.image(chat_id, caption=rest or None)
            elif cmd == "/voice":
                payload = F.audio(chat_id)
            elif line.isdigit() and 1 <= int(line) <= len(options):
                opt = options[int(line) - 1]
                payload = F.text(chat_id, opt["title"]) if opt["as_text"] else F.reply(chat_id, opt["id"])
            else:
                payload = F.text(chat_id, line)

            OUTBOX.clear()
            client.post("/telegram/webhook", json=payload)
            options = []
            for msg in OUTBOX:
                options = render(msg) or options


if __name__ == "__main__":
    main()
