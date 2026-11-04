"""Report triage: barrier type, department, severity.

Uses a decision model (Jev by default) through OpenRouter's Decisions API when
OPENROUTER_API_KEY and OPENROUTER_MODEL are set; otherwise keyword rules on top of the
resident's menu choice. Decision models return typed answers with probabilities, not text, so
each field is one question:

  barrier_type  choice  sub-categories of the category the resident picked
  department    choice  departments.json, criteria = what each department handles
  severity      score   ordered low → critical

Low-confidence answers keep the resident's own choice / the rules' department and flag the
report for review. https://openrouter.ai/docs/guides/community/jev
"""

import logging
from dataclasses import asdict, dataclass

import httpx

from app import taxonomy
from app.config import Settings
from app.models import Report

log = logging.getLogger(__name__)

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
SEVERITIES = ("low", "medium", "high", "critical")
SEVERITY_CRITERIA = [
    "Low: minor or cosmetic problem",
    "Medium: a real problem that makes daily life harder but is not urgent",
    "High: blocks movement or access for persons with disabilities, or affects many households",
    "Critical: immediate danger to life, such as a live wire, open manhole, or people trapped by water",
]
URGENT_WORDS = (
    "ప్రమాదం", "అత్యవసరం", "కరెంటు షాక్", "తెరిచిన మ్యాన్‌హోల్", "danger", "accident", "urgent",
    "emergency", "live wire", "open manhole", "pramadam", "atyavasaram",
)


@dataclass
class Classification:
    barrier_type: str
    department_id: str | None
    severity: str
    summary_en: str | None = None
    description_en: str | None = None
    confidence: float | None = None
    needs_review: bool = False
    method: str = "rules"
    model: str | None = None
    probabilities: dict | None = None
    cost_usd: float | None = None

    def as_log(self) -> dict:
        return asdict(self)


def classify_report(report: Report, settings: Settings) -> Classification:
    use_model = settings.openrouter_api_key and settings.openrouter_model
    if use_model and report.description_type == "text" and report.description_raw:
        try:
            return _classify_decisions(report, settings)
        except Exception:
            log.exception("decision-model classification failed; falling back to rules")
            result = _classify_rules(report)
            result.needs_review = True
            return result
    return _classify_rules(report)


def _classify_rules(report: Report) -> Classification:
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


def build_request(report: Report, model: str) -> dict:
    cat = taxonomy.category(report.category)
    return {
        "model": model,
        "state": {
            "context": "Citizen grievance report to a municipal corporation in Andhra Pradesh, India. "
            "The description may be in Telugu script, romanised Telugu, English, or a mix.",
            "category_chosen_by_resident": cat["label_en"],
            "sub_category_chosen_by_resident": report.subcategory,
            "reported_for": {
                "self": "a person with disability reporting for themself",
                "caregiver": "a caregiver reporting for a person with disability",
                "none": "a general problem, not disability-related",
            }.get(report.affected, report.affected),
            "location_name": report.location_name,
            "description": report.description_raw,
        },
        "questions": {
            "barrier_type": {
                "type": "choice",
                "instructions": "Which sub-category best describes the problem in the description? "
                "Prefer the resident's own choice unless the description clearly describes another.",
                "criteria": {s["id"]: f"{s['label_en']}: {s['description_en']}" for s in cat["subcategories"]},
            },
            "department": {
                "type": "choice",
                "instructions": "Which municipal department is responsible for fixing this problem?",
                "criteria": {d["id"]: f"{d['name_en']}: {d['handles']}" for d in taxonomy.departments()},
            },
            "severity": {
                "type": "score",
                "instructions": "How severe is this problem?",
                "criteria": SEVERITY_CRITERIA,
            },
        },
        "session_id": report.interaction_id,
    }


def _call_decisions(payload: dict, settings: Settings) -> dict:
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "X-Title": "PI4C"}
    r = httpx.post(DECISIONS_URL, json=payload, headers=headers, timeout=settings.openrouter_timeout_s)
    if r.is_error:
        log.error("Decisions API %s: %s", r.status_code, r.text[:500])
    r.raise_for_status()
    return r.json()


def _argmax(probabilities: dict) -> tuple[str, float]:
    key = max(probabilities, key=probabilities.get)
    return key, probabilities[key]


def _classify_decisions(report: Report, settings: Settings) -> Classification:
    response = _call_decisions(build_request(report, settings.openrouter_model), settings)
    answers = response["answers"]
    rules = _classify_rules(report)
    threshold = settings.classify_min_confidence

    barrier = answers["barrier_type"]
    valid_subs = {s["id"] for s in taxonomy.category(report.category)["subcategories"]}
    barrier_ok = barrier.get("choice") in valid_subs and barrier.get("confidence", 0) >= threshold
    barrier_type = barrier["choice"] if barrier_ok else report.subcategory

    dept = answers["department"]
    dept_ok = dept.get("choice") in taxonomy.department_ids() and dept.get("confidence", 0) >= threshold
    department_id = dept["choice"] if dept_ok else rules.department_id

    sev = answers["severity"]
    level, _ = _argmax(sev["probabilities"])
    severity = SEVERITIES[int(level)] if sev.get("confidence", 0) >= threshold else rules.severity

    return Classification(
        barrier_type=barrier_type,
        department_id=department_id,
        severity=severity,
        confidence=min(barrier.get("confidence", 0), dept.get("confidence", 0)),
        needs_review=not (barrier_ok and dept_ok),
        method="decisions",
        model=response.get("model", settings.openrouter_model),
        probabilities={
            "barrier_type": barrier.get("probabilities"),
            "department": dept.get("probabilities"),
            "severity": sev.get("probabilities"),
        },
        cost_usd=(response.get("usage") or {}).get("cost"),
    )
