"""Post-submission processing: classify, then cluster. Failures flag the report for review."""

import logging

from sqlalchemy.orm import Session

from app import audit, classify, cluster
from app.config import Settings
from app.models import Report

log = logging.getLogger(__name__)


def process_report(db: Session, report: Report, settings: Settings) -> None:
    try:
        result = classify.classify_report(report)
        report.barrier_type = result.barrier_type
        report.department_id = result.department_id
        report.severity = result.severity
        report.classifier = result.method
        report.needs_review = result.needs_review
        audit.log_event(db, report.interaction_id, "classified", payload=result.as_log(), report_id=report.id)
    except Exception as exc:
        log.exception("classification failed for report %s", report.id)
        report.needs_review = True
        audit.log_event(db, report.interaction_id, "classify_error", payload={"error": str(exc)}, report_id=report.id)

    try:
        c = cluster.assign_cluster(db, report, settings)
        audit.log_event(
            db, report.interaction_id, "clustered",
            payload={"cluster_id": c.id, "match": report.cluster_match}, report_id=report.id,
        )
    except Exception as exc:
        log.exception("clustering failed for report %s", report.id)
        audit.log_event(db, report.interaction_id, "cluster_error", payload={"error": str(exc)}, report_id=report.id)

    db.commit()
