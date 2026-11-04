"""Place search for residents who type a place name instead of sharing a location.

LocationIQ when LOCATIONIQ_API_KEY is set, otherwise the public OpenStreetMap Nominatim server
(free, no key; its policy allows one search per typed name, but not search-as-you-type, and at
most one request per second). Both speak the same Nominatim API. Results are limited to
PLACE_SEARCH_BBOX (Visakhapatnam by default); anything outside it is dropped.
"""

import logging
import threading
import time
from dataclasses import dataclass

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

LOCATIONIQ_URL = "https://us1.locationiq.com/v1/search"
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


def bbox(settings: Settings) -> tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max)"""
    lon_min, lat_min, lon_max, lat_max = (float(x) for x in settings.place_search_bbox.split(","))
    return lon_min, lat_min, lon_max, lat_max


def search(query: str, settings: Settings, language: str = "en") -> list[Place] | None:
    """Up to MAX_RESULTS places inside the bbox; [] when nothing matches, None when the service failed."""
    lon_min, lat_min, lon_max, lat_max = bbox(settings)
    params = {
        "q": query,
        "format": "json",
        "limit": MAX_RESULTS + 3,  # a few spare, since duplicates are dropped
        "viewbox": f"{lon_min},{lat_max},{lon_max},{lat_min}",
        "bounded": 1,
        "countrycodes": "in",
        "addressdetails": 1,
        "accept-language": language,
    }
    if settings.locationiq_api_key:
        url, params["key"] = LOCATIONIQ_URL, settings.locationiq_api_key
    else:
        url = NOMINATIM_URL
        _wait_for_nominatim()
    try:
        r = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=settings.place_search_timeout_s)
        if r.status_code == 404:  # LocationIQ answers "no match" with 404
            return []
        r.raise_for_status()
        items = r.json()
    except Exception:
        log.warning("place search failed", exc_info=True)
        return None

    places, seen = [], set()
    for item in items:
        lat, lon = float(item["lat"]), float(item["lon"])
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue
        place = _place(item, lat, lon)
        key = (place.name.casefold(), place.address.casefold())
        if key not in seen:
            seen.add(key)
            places.append(place)
    return places[:MAX_RESULTS]


def _place(item: dict, lat: float, lon: float) -> Place:
    parts = [p.strip() for p in item.get("display_name", "").split(",") if p.strip()]
    name = item.get("name") or (parts[0] if parts else "")
    addr = item.get("address") or {}
    # Neighbourhood and area, enough to tell two "Bus stops" apart without reading out the whole address
    area = [
        addr.get(k)
        for k in ("road", "neighbourhood", "suburb", "city_district", "city", "town", "village")
        if addr.get(k) and addr.get(k) != name
    ]
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
