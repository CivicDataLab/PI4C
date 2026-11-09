import json

from app import fake_inbound as F
from app.config import get_settings
from app.messenger import OUTBOX
from tests.conftest import READ, WRITE, report_from_ack, send, walk_to_readback


def _make_report(client, chat_id="912000000001", **kw) -> dict:
    walk_to_readback(client, chat_id, **kw)
    send(client, F.reply(chat_id, "rb:confirm"))
    return report_from_ack(client)


def test_read_is_public_but_a_wrong_key_is_rejected(client):
    assert client.get("/api/v1/reports").status_code == 200
    assert client.get("/api/v1/reports", headers=READ).status_code == 200
    # a wrong key is rejected rather than silently treated as public
    assert client.get("/api/v1/reports", headers={"X-API-Key": "nope"}).status_code == 401


def test_read_key_cannot_patch(client):
    report = _make_report(client)
    r = client.patch(f"/api/v1/reports/{report['id']}", json={"status": "acknowledged"}, headers=READ)
    assert r.status_code == 403


def test_patch_status_and_department(client):
    report = _make_report(client, "912000000002")
    r = client.patch(
        f"/api/v1/reports/{report['id']}",
        json={"status": "in_progress", "department_id": "town_planning", "needs_review": False},
        headers=WRITE,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
    assert r.json()["department_id"] == "town_planning"

    bad = client.patch(f"/api/v1/reports/{report['id']}", json={"department_id": "nasa"}, headers=WRITE)
    assert bad.status_code == 422

    log = client.get(f"/api/v1/reports/{report['id']}/log", headers=WRITE).json()
    stages = [e["stage"] for e in log]
    assert "submitted" in stages and "classified" in stages and "api_update" in stages


def test_filters_and_geojson(client):
    _make_report(client, "912000000003", category="civic", sub="drainage", affected="none", lat=10.5, lon=78.5)
    r = client.get("/api/v1/reports", params={"barrier_type": "drainage", "pwd_marker": False}, headers=READ)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all(i["barrier_type"] == "drainage" and not i["pwd_marker"] for i in items)

    box = client.get("/api/v1/reports", params={"bbox": "78.4,10.4,78.6,10.6"}, headers=READ).json()
    assert box["total"] >= 1 and all(10.4 <= i["latitude"] <= 10.6 for i in box["items"])

    geo = client.get("/api/v1/reports.geojson", params={"barrier_type": "drainage"}, headers=READ).json()
    assert geo["type"] == "FeatureCollection"
    assert geo["features"][0]["geometry"]["coordinates"] == [78.5, 10.5]


def test_clusters_stats_metrics_reference(client):
    _make_report(client, "912000000004")
    clusters = client.get("/api/v1/clusters", headers=READ).json()
    assert clusters["total"] >= 1
    detail = client.get(f"/api/v1/clusters/{clusters['items'][0]['id']}", headers=READ).json()
    assert detail["report_ids"]

    assert client.get("/api/v1/stats/by-ward", headers=READ).json()
    assert client.get("/api/v1/stats/by-category", headers=READ).json()
    metrics = client.get("/api/v1/metrics", headers=READ).json()
    assert metrics["reports"] >= 1 and metrics["conversations_started"] >= 1

    assert len(client.get("/api/v1/taxonomy", headers=READ).json()["categories"]) == 3
    assert client.get("/api/v1/departments", headers=READ).json()["departments"]


def test_chat_id_never_exposed(client):
    chat_id = "912000000099"
    report = _make_report(client, chat_id)
    assert chat_id not in json.dumps(report)
    assert report["channel"] == "telegram"


def test_telegram_secret_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "tg-secret")
    payload = F.text("912000000006", "hi")
    assert client.post("/telegram/webhook", json=payload).status_code == 403
    r = client.post("/telegram/webhook", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"})
    assert r.status_code == 200


def test_telegram_ignores_group_and_edited_messages(client):
    group = F.text("-100123", "hi")
    group["message"]["chat"]["type"] = "group"
    edited = {"update_id": 1, "edited_message": F.text("912000000007", "hi")["message"]}
    for update in (group, edited):
        assert client.post("/telegram/webhook", json=update).status_code == 200
    assert OUTBOX == []



def test_write_endpoints_still_need_a_write_key(client):
    report = _make_report(client, "912000000050")
    assert client.get(f"/api/v1/reports/{report['id']}").status_code == 200
    assert client.get("/api/v1/stats/summary").status_code == 200
    assert client.patch(f"/api/v1/reports/{report['id']}", json={"status": "acknowledged"}).status_code == 401
    assert client.get(f"/api/v1/reports/{report['id']}/log").status_code == 401
    assert client.get(f"/api/v1/reports/{report['id']}/log", headers=WRITE).status_code == 200


def test_read_works_without_any_keys_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_keys", "")
    assert client.get("/api/v1/taxonomy").status_code == 200
    assert client.patch("/api/v1/reports/1", json={"status": "acknowledged"}).status_code == 503
