from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app, base_url="http://localhost")


def test_telegram_webhook_rejects_wrong_secret():
    with patch.object(settings, "telegram_webhook_secret", "s3cr3t"):
        resp = client.post(
            "/telegram/webhook/other",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
    assert resp.status_code == 401


def test_telegram_webhook_accepts_matching_header():
    with patch.object(settings, "telegram_webhook_secret", "s3cr3t"):
        resp = client.post(
            "/telegram/webhook/other",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_telegram_webhook_accepts_matching_path():
    with patch.object(settings, "telegram_webhook_secret", "s3cr3t"):
        resp = client.post("/telegram/webhook/s3cr3t", json={"update_id": 1})
    assert resp.status_code == 200


def test_whatsapp_verify_challenge():
    with patch.object(settings, "whatsapp_verify_token", "tok"):
        resp = client.get(
            "/whatsapp/webhook",
            params={
                "hub_mode": "subscribe",
                "hub_challenge": "12345",
                "hub_verify_token": "tok",
            },
        )
    assert resp.status_code == 200
    assert resp.text == "12345"


def test_whatsapp_verify_rejects_bad_token():
    with patch.object(settings, "whatsapp_verify_token", "tok"):
        resp = client.get(
            "/whatsapp/webhook",
            params={
                "hub_mode": "subscribe",
                "hub_challenge": "12345",
                "hub_verify_token": "nope",
            },
        )
    assert resp.status_code == 403


def test_whatsapp_post_is_public():
    resp = client.post("/whatsapp/webhook", json={"entry": []})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
