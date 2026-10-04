"""Envia o resumo proativo diário pelos canais vinculados (Fase 6).

Uso no container:

    python -m app.scripts.notify_channels

Cron sugerido no host:

    0 6 * * * docker compose exec -T app2 python -m app.scripts.notify_channels

No-op seguro se não houver vínculos ou se nada relevante aconteceu. Todos os
números vêm de Python; nenhuma escrita acontece aqui.
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import UserChannelLink
from app.services import channels
from app.services.proactive import build_daily_digest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _run() -> None:
    db = SessionLocal()
    sent = 0
    try:
        links = db.scalars(
            select(UserChannelLink).where(UserChannelLink.external_user_id.isnot(None))
        ).all()
        for link in links:
            digest = build_daily_digest(db, link.user_id)
            if not digest:
                continue
            if link.channel == "telegram":
                ok = await channels.send_telegram_message(
                    settings.telegram_bot_token, link.external_user_id, digest
                )
            elif link.channel == "whatsapp":
                ok = await channels.send_whatsapp_message(
                    settings.whatsapp_access_token,
                    settings.whatsapp_phone_number_id,
                    link.external_user_id,
                    digest,
                )
            else:
                ok = False
            if ok:
                sent += 1
        logger.info("Resumos proativos enviados: %s/%s vínculos", sent, len(links))
    finally:
        db.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
