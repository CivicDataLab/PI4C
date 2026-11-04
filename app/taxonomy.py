import json
from functools import lru_cache

from app.config import get_settings


@lru_cache
def _load(name: str) -> dict:
    return json.loads((get_settings().data_dir / name).read_text(encoding="utf-8"))


def categories() -> list[dict]:
    return _load("taxonomy.json")["categories"]


def category(cat_id: str | None) -> dict | None:
    return next((c for c in categories() if c["id"] == cat_id), None)


def subcategory(cat_id: str | None, sub_id: str | None) -> dict | None:
    cat = category(cat_id)
    if not cat:
        return None
    return next((s for s in cat["subcategories"] if s["id"] == sub_id), None)


def departments() -> list[dict]:
    return _load("departments.json")["departments"]


def department_ids() -> set[str]:
    return {d["id"] for d in departments()}
