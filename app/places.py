"""Place search for residents who type a place name instead of sharing a location.

Uses the public OpenStreetMap Nominatim server (free, no key; its policy allows one search per
typed name, but not search-as-you-type, and at most one request per second). Results can be
anywhere in India; each one names its town or city so same-named places can be told apart.
"""

import logging
import threading
import time
from dataclasses import dataclass

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PI4C-grievance-bot/0.1 (+https://github.com/JatinChauhan008/PI4C)"
MAX_RESULTS = 5

_nominatim_lock = threading.Lock()
_nominatim_last = 0.0


@dataclass
class Place:
    name: str
    address: str
    latitude: float
    longitude: float


def search(query: str, settings: Settings, language: str = "en") -> list[Place] | None:
    """Up to MAX_RESULTS places; [] when nothing matches, None when the service failed."""
    params = {
        "q": query,
        "format": "json",
        "limit": MAX_RESULTS + 3,  # a few spare, since duplicates are dropped
        "countrycodes": "in",
        "addressdetails": 1,
        "accept-language": language,
    }
    _wait_for_nominatim()
    try:
        r = httpx.get(
            NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=settings.place_search_timeout_s
        )
        r.raise_for_status()
        items = r.json()
    except Exception:
        log.warning("place search failed", exc_info=True)
        return None

    places, seen = [], set()
    for item in items:
        place = _place(item, float(item["lat"]), float(item["lon"]))
        key = (place.name.casefold(), place.address.casefold())
        if key not in seen:
            seen.add(key)
            places.append(place)
    return places[:MAX_RESULTS]


def _place(item: dict, lat: float, lon: float) -> Place:
    parts = [p.strip() for p in item.get("display_name", "").split(",") if p.strip()]
    name = item.get("name") or (parts[0] if parts else "")
    addr = item.get("address") or {}
    # Up to two local parts plus the town or city, enough to tell two "Bus stands" apart (even in
    # different cities) without reading out the whole address
    local = [
        addr.get(k)
        for k in ("road", "neighbourhood", "suburb", "city_district")
        if addr.get(k) and addr.get(k) != name
    ][:2]
    town = next((addr.get(k) for k in ("city", "town", "village", "state_district") if addr.get(k)), None)
    area = local + ([town] if town and town != name else [])
    if not area:
        skip = {addr.get("state"), addr.get("country"), addr.get("postcode"), "India", "Andhra Pradesh"}
        area = [p for p in parts[1:] if not p.isdigit() and p not in skip]
    return Place(name=name, address=", ".join(dict.fromkeys(area[:3])), latitude=lat, longitude=lon)


def _wait_for_nominatim() -> None:
    """Nominatim's usage policy: at most one request per second."""
    global _nominatim_last
    with _nominatim_lock:
        wait = 1.0 - (time.monotonic() - _nominatim_last)
        if wait > 0:
            time.sleep(wait)
        _nominatim_last = time.monotonic()
