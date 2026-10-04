"""CLI para gerar o insight financeiro proativo do mes (Fase 2 do plano
`.cursor/plans/agente-inteligencia-proativa.md`).

Uso dentro do container:

    python -m app.scripts.generate_insights

Pensado para rodar 1x/dia via cron do host, ex.:

    0 6 * * * docker compose exec -T app2 python -m app.scripts.generate_insights

No-op seguro (sai sem chamar a API) se ENABLE_AI_INSIGHTS estiver desligado
ou sem GROQ_API_KEY configurada — pode ser agendado antes de ativar a
feature.
"""

import asyncio
import logging

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.services.insights import generate_monthly_insight

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _run() -> None:
    if not settings.enable_ai_insights or not settings.groq_api_key.strip():
        logger.info(
            "AI insights desligado (ENABLE_AI_INSIGHTS/GROQ_API_KEY) — nada a fazer."
        )
        return

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active.is_(True)).all()
        generated = 0
        for user in users:
            try:
                insight = await generate_monthly_insight(db, user)
            except Exception:  # noqa: BLE001 — um usuario com erro não pode parar o job
                logger.exception("Falha ao gerar insight para user_id=%s", user.id)
                db.rollback()
                continue
            if insight:
                generated += 1
        db.commit()
        logger.info("Insights gerados: %s/%s usuarios ativos", generated, len(users))
    finally:
        db.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
