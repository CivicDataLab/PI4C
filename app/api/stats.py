from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, literal_column, select
from sqlalchemy.orm import Session

from app.api.filters import report_filters
from app.auth import require_scope
from app.db import get_db
from app.models import InteractionLog, Media, Report

router = APIRouter(tags=["stats"])

# Columns a dashboard may group by (?group_by=status&group_by=severity)
GROUPABLE = {
    name: getattr(Report, name)
    for name in (
        "category", "subcategory", "barrier_type", "department_id", "severity", "status", "ward", "pwd_marker",
        "needs_review", "affected", "language", "channel", "classifier", "cluster_match",
    )
}
OPEN_STATUSES = ("new", "acknowledged", "in_progress")


def _grouped(db: Session, columns: list, conds: list) -> list[dict]:
    stmt = select(*columns, func.count().label("count")).where(*conds).group_by(*columns).order_by(*columns)
    return [dict(row._mapping) for row in db.execute(stmt)]


@router.get("/stats/by-ward")
def stats_by_ward(conds: list = Depends(report_filters), db: Session = Depends(get_db), _=Depends(require_scope("read"))):
    return _grouped(db, [Report.ward, Report.category, Report.pwd_marker], conds)


@router.get("/stats/by-category")
def stats_by_category(conds: list = Depends(report_filters), db: Session = Depends(get_db), _=Depends(require_scope("read"))):
    return _grouped(db, [Report.category, Report.barrier_type, Report.pwd_marker], conds)


@router.get("/stats/by-department")
def stats_by_department(conds: list = Depends(report_filters), db: Session = Depends(get_db), _=Depends(require_scope("read"))):
    return _grouped(db, [Report.department_id, Report.status], conds)


def _group_columns(group_by: list[str]) -> list:
    unknown = [g for g in group_by if g not in GROUPABLE]
    if unknown:
        raise HTTPException(422, f"Cannot group by {', '.join(unknown)}; choose from {', '.join(sorted(GROUPABLE))}")
    return [GROUPABLE[g].label(g) for g in group_by]


@router.get("/stats/summary")
def stats_summary(conds: list = Depends(report_filters), db: Session = Depends(get_db), _=Depends(require_scope("read"))):
    """Headline numbers for a dashboard's top row; takes the same filters as /reports."""

    def count(*extra) -> int:
        return db.scalar(select(func.count()).select_from(Report).where(*conds, *extra))

    first, last = db.execute(select(func.min(Report.created_at), func.max(Report.created_at)).where(*conds)).one()
    return {
        "reports": count(),
        "open": count(Report.status.in_(OPEN_STATUSES)),
        "resolved": count(Report.status == "resolved"),
        "rejected": count(Report.status == "rejected"),
        "pwd_marker": count(Report.pwd_marker.is_(True)),
        "needs_review": count(Report.needs_review.is_(True)),
        "high_or_critical": count(Report.severity.in_(("high", "critical"))),
        "with_photo": count(Report.media.any(Media.kind == "image")),
        "distinct_problems": db.scalar(select(func.count(distinct(Report.cluster_id))).where(*conds)),
        "first_report_at": first,
        "last_report_at": last,
    }


@router.get("/stats/counts")
def stats_counts(
    group_by: list[str] = Query(..., description=f"One or more of: {', '.join(GROUPABLE)}"),
    conds: list = Depends(report_filters),
    db: Session = Depends(get_db),
    _=Depends(require_scope("read")),
):
    """Report counts grouped by any combination of fields, e.g. ?group_by=status&group_by=severity."""
    return _grouped(db, _group_columns(group_by), conds)


def _period(db: Session, interval: str):
    """created_at truncated to the start of its day / week (Monday) / month, as YYYY-MM-DD."""
    col = Report.created_at
    if db.get_bind().dialect.name == "postgresql":
        # Literals, not bound parameters: Postgres only matches the GROUP BY expression if it's identical
        trunc = func.date_trunc(literal_column(f"'{interval}'"), col)
        return func.to_char(trunc, literal_column("'YYYY-MM-DD'"))
    if interval == "day":
        return func.date(col)
    if interval == "week":
        return func.date(col, "weekday 0", "-6 days")
    return func.strftime("%Y-%m-01", col)


@router.get("/stats/timeseries")
def stats_timeseries(
    interval: Literal["day", "week", "month"] = "day",
    group_by: list[str] = Query([], description="Optional split per period, e.g. category"),
    conds: list = Depends(report_filters),
    db: Session = Depends(get_db),
    _=Depends(require_scope("read")),
):
    """Reports per day / week / month (UTC) for trend charts. Periods with no reports are omitted."""
    return _grouped(db, [_period(db, interval).label("period"), *_group_columns(group_by)], conds)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db), _=Depends(require_scope("read"))):
    """Evaluation signals from the work plan: completion, read-back fidelity, review load."""

    def count_by(column) -> dict:
        return {str(k): v for k, v in db.execute(select(column, func.count()).group_by(column))}

    def sessions_with(stage: str) -> int:
        return db.scalar(select(func.count(distinct(InteractionLog.interaction_id))).where(InteractionLog.stage == stage))

    reports = db.scalar(select(func.count()).select_from(Report))
    started = sessions_with("session_start")
    return {
        "reports": reports,
        "conversations_started": started,
        "conversations_cancelled": sessions_with("cancelled"),
        "conversations_expired": sessions_with("expired"),
        "completion_rate": round(reports / started, 3) if started else None,
        "readback_outcome": count_by(Report.readback_outcome),
        "needs_review": db.scalar(select(func.count()).where(Report.needs_review.is_(True))),
        "classifier": count_by(Report.classifier),
        "location_route": count_by(Report.location_route),
        "cluster_match": count_by(Report.cluster_match),
        "pwd_marker": count_by(Report.pwd_marker),
    }
