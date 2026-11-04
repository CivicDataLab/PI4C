from datetime import datetime, timezone

from fastapi import HTTPException, Query

from app.models import Report


def naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be minLon,minLat,maxLon,maxLat")
    return min_lon, min_lat, max_lon, max_lat


def report_filters(
    category: str | None = None,
    subcategory: str | None = None,
    barrier_type: str | None = None,
    ward: str | None = None,
    department_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    pwd_marker: bool | None = None,
    needs_review: bool | None = None,
    cluster_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    updated_since: datetime | None = Query(None, description="For incremental sync: records changed after this time"),
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
) -> list:
    equals = {
        Report.category: category,
        Report.subcategory: subcategory,
        Report.barrier_type: barrier_type,
        Report.ward: ward,
        Report.department_id: department_id,
        Report.severity: severity,
        Report.status: status,
        Report.pwd_marker: pwd_marker,
        Report.needs_review: needs_review,
        Report.cluster_id: cluster_id,
    }
    conds = [col == value for col, value in equals.items() if value is not None]
    if created_from:
        conds.append(Report.created_at >= naive_utc(created_from))
    if created_to:
        conds.append(Report.created_at < naive_utc(created_to))
    if updated_since:
        conds.append(Report.updated_at > naive_utc(updated_since))
    if box := parse_bbox(bbox):
        min_lon, min_lat, max_lon, max_lat = box
        conds += [
            Report.longitude.between(min_lon, max_lon),
            Report.latitude.between(min_lat, max_lat),
        ]
    return conds
