# PI4C — accessible grievance chatbot (Telegram, Telugu)

Residents report accessibility barriers, civic problems and disaster/climate impacts to a Telegram
bot in Telugu or English. Each report is structured (category, location, photo, disability context), read back
for confirmation, triaged by keyword rules (barrier type, department, severity), grouped with
repeat reports of the same problem, and exposed through a REST API for downstream systems.

```
Telegram ─► poll / webhook ─► dispatch ─► flow.py (state machine) ─► Report ─► classify (rules) ─► cluster ─► /api/v1/*
```

The flow is channel-neutral (`app/messenger.py`); Telegram is the only adapter.

## Quick start

```bash
uv sync
uv run pytest
uv run python -m simulator.chat      # chat with the bot in the terminal, no token needed
```

## Running the Telegram bot

1. In Telegram, message **@BotFather** → `/newbot` → copy the token into `.env` as `TELEGRAM_BOT_TOKEN`.
2. Local development (no public URL needed):

   ```bash
   uv run python -m app.telegram_cli poll
   ```

   Open your bot in Telegram and send `/start`.
3. The read API runs separately:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

   Docs at http://localhost:8000/docs; import http://localhost:8000/openapi.json into Postman.

**Bot profile:** the description, profile "About" text and `/start` `/language` `/cancel` menu live in
`BOT_DESCRIPTION`, `BOT_SHORT_DESCRIPTION` and `BOT_COMMANDS` in `app/messages_en.py` / `app/messages_te.py`.
After editing them, publish with `uv run python -m app.telegram_cli set-profile` (English is the
default; Telugu is shown to users whose Telegram app is set to Telugu).

**Webhook mode** (deployed server): set `TELEGRAM_WEBHOOK_SECRET`, run uvicorn behind HTTPS, then
`uv run python -m app.telegram_cli set-webhook https://<host>/telegram/webhook`. Polling and a
webhook can't run at the same time; `poll` deletes the webhook on start.

## Database

SQLite only for now: `data/pi4c.db`, or another SQLite file set as `DATABASE_URL=sqlite:///...`
in `.env`. Tables are created on startup.

Photos are stored in the database too (`media_files`), written
with the report when the resident confirms. During the conversation they sit in `data/media/`,
since the session state can't hold file bytes; that copy is left in place. The API serves files
from the database.

## Classifier (keyword rules)

`app/classify.py` triages each confirmed report without any external service:

| Field | Rule |
|---|---|
| `barrier_type` | the sub-category the resident picked |
| `department_id` | the sub-category's `default_department` in `data/taxonomy.json` |
| `severity` | `high` for urgent words (danger, open manhole, live wire...) or disaster reports, otherwise `medium` |

A report whose default department isn't in `data/departments.json` gets `needs_review`.
`summary_en`, `description_en`, `confidence` and `classifier_model` stay empty.

## Conversation

| Step | Resident sees | Accepts |
|---|---|---|
| LANGUAGE | తెలుగు / English (first contact and every `/start`) | tap |
| MENU | 3 buttons: Accessibility / General Civic / Disaster-Climate | tap, or type 1–3 |
| LOCATION | **Live location**, **Choose a location** and **Type the place name** keyboard buttons | device location, live location, a place picked via the attach (paperclip) menu → Location ("Choose a location" replies with those steps), or a typed place name |
| LOCATION_PICK | up to 5 matching places in Visakhapatnam as a numbered list, plus "None of these" | tap, type the number, or type another name to search again |
| SUBCATEGORY | numbered list + buttons | tap, or type the number |
| DESCRIBE | free text prompt | typed text, or a photo with a caption (voice notes are refused) |
| PHOTO | optional, "No photo" button | photo or skip |
| AFFECTED | self (PwD) / caregiver / general | tap |
| READBACK | summary + Confirm / Edit / Cancel | Edit jumps to one step, then back here |

`/start`, "మెనూ" or "hi" restarts; `/cancel` or "రద్దు" cancels. Sessions expire after 30 min of silence.
Only private chats are handled; group messages are ignored.

`pwd_marker` is true when the reporter is a person with disability or a caregiver, or the category is accessibility.

## API (all under `/api/v1`, header `X-API-Key`)

