import re

import httpx

import pytest

from app import classify, geo, i18n, taxonomy
from app.config import Settings
from app.models import Report


@pytest.mark.parametrize("lang", sorted(i18n.MESSAGES))
def test_taxonomy_is_complete(lang):
    for cat in taxonomy.categories():
        for sub in cat["subcategories"]:
            assert sub.get(f"label_{lang}") and sub.get(f"description_{lang}"), (lang, sub["id"])
            assert sub["default_department"] in taxonomy.department_ids(), sub["id"]


def test_languages_define_the_same_strings():
    names = lambda mod: {n for n in vars(mod) if n.isupper() or n in ("readback", "submitted")}
    assert names(i18n.messages("te")) == names(i18n.messages("en"))


@pytest.mark.parametrize("lang", sorted(i18n.MESSAGES))
def test_no_symbols_read_aloud_by_screen_readers(lang):
    """Emoji are announced by name, bullets as "bullet", em dashes often as "em dash"."""
    M = i18n.messages(lang)
    symbols = re.compile("[\U0001F000-\U0001FAFF←-⯿—•️]")
    texts = [v for n, v in vars(M).items() if n.isupper() and isinstance(v, str)]
    texts += [t for n, v in vars(M).items() if n.isupper() and isinstance(v, list) for *_, t in v]
    texts += [M.readback("x", "y", "z", "loc", 1, "a"), M.submitted("R-1")]
    for t in texts:
        assert not symbols.search(t), t


def test_point_in_ward():
    wards = {
        "features": [
            {"properties": {"ward": "W1"}, "geometry": {"type": "Polygon", "coordinates": [[[80, 13], [80.1, 13], [80.1, 13.1], [80, 13.1], [80, 13]]]}}
        ]
    }
    assert geo.find_ward(13.05, 80.05, wards) == "W1"
    assert geo.find_ward(13.5, 80.05, wards) is None
    assert geo.find_ward(13.05, 80.05, {"features": []}) is None


def test_haversine():
    assert geo.haversine_m(13.0, 80.0, 13.0, 80.0) == 0
    assert 1100 < geo.haversine_m(13.0, 80.0, 13.01, 80.0) < 1120


def _report(**kw) -> Report:
    defaults = dict(category="accessibility", subcategory="footpath", description_raw="footpath broken", description_type="text", affected="self")
    return Report(**{**defaults, **kw})


def test_rules_classifier_flags_urgent():
    result = classify.classify_report(_report(description_raw="తెరిచిన మురుగు కాలువ, ప్రమాదం!"), Settings())
    assert result.severity == "high"
    assert result.department_id == "engineering"
    assert result.method == "rules"


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.status_code = status
        self.is_error = status >= 400
        self.text = ""
        self._payload = payload

    def raise_for_status(self):
        if self.is_error:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload


def _decisions(barrier=("ramp", 0.9), dept=("town_planning", 0.85), severity_probs=None, sev_conf=0.9) -> dict:
    severity_probs = severity_probs or {"0": 0.0, "1": 0.1, "2": 0.85, "3": 0.05}
    return {
        "answers": {
            "barrier_type": {"type": "choice", "choice": barrier[0], "confidence": barrier[1], "probabilities": {barrier[0]: barrier[1]}},
            "department": {"type": "choice", "choice": dept[0], "confidence": dept[1], "probabilities": {dept[0]: dept[1]}},
            "severity": {"type": "score", "score": 1.95, "confidence": sev_conf, "probabilities": severity_probs},
        },
        "model": "typesafe/jev-1.14-20261001",
        "usage": {"cost": 0.00002, "input_tokens": 500, "output_tokens": 60},
    }


MODEL_SETTINGS = dict(openrouter_api_key="k", openrouter_model="typesafe/jev-1.14")


def test_decision_request_shape():
    req = classify.build_request(_report(), "typesafe/jev-1.14")
    q = req["questions"]
    assert q["barrier_type"]["type"] == "choice" and "ramp" in q["barrier_type"]["criteria"]
    assert set(q["department"]["criteria"]) == taxonomy.department_ids()
    assert q["severity"]["type"] == "score" and len(q["severity"]["criteria"]) == 4
    assert req["state"]["description"] == "footpath broken"


