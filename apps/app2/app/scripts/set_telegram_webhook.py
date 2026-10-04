"""Registra/consulta/remove o webhook do Telegram (Fase 4).

Uso no container:

    python -m app.scripts.set_telegram_webhook            # setWebhook
    python -m app.scripts.set_telegram_webhook --info     # getWebhookInfo
    python -m app.scripts.set_telegram_webhook --delete   # deleteWebhook

A URL base vem de APP2_PUBLIC_BASE_URL (default https://assistfin.com.br).
No-op seguro se APP2_TELEGRAM_BOT_TOKEN estiver vazio.
"""

import argparse
import asyncio
import json
import logging
import os

import httpx

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://assistfin.com.br"


def _base_url() -> str:
    return os.environ.get("APP2_PUBLIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


async def _call(method: str, token: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        if payload is None:
            response = await client.get(url)
        else:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def _run(args: argparse.Namespace) -> None:
    token = settings.telegram_bot_token.strip()
    if not token:
        logger.info("APP2_TELEGRAM_BOT_TOKEN vazio — nada a fazer.")
        return

    if args.info:
        data = await _call("getWebhookInfo", token)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.delete:
        data = await _call("deleteWebhook", token, {"drop_pending_updates": False})
        logger.info("deleteWebhook: %s", data)
        return

    secret = settings.telegram_webhook_secret.strip()
    path_secret = secret or token
    url = f"{_base_url()}/telegram/webhook/{path_secret}"
    payload: dict = {
        "url": url,
        "allowed_updates": ["message", "edited_message", "callback_query"],
    }
    if secret:
        payload["secret_token"] = secret
    data = await _call("setWebhook", token, payload)
    logger.info("setWebhook %s -> %s", url, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Webhook do Telegram do AssistFin")
    parser.add_argument("--info", action="store_true", help="getWebhookInfo")
    parser.add_argument("--delete", action="store_true", help="deleteWebhook")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
