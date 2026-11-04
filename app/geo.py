import json
import math
from functools import lru_cache

from app.config import get_settings

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@lru_cache
def load_wards() -> dict:
    path = get_settings().data_dir / "wards.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(lon: float, lat: float, rings: list) -> bool:
    outer, *holes = rings
    return _in_ring(lon, lat, outer) and not any(_in_ring(lon, lat, h) for h in holes)


def point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    if geometry["type"] == "Polygon":
        return _in_polygon(lon, lat, geometry["coordinates"])
    if geometry["type"] == "MultiPolygon":
        return any(_in_polygon(lon, lat, poly) for poly in geometry["coordinates"])
    return False


def find_ward(lat: float, lon: float, wards: dict | None = None) -> str | None:
    """Ward containing the point, or None if no ward file / outside all wards."""
    for feature in (wards if wards is not None else load_wards()).get("features", []):
        if feature.get("geometry") and point_in_geometry(lon, lat, feature["geometry"]):
            props = feature.get("properties") or {}
            return str(props.get("ward") or props.get("name") or props.get("id"))
    return None
