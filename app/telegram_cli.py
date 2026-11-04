"""Run or wire up the Telegram bot.

    uv run python -m app.telegram_cli poll                     # local dev: long polling, no public URL
    uv run python -m app.telegram_cli set-webhook https://<host>/telegram/webhook
    uv run python -m app.telegram_cli delete-webhook
    uv run python -m app.telegram_cli whoami
    uv run python -m app.telegram_cli set-profile              # description, about text, command menu
"""

import argparse
import logging
import time

import httpx

from app.config import get_settings
from app import i18n
from app.db import init_db
from app.dispatch import process_incoming
from app.telegram import TelegramClient, parse_update

log = logging.getLogger("pi4c.telegram")


def poll(client: TelegramClient) -> None:
    init_db()
    client.delete_webhook()  # getUpdates doesn't work while a webhook is set
    me = client.get_me()
    log.info("polling as @%s — message the bot on Telegram (Ctrl+C to stop)", me.get("username"))
    offset = None
    while True:
        try:
            updates = client.get_updates(offset)
        except (httpx.HTTPError, RuntimeError):
            log.exception("getUpdates failed; retrying in 5 s")
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            if msg := parse_update(update):
                process_incoming(msg, client)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs contain the bot token
    parser = argparse.ArgumentParser(prog="python -m app.telegram_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("poll")
    hook = sub.add_parser("set-webhook")
    hook.add_argument("url")
    sub.add_parser("delete-webhook")
    sub.add_parser("whoami")
    sub.add_parser("set-profile")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.telegram_bot_token:
        parser.error("TELEGRAM_BOT_TOKEN is not set (.env)")
    settings.dry_run = False
    client = TelegramClient(settings)

    if args.command == "poll":
        try:
            poll(client)
        except KeyboardInterrupt:
            pass
    elif args.command == "set-webhook":
        client.set_webhook(args.url, settings.telegram_webhook_secret or None)
        print(f"webhook set to {args.url}")
    elif args.command == "delete-webhook":
        client.delete_webhook()
        print("webhook deleted")
    elif args.command == "set-profile":
        # English is the default; each other language is shown to users whose Telegram app uses it
        for lang in sorted(i18n.MESSAGES, key=lambda code: code != "en"):
            M = i18n.messages(lang)
            code = "" if lang == "en" else lang
            client.set_profile(M.BOT_DESCRIPTION, M.BOT_SHORT_DESCRIPTION, M.BOT_COMMANDS, code)
            profile = client.get_profile(code)
            print(f"[{lang or 'default'}] description {len(profile['description'])} chars, "
                  f"short {len(profile['short_description'])} chars, commands {profile['commands']}")
    else:
        print(client.get_me())


if __name__ == "__main__":
    main()
