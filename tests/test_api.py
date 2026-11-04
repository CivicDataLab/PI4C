import hashlib
import hmac
import json

from app import fake_inbound as F
from app.config import get_settings
from app.messenger import OUTBOX
from tests.conftest import READ, WRITE, report_from_ack, send, walk_to_readback


def _make_report(client, chat_id="912000000001", **kw) -> dict:
    walk_to_readback(client, chat_id, **kw)
    send(client, F.reply(chat_id, "rb:confirm"))
    return report_from_ack(client)


def test_auth_required(client):
    assert client.get("/api/v1/reports").status_code == 401
    assert client.get("/api/v1/reports", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/api/v1/reports", headers=READ).status_code == 200


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


def _wa_text(wa_id: str, text: str) -> dict:
    message = {"from": wa_id, "id": "wamid.test1", "timestamp": "0", "type": "text", "text": {"body": text}}
    return {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": wa_id}], "messages": [message]}}]}]}


def test_whatsapp_webhook_verification(client):
    ok = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_whatsapp_signature_and_flow(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "wa_app_secret", "s3cret")
    raw = json.dumps(_wa_text("919800000001", "hi")).encode()
    headers = {"Content-Type": "application/json"}
    assert client.post("/whatsapp/webhook", content=raw, headers=headers).status_code == 403
    sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
    r = client.post("/whatsapp/webhook", content=raw, headers={**headers, "X-Hub-Signature-256": sig})
    assert r.status_code == 200
    assert OUTBOX[-1]["channel"] == "whatsapp" and OUTBOX[-1]["kind"] == "buttons"
