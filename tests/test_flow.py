from app import fake_inbound as F
from app import messages_te as M
from app.messenger import OUTBOX
from app import messages_en as EN
from tests.conftest import body, kind, last, report_from_ack, send, start, walk_to_readback


def test_happy_path_creates_report(client):
    walk_to_readback(client, "911000000001")
    send(client, F.reply("911000000001", "rb:confirm"))
    assert "PI4C-" in body(last())

    report = report_from_ack(client)
    assert report["category"] == "accessibility"
    assert report["barrier_type"] == "footpath"
    assert report["pwd_marker"] is True
    assert report["affected"] == "self"
    assert report["department_id"] == "engineering"
    assert report["classifier"] == "rules"
    assert report["readback_outcome"] == "confirmed"
    assert report["cluster_id"] is not None
    assert report["location_name"] == "Bus stand"


def test_typed_numbers_work_like_taps(client):
    wa = "911000000002"
    send(client, F.text(wa, "నమస్కారం"))  # first contact → language question
    send(client, F.text(wa, "1"))  # తెలుగు
    send(client, F.text(wa, "1"))  # first category = accessibility
    assert kind(last()) == "location_request"
    send(client, F.location(wa, 13.0, 80.0))
    assert kind(last()) == "list"
    send(client, F.text(wa, "2"))  # second sub-category = ramp
    assert kind(last()) == "text"
    assert body(last()) == M.DESCRIBE


def test_invalid_input_reprompts_without_advancing(client):
    wa = "911000000003"
    start(client, wa)
    send(client, F.text(wa, "something random"))
    assert kind(last()) == "buttons"
    assert body(last()).startswith(M.CHOOSE_FROM_BUTTONS)


def test_location_is_asked_right_after_menu_with_two_options(client):
    wa = "911000000004"
    start(client, wa)
    send(client, F.reply(wa, "cat:civic"))
    assert kind(last()) == "location_request" and body(last()) == M.LOCATION
    assert [o["title"] for o in last()["options"]] == [M.BTN_SEND_LOCATION, M.BTN_CHOOSE_LOCATION]
    keyboard = last()["payload"]["reply_markup"]["keyboard"]
    assert keyboard[0][0]["request_location"] is True and "request_location" not in keyboard[1][0]


def test_choose_a_location_explains_map_picker(client):
    wa = "911000000015"
    start(client, wa)
    send(client, F.reply(wa, "cat:civic"))
    send(client, F.text(wa, M.BTN_CHOOSE_LOCATION))  # what Telegram sends for the plain keyboard button
    assert kind(last()) == "location_request"
    assert body(last()).startswith(M.CHOOSE_ON_MAP)
    send(client, F.location(wa, 13.01, 80.22, name="Temple", address="North St"))  # place picked on the map
    assert kind(last()) == "list"


def test_location_step_requires_shared_location(client):
    wa = "911000000016"
    start(client, wa)
    send(client, F.reply(wa, "cat:civic"))
    send(client, F.text(wa, "near the temple"))
    assert kind(last()) == "location_request"
    assert body(last()) == M.LOCATION_RETRY


def test_edit_location_returns_to_readback(client):
    wa = "911000000005"
    walk_to_readback(client, wa)
    send(client, F.reply(wa, "rb:edit"))
    assert kind(last()) == "list"
    send(client, F.reply(wa, "edit:location"))
    assert kind(last()) == "location_request"
    send(client, F.location(wa, 13.05, 80.25, name="Market"))
    assert kind(last()) == "buttons" and "Market" in body(last())  # straight back to read-back
    send(client, F.reply(wa, "rb:confirm"))

    report = report_from_ack(client)
    assert report["readback_outcome"] == "edited"
    assert report["edit_count"] == 1
    assert report["latitude"] == 13.05


def test_edit_category_goes_through_subcategory(client):
    wa = "911000000006"
    walk_to_readback(client, wa)
    send(client, F.reply(wa, "rb:edit"))
    send(client, F.reply(wa, "edit:category"))
    send(client, F.reply(wa, "cat:disaster"))
    assert kind(last()) == "list"
    send(client, F.reply(wa, "sub:flooding"))
    assert kind(last()) == "buttons"  # straight back to read-back
    send(client, F.reply(wa, "rb:confirm"))
    report = report_from_ack(client)
    assert report["category"] == "disaster"
    assert report["severity"] == "high"
    assert report["pwd_marker"] is True  # affected=self


def test_cancel(client):
    wa = "911000000007"
    start(client, wa)
    send(client, F.reply(wa, "cat:civic"))
    send(client, F.text(wa, "రద్దు"))
    assert body(last()) == M.CANCELLED


