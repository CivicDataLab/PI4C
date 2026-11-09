import csv
import io
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import audit, taxonomy
from app.api.filters import report_filters
from app.auth import require_write_access
from app.db import get_db
from app.models import InteractionLog, Media, Report
from app.schemas import LogEntry, Page, ReportOut, ReportPatch

router = APIRouter(tags=["reports"])


def _get_report(db: Session, report_id: int) -> Report:
    report = db.get(Report, report_id, options=[selectinload(Report.media)])
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/reports", response_model=Page[ReportOut])
def list_reports(
    conds: list = Depends(report_filters),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(Report).where(*conds))
    rows = db.scalars(
        select(Report)
        .where(*conds)
        .options(selectinload(Report.media))
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[ReportOut](items=rows, total=total, limit=limit, offset=offset)


@router.get("/reports.geojson")
def reports_geojson(
    conds: list = Depends(report_filters),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Report).where(*conds).order_by(Report.id.desc()).limit(limit)).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": r.id,
                "geometry": {"type": "Point", "coordinates": [r.longitude, r.latitude]},
                "properties": {
                    "ref": r.ref,
                    "category": r.category,
                    "barrier_type": r.barrier_type,
                    "department_id": r.department_id,
                    "severity": r.severity,
                    "status": r.status,
                    "pwd_marker": r.pwd_marker,
                    "ward": r.ward,
                    "cluster_id": r.cluster_id,
                    "created_at": r.created_at.isoformat(),
                },
            }
            for r in rows
        ],
    }


CSV_FIELDS = [name for name in ReportOut.model_fields if name != "media"] + ["photo_count", "media_urls"]


@router.get("/reports.csv", response_class=StreamingResponse)
def reports_csv(
    conds: list = Depends(report_filters),
    db: Session = Depends(get_db),
):
    """Every matching report as CSV (UTF-8 with BOM so Excel shows Telugu correctly), for Excel / Power BI."""
    stmt = select(Report).where(*conds).options(selectinload(Report.media)).order_by(Report.id)

    def rows() -> Iterator[str]:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
        buf.write("﻿")
        writer.writeheader()
        for report in db.scalars(stmt):
            out = ReportOut.model_validate(report)
            row = out.model_dump(exclude={"media"})
            row["photo_count"] = sum(1 for m in out.media if m.kind == "image")
            row["media_urls"] = " ".join(m.url for m in out.media)
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
        yield buf.getvalue()

    return StreamingResponse(
        rows(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="pi4c-reports.csv"'}
    )


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    return _get_report(db, report_id)


@router.patch("/reports/{report_id}", response_model=ReportOut)
def update_report(
    report_id: int,
    patch: ReportPatch,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
):
    report = _get_report(db, report_id)
    changes = patch.model_dump(exclude_unset=True)
    if changes.get("department_id") and changes["department_id"] not in taxonomy.department_ids():
        raise HTTPException(422, f"Unknown department_id '{changes['department_id']}'")
    for field, value in changes.items():
        setattr(report, field, value)
    audit.log_event(db, report.interaction_id, "api_update", payload={"changes": changes}, report_id=report.id)
    db.commit()
    return _get_report(db, report_id)


@router.get("/reports/{report_id}/media/{media_id}")
def get_media(
    report_id: int, media_id: int, db: Session = Depends(get_db)
):
    media = db.get(Media, media_id)
    if media is None or media.report_id != report_id:
        raise HTTPException(404, "Media not found")
    if media.file:
        return Response(
            media.file.data,
            media_type=media.mime_type or "application/octet-stream",
            headers={"ETag": f'"{media.file.sha256}"', "Cache-Control": "private, max-age=86400"},
        )
    raise HTTPException(404, "Media not found")


@router.get("/reports/{report_id}/log", response_model=list[LogEntry])
def get_report_log(report_id: int, db: Session = Depends(get_db), _: None = Depends(require_write_access)):
    """Stage-wise interaction log for the conversation that produced this report (internal use)."""
    report = _get_report(db, report_id)
    return db.scalars(
        select(InteractionLog)
        .where(InteractionLog.interaction_id == report.interaction_id)
        .order_by(InteractionLog.id)
    ).all()
