"""Language registry. Add a language by adding a messages_<code>.py and label_<code> /
description_<code> fields in data/taxonomy.json."""

from types import ModuleType

from app import messages_en, messages_te

DEFAULT_LANGUAGE = "te"
MESSAGES: dict[str, ModuleType] = {"te": messages_te, "en": messages_en}

# Shown before a language is known, so it's in both
CHOOSE_LANGUAGE = "మీ భాషను ఎంచుకోండి\nPlease choose your language"
LANGUAGE_OPTIONS: list[tuple[str, str]] = [("te", "తెలుగు"), ("en", "English")]


def messages(lang: str | None) -> ModuleType:
    return MESSAGES.get(lang or DEFAULT_LANGUAGE, MESSAGES[DEFAULT_LANGUAGE])


def label(item: dict, lang: str | None, field: str = "label") -> str:
    """Taxonomy text in the resident's language, falling back to Telugu."""
    return item.get(f"{field}_{lang or DEFAULT_LANGUAGE}") or item.get(f"{field}_{DEFAULT_LANGUAGE}", "")
