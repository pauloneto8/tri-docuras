import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _deterministic_agent_flags(monkeypatch):
    """Mantém a suíte independente do .env de produção.

    Sem isso, ligar ENABLE_AGENT_V2/AGENT_V2_USERS no host faria testes que
    chamam process_message(db, 1, ...) desviarem para o motor v2.
    """
    monkeypatch.setattr(settings, "enable_agent_v2", False, raising=False)
    monkeypatch.setattr(settings, "agent_v2_users", "", raising=False)