def test_decisions_answers_are_used(monkeypatch):
    calls = []
    monkeypatch.setattr(classify.httpx, "post", lambda url, **k: calls.append(url) or _FakeResponse(_decisions()))
    result = classify.classify_report(_report(), Settings(**MODEL_SETTINGS))
    assert calls == [classify.DECISIONS_URL]
    assert (result.method, result.barrier_type, result.department_id, result.severity) == ("decisions", "ramp", "town_planning", "high")
    assert result.needs_review is False
    assert result.confidence == 0.85
    assert result.cost_usd == 0.00002


def test_low_confidence_keeps_resident_choice_and_flags(monkeypatch):
    payload = _decisions(barrier=("ramp", 0.4), dept=("town_planning", 0.3), sev_conf=0.2)
    monkeypatch.setattr(classify.httpx, "post", lambda *a, **k: _FakeResponse(payload))
    result = classify.classify_report(_report(), Settings(**MODEL_SETTINGS))
    assert result.barrier_type == "footpath"
    assert result.department_id == "engineering"  # rules default
    assert result.severity == "medium"  # rules
    assert result.needs_review is True


def test_unknown_department_falls_back(monkeypatch):
    payload = _decisions(dept=("nasa", 0.99))
    monkeypatch.setattr(classify.httpx, "post", lambda *a, **k: _FakeResponse(payload))
    result = classify.classify_report(_report(), Settings(**MODEL_SETTINGS))
    assert result.department_id == "engineering" and result.needs_review is True


def test_api_error_falls_back_to_rules(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(classify.httpx, "post", boom)
    result = classify.classify_report(_report(), Settings(**MODEL_SETTINGS))
    assert result.method == "rules" and result.needs_review is True


def test_telegram_parsing():
    from app import fake_inbound as F
    from app.telegram import parse_update

    venue = parse_update(F.location("42", 13.0, 80.0, name="Temple", address="North St"))
    assert (venue.type, venue.location_name, venue.user_id) == ("location", "Temple", "tg:42")
    photo = parse_update(F.image("42", file_id="big", caption="broken"))
    assert (photo.type, photo.media_id, photo.caption) == ("image", "big", "broken")
    tap = parse_update(F.reply("42", "cat:civic"))
    assert (tap.type, tap.reply_id) == ("reply", "cat:civic") and tap.callback_id
    assert parse_update(F.audio("42")).type == "unsupported"  # voice notes aren't accepted


def test_place_search_keeps_only_results_inside_the_city(monkeypatch):
    from app import places
    from app.config import Settings

    items = [
        {"lat": "17.7124", "lon": "83.3030", "name": "Jagadamba Junction", "display_name": "Jagadamba Junction, Dwaraka Nagar, Visakhapatnam, Andhra Pradesh, 530020, India",
         "address": {"suburb": "Dwaraka Nagar", "city": "Visakhapatnam", "state": "Andhra Pradesh", "country": "India"}},
        {"lat": "17.7124", "lon": "83.3030", "name": "Jagadamba Junction", "display_name": "duplicate",
         "address": {"suburb": "Dwaraka Nagar", "city": "Visakhapatnam"}},
        {"lat": "17.4375", "lon": "78.4483", "name": "Ameerpet", "display_name": "Ameerpet, Hyderabad, Telangana, India", "address": {}},
    ]
    seen = {}

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return items

    def fake_get(url, params, headers, timeout):
        seen.update(url=url, params=params)
        return Resp()

    monkeypatch.setattr(places.httpx, "get", fake_get)
    monkeypatch.setattr(places, "_wait_for_nominatim", lambda: None)
    found = places.search("jagadamba", Settings(locationiq_api_key="k"), "te")
    assert found == [places.Place("Jagadamba Junction", "Dwaraka Nagar, Visakhapatnam", 17.7124, 83.3030)]
    assert seen["url"] == places.LOCATIONIQ_URL
    assert seen["params"]["bounded"] == 1 and seen["params"]["key"] == "k" and seen["params"]["accept-language"] == "te"


def test_place_search_failure_returns_none(monkeypatch):
    from app import places
    from app.config import Settings

    def boom(*a, **k):
        raise places.httpx.ConnectError("down")

    monkeypatch.setattr(places.httpx, "get", boom)
    monkeypatch.setattr(places, "_wait_for_nominatim", lambda: None)
    assert places.search("x", Settings(locationiq_api_key=""), "en") is None
