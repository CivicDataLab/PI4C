"""Photos stored in the database, and the API endpoints external dashboards use."""

import csv
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app import fake_inbound as F
from app import main, media_to_db
from app.db import SessionLocal
from app.models import Media, MediaFile
from tests.conftest import READ, report_from_ack, send, start

PHOTO = b"\xff\xd8\xff\xe0 fake jpeg bytes \xff\xd9"


def _fake_download(monkeypatch, content: bytes = PHOTO):
    def download(media_id, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{media_id}.jpg"
        path.write_bytes(content)
        return path

    monkeypatch.setattr(main.telegram, "download_media", download)


def _report_with_photo(client, chat_id: str, description="ఫుట్‌పాత్ పాడైంది") -> dict:
    start(client, chat_id)
    send(client, F.reply(chat_id, "cat:accessibility"))
    send(client, F.location(chat_id, 17.38, 78.48, name="Bus stand"))
    send(client, F.reply(chat_id, "sub:footpath"))
    send(client, F.text(chat_id, description))
    send(client, F.image(chat_id, file_id=f"photo-{chat_id}"))
    send(client, F.reply(chat_id, "aff:self"))
    send(client, F.reply(chat_id, "rb:confirm"))
    return report_from_ack(client)


def test_photo_is_stored_in_and_served_from_the_database(client, monkeypatch):
    _fake_download(monkeypatch)
    report = _report_with_photo(client, "913000000001")
    [media] = report["media"]

    with SessionLocal() as db:
        row = db.get(Media, media["id"])
        assert row.file.data == PHOTO and row.file.size_bytes == len(PHOTO)
        disk_copy = row.path

    # Served from the database even once the disk copy is gone
    Path(disk_copy).unlink()
    r = client.get(media["url"], headers=READ)
    assert r.status_code == 200 and r.content == PHOTO
    assert r.headers["content-type"] == "image/jpeg" and r.headers["etag"]
    assert client.get(media["url"]).status_code == 401


def test_media_to_db_moves_older_disk_files(client, monkeypatch, tmp_path):
    _fake_download(monkeypatch)
    report = _report_with_photo(client, "913000000002")
    legacy = tmp_path / "legacy.jpg"
    legacy.write_bytes(b"older photo")
    with SessionLocal() as db:
        media = Media(report_id=report["id"], kind="image", mime_type="image/jpeg", path=str(legacy))
        gone = Media(report_id=report["id"], kind="image", mime_type="image/jpeg", path=str(tmp_path / "missing.jpg"))
        db.add_all([media, gone])
        db.commit()
        media_id, gone_id = media.id, gone.id

    url = f"/api/v1/reports/{report['id']}/media/{media_id}"
    assert client.get(url, headers=READ).content == b"older photo"  # disk fallback

    media_to_db.main()
    media_to_db.main()  # second run changes nothing
    with SessionLocal() as db:
        assert db.get(MediaFile, media_id).data == b"older photo"
        assert db.get(MediaFile, gone_id) is None
    legacy.unlink()
    assert client.get(url, headers=READ).content == b"older photo"
    assert client.get(f"/api/v1/reports/{report['id']}/media/{gone_id}", headers=READ).status_code == 404


def test_summary(client, monkeypatch):
    _fake_download(monkeypatch)
    _report_with_photo(client, "913000000003")
    s = client.get("/api/v1/stats/summary", headers=READ).json()
    assert s["reports"] >= 1 and s["with_photo"] >= 1 and s["pwd_marker"] >= 1
    assert s["open"] + s["resolved"] + s["rejected"] == s["reports"]
    assert s["first_report_at"] <= s["last_report_at"]

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    empty = client.get("/api/v1/stats/summary", params={"created_from": future}, headers=READ).json()
    assert empty["reports"] == 0 and empty["first_report_at"] is None


def test_counts_group_by_any_field(client, monkeypatch):
    _fake_download(monkeypatch)
    _report_with_photo(client, "913000000004")
    rows = client.get("/api/v1/stats/counts", params=[("group_by", "status"), ("group_by", "category")], headers=READ).json()
    assert rows and set(rows[0]) == {"status", "category", "count"}
    total = client.get("/api/v1/stats/summary", headers=READ).json()["reports"]
    assert sum(r["count"] for r in rows) == total

    bad = client.get("/api/v1/stats/counts", params={"group_by": "reporter_hash"}, headers=READ)
    assert bad.status_code == 422


def test_timeseries(client, monkeypatch):
    _fake_download(monkeypatch)
    _report_with_photo(client, "913000000005")
    today = datetime.now(timezone.utc).date()
    expected = {
        "day": today,
        "week": today - timedelta(days=today.weekday()),
        "month": today.replace(day=1),
    }
    for interval, period in expected.items():
        rows = client.get("/api/v1/stats/timeseries", params={"interval": interval}, headers=READ).json()
        assert rows[-1]["period"] == period.isoformat(), interval
        assert all(date.fromisoformat(r["period"]) for r in rows)

    split = client.get("/api/v1/stats/timeseries", params={"group_by": "category"}, headers=READ).json()
    assert {"period", "category", "count"} == set(split[0])
    assert client.get("/api/v1/stats/timeseries", params={"interval": "year"}, headers=READ).status_code == 422


def test_csv_export(client, monkeypatch):
    _fake_download(monkeypatch)
    report = _report_with_photo(client, "913000000006", description="ర్యాంప్ లేదు, CSV test")
    r = client.get("/api/v1/reports.csv", headers=READ)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(text.removeprefix("﻿"))))
    assert len(rows) == client.get("/api/v1/stats/summary", headers=READ).json()["reports"]
    row = next(r for r in rows if r["ref"] == report["ref"])
    assert row["description_raw"] == "ర్యాంప్ లేదు, CSV test"
    assert row["photo_count"] == "1" and row["media_urls"] == report["media"][0]["url"]
    assert "media" not in row and "reporter_hash" not in row

    filtered = client.get("/api/v1/reports.csv", params={"category": "disaster"}, headers=READ).content.decode()
    assert report["ref"] not in filtered


def test_cors_for_listed_dashboard_origin_only(client):
    preflight = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-API-Key"}
    ok = client.options("/api/v1/reports", headers={"Origin": "https://dashboard.example", **preflight})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "https://dashboard.example"
    other = client.options("/api/v1/reports", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in other.headers