| Endpoint | Scope | |
|---|---|---|
| `GET /reports` | read | filters: category, subcategory, barrier_type, ward, department_id, severity, status, pwd_marker, needs_review, cluster_id, created_from/to, updated_since, bbox; paginated |
| `GET /reports/{id}` | read | full record incl. media links |
| `PATCH /reports/{id}` | write | status, status_note, department_id, severity, municipal_subject, needs_review |
| `GET /reports/{id}/media/{media_id}` | read | photo (from the database) |
| `GET /reports/{id}/log` | write | stage-wise interaction log |
| `GET /reports.geojson` | read | same filters, GeoJSON points |
| `GET /reports.csv` | read | same filters, every matching report as CSV (Excel / Power BI); UTF-8 with BOM |
| `GET /clusters`, `/clusters/{id}` | read | distinct problems with report counts |
| `GET /stats/summary` | read | headline numbers: total, open, resolved, PwD, needs review, high/critical, with photo |
| `GET /stats/counts?group_by=…` | read | counts grouped by any of category, status, severity, ward, department_id, pwd_marker… (repeat `group_by`) |
| `GET /stats/timeseries?interval=day\|week\|month` | read | reports per period (UTC), optional `group_by` split |
| `GET /stats/by-ward`, `/by-category`, `/by-department` | read | grouped counts |
| `GET /metrics` | read | completion rate, read-back confirm/edit, review load, classifier mix |
| `GET /taxonomy`, `/departments`, `/wards` | read | reference data |

Chat IDs are never exposed; reports carry an HMAC `reporter_hash` instead.

All `/stats/*` endpoints and `/reports.csv` take the same filters as `/reports`.

**External dashboards.** Give each dashboard its own read key in `API_KEYS` (`grafana:read:<key>`)
so it can be revoked alone. Server-side tools (Power BI web connector, Grafana Infinity, Metabase,
scripts) just send the `X-API-Key` header. A web dashboard calling the API from the browser on
another site also needs its address in `CORS_ORIGINS`; note that a key in browser code is
visible to anyone using that page.

## Place search (typed place names)

Residents who can't share a location, or would rather not drag a map pin (screen-reader users
especially), type a landmark, shop, road or area. `app/places.py` searches it and the bot offers
the matches as a numbered list; the pick is stored with `location_route = place_search`, and the
read-back says the place name instead of coordinates.

- With `LOCATIONIQ_API_KEY` set, searches go to [LocationIQ](https://locationiq.com) (free plan, no card).
- Without it, the public OpenStreetMap Nominatim server is used: free and keyless, limited to one
  search per second, and its policy rules out search-as-you-type. Fine for testing and a small pilot.
- Results are kept inside `PLACE_SEARCH_BBOX` (`lon_min,lat_min,lon_max,lat_max`), Visakhapatnam's GVMC
  area by default, so a name like "Ameerpet" (Hyderabad) finds nothing. Shared locations are not limited.

## Configuration you'll want to edit

- `data/departments.json`: **placeholder** department list. `handles` becomes the classifier's option description.
- `data/taxonomy.json`: categories and sub-categories (Telugu labels, default department, municipal subject).
- `data/wards.geojson`: optional ward polygons; reports get `ward` set from their location.
- `app/messages_te.py`: every Telugu string the bot sends, with English glosses, for review with OPDs.

## Layout

```
app/
  main.py          FastAPI: read API + Telegram webhook
  telegram_cli.py  poll / set-webhook / delete-webhook / whoami
  dispatch.py      dedupe + per-resident lock + run flow
  flow.py          conversation state machine (channel-neutral)
  messenger.py     Incoming type + Messenger interface
  places.py        typed place-name search (LocationIQ / Nominatim), limited to the city
  telegram.py      Telegram adapter
  messages_te.py   Telugu strings (messages_en.py: English)
  classify.py      keyword-rules triage
  cluster.py       repeat-report grouping
  geo.py           ward lookup, distances
  api/             REST endpoints
  models.py        SQLAlchemy tables
simulator/chat.py  terminal simulator
tests/
```

## Not yet done

- No status notifications back to residents.
- Telugu strings need native-speaker and OPD review.
- No municipal grievance-system connector; downstream systems pull from the API.
