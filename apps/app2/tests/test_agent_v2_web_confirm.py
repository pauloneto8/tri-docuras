"""Confirmação do plano do agente v2 pela rota web.

Cobre o que quebrou em produção: o plano pendente vai para o **cookie de
sessão** e, com um `datetime.date` no meio (todo `RegisterExpenseInput` tem),
o `json.dumps` do Starlette estourava — a resposta do chat virava 500 depois de
a mensagem já estar salva no banco. Também trava os botões Confirmar/Cancelar,
que só existiam para o plano do agente legado (`pending_action`).
"""
from __future__ import annotations

import time
import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent import brain
from app.agent.brain import BrainResult
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Account, Transaction, User

client = TestClient(app, base_url="https://localhost")


def _register_ready_user() -> int:
    """Cadastra um usuário já com onboarding concluído e uma conta bancária."""
    email = f"v2web-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/register",
        data={"name": "V2 Web", "email": email, "password": "senha-forte-123"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303), resp.status_code

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.onboarding_completed = True
        user.is_active = True
        db.add(
            Account(
                user_id=user.id,
                name="Conta Teste",
                account_type="corrente",
                opening_balance_cents=0,
                opening_balance_date=date(2026, 1, 1),
            )
        )
        db.commit()
        user_id = user.id
    finally:
        db.close()

    login = client.post(
        "/login",
        data={"email": email, "password": "senha-forte-123"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 303), login.status_code
    return user_id


def _plan(user_id: int) -> BrainResult:
    return BrainResult(
        response="Confirma as duas despesas?",
        pending_plan={
            "actions": [
                {
                    "tool": "register_expense",
                    "arguments": {
                        "amount": "35.00",
                        "description": "ifood",
                        "account_name": "Conta Teste",
                        "category_name": "Alimentação",
                        # `date` de verdade, como sai do `model_dump` do pydantic:
                        # era o que estourava o `json.dumps` do cookie de sessão
                        "transaction_date": date(2026, 10, 4),
                        "payment_date": date(2026, 10, 4),
                    },
                }
            ],
            # o plano expira em 30 min: carimbo a hora agora, senão o teste
            # depende do relógio e cai no caminho "plano expirado"
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        tool_calls=[{"tool": "register_expense", "arguments": {"amount": "35.00"}}],
        metrics={"iterations": 1},
    )


def test_chat_com_plano_pendente_responde_200_e_mostra_botoes(monkeypatch):
    user_id = _register_ready_user()

    async def fake_run(db, user_id, message, channel="web", history=None):
        return _plan(user_id)

    monkeypatch.setattr(brain, "run", fake_run)
    monkeypatch.setattr(settings, "enable_agent_v2", True, raising=False)
    monkeypatch.setattr(settings, "agent_v2_users", str(user_id), raising=False)

    resp = client.post(
        "/agent/chat",
        data={"message": "gastei 35 no ifood ontem na Conta Teste", "confirmed": "false"},
    )

    assert resp.status_code == 200
    assert "Confirmar" in resp.text
    assert "Cancelar" in resp.text
    assert "ifood" in resp.text


def test_botao_confirmar_executa_o_plano_pendente(monkeypatch):
    user_id = _register_ready_user()

    async def fake_run(db, user_id, message, channel="web", history=None):
        return _plan(user_id)

    monkeypatch.setattr(brain, "run", fake_run)
    monkeypatch.setattr(settings, "enable_agent_v2", True, raising=False)
    monkeypatch.setattr(settings, "agent_v2_users", str(user_id), raising=False)

    pending = client.post(
        "/agent/chat",
        data={"message": "gastei 35 no ifood ontem na Conta Teste", "confirmed": "false"},
    )
    assert pending.status_code == 200

    confirmed = client.post(
        "/agent/chat", data={"message": "Confirmar", "confirmed": "false"}
    )

    assert confirmed.status_code == 200
    assert "35" in confirmed.text

    db = SessionLocal()
    try:
        tx = db.scalars(
            select(Transaction).where(Transaction.user_id == user_id)
        ).all()
    finally:
        db.close()
    assert [t.amount_cents for t in tx] == [3500]
    assert tx[0].type == "expense"
    assert tx[0].status == "actual"
    assert tx[0].transaction_date == date(2026, 10, 4)


def test_botao_cancelar_nao_grava_nada(monkeypatch):
    user_id = _register_ready_user()

    async def fake_run(db, user_id, message, channel="web", history=None):
        return _plan(user_id)

    monkeypatch.setattr(brain, "run", fake_run)
    monkeypatch.setattr(settings, "enable_agent_v2", True, raising=False)
    monkeypatch.setattr(settings, "agent_v2_users", str(user_id), raising=False)

    pending = client.post(
        "/agent/chat",
        data={"message": "gastei 35 no ifood ontem na Conta Teste", "confirmed": "false"},
    )
    assert pending.status_code == 200

    cancelled = client.post(
        "/agent/chat", data={"message": "cancelar", "confirmed": "true"}
    )

    assert cancelled.status_code == 200
    db = SessionLocal()
    try:
        total = db.scalars(
            select(Transaction).where(Transaction.user_id == user_id)
        ).all()
    finally:
        db.close()
    assert total == []