"""Report triage: barrier type, department, severity, from keyword rules on top of the
resident's menu choice.

  barrier_type  the sub-category the resident picked
  department    the sub-category's default department (taxonomy.json)
  severity      high for urgent words or disaster reports, otherwise medium

Reports whose default department is unknown are flagged for review.
"""

from dataclasses import asdict, dataclass

from app import taxonomy
from app.models import Report

URGENT_WORDS = (
    "ప్రమాదం", "అత్యవసరం", "కరెంటు షాక్", "తెరిచిన మ్యాన్‌హోల్", "danger", "accident", "urgent",
    "emergency", "live wire", "open manhole", "pramadam", "atyavasaram",
)


@dataclass
class Classification:
    barrier_type: str
    department_id: str | None
    severity: str
    needs_review: bool = False
    method: str = "rules"

    def as_log(self) -> dict:
        return asdict(self)


def classify_report(report: Report) -> Classification:
    sub = taxonomy.subcategory(report.category, report.subcategory) or {}
    dept = sub.get("default_department")
    dept_ok = dept in taxonomy.department_ids()
    text = (report.description_raw or "").casefold()
    if any(w in text for w in URGENT_WORDS) or report.category == "disaster":
        severity = "high"
    else:
        severity = "medium"
    return Classification(
        barrier_type=report.subcategory,
        department_id=dept if dept_ok else None,
        severity=severity,
        needs_review=not dept_ok,
    )
