import json
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import clusters, meta, reports, stats
from app.config import get_settings
from app.db import init_db
from app.dispatch import process_incoming
from app.telegram import TelegramClient, parse_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # Telegram request URLs contain the bot token

settings = get_settings()
telegram = TelegramClient(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="PI4C API",
    version="0.1.0",
    description="Accessible grievance reporting over Telegram (Telugu) and a read API for downstream systems.",
    lifespan=lifespan,
)
for module in (reports, clusters, stats, meta):
    app.include_router(module.router, prefix="/api/v1")
# Any website may call the API from the browser. Safe because read endpoints are public anyway and
# keys travel in the X-API-Key header, not cookies (no credentials mode), so a site can't borrow a login.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PATCH"],
    allow_headers=["X-API-Key", "Content-Type"],
    expose_headers=["Content-Disposition", "ETag"],
)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "dry_run": settings.dry_run}


async def _json_body(request: Request) -> dict:
    try:
        return json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")


# --- Telegram (active channel) ------------------------------------------------------------


@app.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(request: Request, background: BackgroundTasks):
    """Register with `python -m app.telegram_cli set-webhook <url>`; for local dev use `poll` instead."""
    if settings.telegram_webhook_secret:
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
        if not secrets.compare_digest(given, settings.telegram_webhook_secret):
            raise HTTPException(403, "Bad secret token")
    body = await _json_body(request)
    if msg := parse_update(body):
        background.add_task(process_incoming, msg, telegram)
    return {"ok": True}

