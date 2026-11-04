"""Group repeat reports of the same physical problem.

Conservative by design: a report joins the nearest open cluster of the same barrier type seen
within the time window and radius. Matches beyond the strict radius are marked "possible" so a
person can confirm them; everything else starts a new cluster.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.geo import haversine_m
from app.models import Cluster, Report, utcnow


def assign_cluster(db: Session, report: Report, settings: Settings) -> Cluster:
    now = utcnow()
    since = now - timedelta(days=settings.cluster_window_days)
    candidates = db.scalars(
        select(Cluster).where(
            Cluster.category == report.category,
            Cluster.subcategory == report.barrier_type,
            Cluster.status != "resolved",
            Cluster.last_seen >= since,
        )
    ).all()

    nearest = min(
        ((haversine_m(report.latitude, report.longitude, c.latitude, c.longitude), c) for c in candidates),
        key=lambda pair: pair[0],
        default=None,
    )

    if nearest and nearest[0] <= settings.cluster_radius_m:
        distance, cluster = nearest
        n = cluster.report_count
        cluster.latitude = (cluster.latitude * n + report.latitude) / (n + 1)
        cluster.longitude = (cluster.longitude * n + report.longitude) / (n + 1)
        cluster.report_count = n + 1
        cluster.last_seen = now
        report.cluster_match = "strict" if distance <= settings.cluster_strict_radius_m else "possible"
    else:
        cluster = Cluster(
            category=report.category,
            subcategory=report.barrier_type,
            latitude=report.latitude,
            longitude=report.longitude,
            report_count=1,
            first_seen=now,
            last_seen=now,
        )
        db.add(cluster)
        report.cluster_match = "new"

    report.cluster = cluster
    db.flush()
    return cluster