def test_general_problem_has_no_pwd_marker(client):
    wa = "911000000008"
    walk_to_readback(client, wa, category="civic", sub="streetlight", affected="none", lat=12.9, lon=80.1)
    send(client, F.reply(wa, "rb:confirm"))
    report = report_from_ack(client)
    assert report["pwd_marker"] is False
    assert report["department_id"] == "electrical"


def test_voice_note_is_refused_and_text_asked_for(client):
    wa = "911000000009"
    start(client, wa)
    send(client, F.reply(wa, "cat:civic"))
    send(client, F.location(wa, 12.95, 80.2))
    send(client, F.reply(wa, "sub:water"))
    send(client, F.audio(wa))
    assert body(last()) == M.DESCRIBE_RETRY  # still on the describe step
    send(client, F.text(wa, "కుళాయిలో నీళ్లు రావడం లేదు"))
    assert kind(last()) == "buttons"  # photo
    send(client, F.reply(wa, "photo:skip"))
    send(client, F.reply(wa, "aff:caregiver"))
    send(client, F.reply(wa, "rb:confirm"))
    report = report_from_ack(client)
    assert report["description_type"] == "text" and report["media"] == []
    assert report["pwd_marker"] is True


def test_photo_with_caption_skips_photo_step(client):
    wa = "911000000010"
    start(client, wa)
    send(client, F.reply(wa, "cat:accessibility"))
    send(client, F.location(wa, 12.99, 80.21))
    send(client, F.reply(wa, "sub:ramp"))
    send(client, F.image(wa, caption="ramp is broken at the school gate"))
    assert body(last()) == M.AFFECTED  # photo step skipped


def test_duplicate_webhook_delivery_is_processed_once(client):
    payload = F.text("911000000011", "hi")
    send(client, payload)
    send(client, payload)
    assert len(OUTBOX) == 1  # language question sent once


def test_nearby_reports_cluster_together(client):
    walk_to_readback(client, "911000000012", sub="kerb", lat=11.0, lon=77.0)
    send(client, F.reply("911000000012", "rb:confirm"))
    first = report_from_ack(client)

    walk_to_readback(client, "911000000013", sub="kerb", lat=11.00005, lon=77.00005)  # ~7 m away
    send(client, F.reply("911000000013", "rb:confirm"))
    second = report_from_ack(client)

    walk_to_readback(client, "911000000014", sub="kerb", lat=11.01, lon=77.0)  # ~1 km away
    send(client, F.reply("911000000014", "rb:confirm"))
    third = report_from_ack(client)

    assert first["cluster_match"] == "new"
    assert second["cluster_id"] == first["cluster_id"]
    assert second["cluster_match"] == "strict"
    assert third["cluster_id"] != first["cluster_id"]


def test_first_contact_asks_language_and_english_flow(client):
    wa = "911000000020"
    send(client, F.text(wa, "hello"))
    assert [o["id"] for o in last()["options"]] == ["lang:te", "lang:en"]
    send(client, F.reply(wa, "lang:en"))
    assert body(last()) == EN.WELCOME
    assert last()["options"][0]["title"] == "Accessibility issue"
    send(client, F.reply(wa, "cat:accessibility"))
    assert body(last()) == EN.LOCATION
    assert [o["title"] for o in last()["options"]] == ["Live location", "Choose a location"]
    send(client, F.location(wa, 12.9, 80.0))
    assert OUTBOX[-2]["body"] == EN.LOCATION_RECEIVED
    assert last()["options"][1]["title"] == "Ramp"
    send(client, F.reply(wa, "sub:ramp"))
    assert body(last()) == EN.DESCRIBE
    send(client, F.text(wa, "No ramp at the post office"))
    send(client, F.reply(wa, "photo:skip"))
    send(client, F.reply(wa, "aff:none"))
    assert body(last()).startswith("Please check your complaint") and "Accessibility issue, Ramp" in body(last())
    send(client, F.reply(wa, "rb:confirm"))
    assert body(last()).startswith("Thank you!")
    assert report_from_ack(client)["language"] == "en"


def test_language_is_remembered_and_changeable(client):
    wa = "911000000021"
    start(client, wa, "en")
    send(client, F.text(wa, "cancel"))
    assert body(last()) == EN.CANCELLED
    send(client, F.text(wa, "menu"))  # remembered: straight to the menu, in English
    assert body(last()) == EN.WELCOME
    send(client, F.reply(wa, "cat:civic"))
    send(client, F.text(wa, "/language"))  # switch mid-report
    assert last()["options"][0]["id"] == "lang:te"
    send(client, F.reply(wa, "lang:te"))
    assert body(last()) == M.WELCOME
    send(client, F.text(wa, "/start"))  # /start always offers the choice
    assert last()["options"][0]["id"] == "lang:te"
