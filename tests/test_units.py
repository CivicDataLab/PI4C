import re


import pytest

from app import classify, geo, i18n, taxonomy
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
    result = classify.classify_report(_report(description_raw="తెరిచిన మురుగు కాలువ, ప్రమాదం!"))
    assert result.severity == "high"
    assert result.department_id == "engineering"
    assert result.method == "rules"


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


def test_place_search_is_not_limited_to_one_area(monkeypatch):
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
    found = places.search("jagadamba", Settings(), "te")
    assert found == [
        places.Place("Jagadamba Junction", "Dwaraka Nagar, Visakhapatnam", 17.7124, 83.3030),  # duplicate dropped
        places.Place("Ameerpet", "Hyderabad, Telangana", 17.4375, 78.4483),  # other cities are kept
    ]
    assert seen["url"] == places.NOMINATIM_URL
    assert "viewbox" not in seen["params"] and "bounded" not in seen["params"]
    assert "key" not in seen["params"] and seen["params"]["accept-language"] == "te"


def test_place_address_names_the_city():
    from app import places

    item = {"name": "Bus Stand", "display_name": "Bus Stand, ...",
            "address": {"road": "MG Road", "neighbourhood": "Old Town", "suburb": "Ward 5", "city": "Guntur"}}
    assert places._place(item, 16.3, 80.4).address == "MG Road, Old Town, Guntur"


def test_place_search_failure_returns_none(monkeypatch):
    from app import places
    from app.config import Settings

    def boom(*a, **k):
        raise places.httpx.ConnectError("down")

    monkeypatch.setattr(places.httpx, "get", boom)
    monkeypatch.setattr(places, "_wait_for_nominatim", lambda: None)
    assert places.search("x", Settings(), "en") is None


def test_reporter_hash_secret_is_generated_once_and_kept_in_the_database(client):
    from app import audit
    from app.db import SessionLocal, init_db
    from app.models import AppSecret

    with SessionLocal() as db:
        secret = db.get(AppSecret, audit.REPORTER_HASH_SECRET).value  # created on startup
        assert len(secret) >= 32
        first = audit.reporter_hash(db, "tg:123")

    init_db()  # a restart keeps the same secret
    with SessionLocal() as db:
        assert db.get(AppSecret, audit.REPORTER_HASH_SECRET).value == secret
        assert audit.reporter_hash(db, "tg:123") == first  # same resident, same hash
        assert audit.reporter_hash(db, "tg:456") != first
        assert len(first) == 32 and all(c in "0123456789abcdef" for c in first)  # hex, not the chat ID
