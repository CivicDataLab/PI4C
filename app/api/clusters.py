from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.filters import parse_bbox
from app.db import get_db
from app.models import Cluster, Report
from app.schemas import ClusterDetail, ClusterOut, Page

router = APIRouter(tags=["clusters"])


@router.get("/clusters", response_model=Page[ClusterOut])
def list_clusters(
    category: str | None = None,
    subcategory: str | None = None,
    status: str | None = None,
    min_reports: int = Query(1, ge=1),
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conds = [Cluster.report_count >= min_reports]
    for col, value in ((Cluster.category, category), (Cluster.subcategory, subcategory), (Cluster.status, status)):
        if value is not None:
            conds.append(col == value)
    if box := parse_bbox(bbox):
        min_lon, min_lat, max_lon, max_lat = box
        conds += [Cluster.longitude.between(min_lon, max_lon), Cluster.latitude.between(min_lat, max_lat)]

    total = db.scalar(select(func.count()).select_from(Cluster).where(*conds))
    rows = db.scalars(
        select(Cluster)
        .where(*conds)
        .order_by(Cluster.report_count.desc(), Cluster.last_seen.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[ClusterOut](items=rows, total=total, limit=limit, offset=offset)


@router.get("/clusters/{cluster_id}", response_model=ClusterDetail)
def get_cluster(cluster_id: int, db: Session = Depends(get_db)):
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(404, "Cluster not found")
    report_ids = db.scalars(select(Report.id).where(Report.cluster_id == cluster_id).order_by(Report.id)).all()
    return ClusterDetail.model_validate(cluster).model_copy(update={"report_ids": list(report_ids)})
