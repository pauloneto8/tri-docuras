from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.config import Settings
from app.scripts.generate_insights import _run
from app.services.insights import _build_prompt, _validate, generate_monthly_insight

_SUMMARY = {
    "period_label": "Setembro/2026",
    "income": "R$ 5.000,00",
    "expense": "R$ 3.200,50",
    "balance": "R$ 1.799,50",
    "projected_ending_balance": "R$ 4.100,00",
}
_BUDGETS = [
    {"category": "Lazer", "spent": "R$ 300,00", "limit": "R$ 400,00", "percent_used": 75.0}
]


def test_build_prompt_includes_only_known_values():
    prompt, known = _build_prompt(_SUMMARY, _BUDGETS)

    assert "R$ 5.000,00" in prompt
    assert "Lazer" in prompt
    assert known == {
        "R$ 5.000,00",
        "R$ 3.200,50",
        "R$ 1.799,50",
        "R$ 4.100,00",
        "R$ 300,00",
        "R$ 400,00",
    }


def test_build_prompt_prefixa_valores_sem_simbolo_de_finance():
    """`finance.get_summary` devolve "1.637,46" (sem R$); o insight sai com o prefixo."""
    summary = {
        **_SUMMARY,
        "income": "0,00",
        "expense": "95,60",
        "balance": "-95,60",
        "projected_ending_balance": "1.637,46",
    }
    budgets = [{"category": "Lazer", "spent": "300,00", "limit": "400,00", "percent_used": 75.0}]

    prompt, known = _build_prompt(summary, budgets)

    assert "Receita: R$ 0,00" in prompt
    assert "Saldo do periodo: -R$ 95,60" in prompt
    assert "gasto R$ 300,00 de R$ 400,00" in prompt
    assert known == {
        "R$ 0,00",
        "R$ 95,60",
        "-R$ 95,60",
        "R$ 1.637,46",
        "R$ 300,00",
        "R$ 400,00",
    }


def test_validate_aceita_valor_com_ou_sem_prefixo_de_real():
    _, known = _build_prompt(
        {**_SUMMARY, "income": "1.637,46", "expense": "95,60", "balance": "-95,60"},
        [],
    )

    assert _validate("Sua receita foi R$ 1.637,46 e as despesas 95,60.", known) is True
    assert _validate("Saldo de -R$ 95,60 no mes.", known) is True
    assert _validate("Sobrou R$ 250,00 no mes.", known) is False


def test_validate_accepts_text_with_only_known_values():
    _, known = _build_prompt(_SUMMARY, _BUDGETS)
    text = "Voce recebeu R$ 5.000,00 e gastou R$ 3.200,50 — sobrou R$ 1.799,50 no mes."

    assert _validate(text, known) is True


def test_validate_rejects_invented_value():
    _, known = _build_prompt(_SUMMARY, _BUDGETS)
    text = "Voce ainda tem R$ 999,99 disponiveis este mes."

    assert _validate(text, known) is False


def test_validate_accepts_text_without_money_mentions():
    _, known = _build_prompt(_SUMMARY, _BUDGETS)

    assert _validate("Mes tranquilo, continue assim!", known) is True


@pytest.mark.asyncio
async def test_generate_monthly_insight_noop_when_flag_disabled():
    user = SimpleNamespace(id=1)
    db = MagicMock()

    with patch("app.services.insights.settings") as settings:
        settings.enable_ai_insights = False
        result = await generate_monthly_insight(db, user)

    assert result is None


@pytest.mark.asyncio
async def test_generate_monthly_insight_discards_invalid_value():
    user = SimpleNamespace(id=1)
    db = MagicMock()

    with (
        patch("app.services.insights.settings") as settings,
        patch("app.services.insights.finance.get_summary", return_value=_SUMMARY),
        patch("app.services.insights.finance.get_budget_status", return_value=_BUDGETS),
        patch(
            "app.services.insights.call_groq_text",
            new_callable=AsyncMock,
            return_value="Voce ainda tem R$ 999,99 sobrando.",
        ),
        patch("app.services.insights.save_insight") as save_insight,
    ):
        settings.enable_ai_insights = True
        result = await generate_monthly_insight(db, user, year=2026, month=9)

    assert result is None
    save_insight.assert_not_called()


@pytest.mark.asyncio
async def test_generate_monthly_insight_saves_valid_text():
    user = SimpleNamespace(id=1)
    db = MagicMock()
    saved = MagicMock()

    with (
        patch("app.services.insights.settings") as settings,
        patch("app.services.insights.finance.get_summary", return_value=_SUMMARY),
        patch("app.services.insights.finance.get_budget_status", return_value=_BUDGETS),
        patch(
            "app.services.insights.call_groq_text",
            new_callable=AsyncMock,
            return_value="Voce recebeu R$ 5.000,00 e sobrou R$ 1.799,50.",
        ),
        patch("app.services.insights.save_insight", return_value=saved) as save_insight,
    ):
        settings.enable_ai_insights = True
        result = await generate_monthly_insight(db, user, year=2026, month=9)

    assert result is saved
    save_insight.assert_called_once_with(
        db,
        user_id=1,
        year=2026,
        month=9,
        text="Voce recebeu R$ 5.000,00 e sobrou R$ 1.799,50.",
    )


@pytest.mark.asyncio
async def test_generate_monthly_insight_reserva_max_tokens_para_o_raciocinio():
    """Com 300 o gpt-oss gastava tudo raciocinando e devolvia texto vazio."""
    user = SimpleNamespace(id=1)
    db = MagicMock()

    with (
        patch("app.services.insights.settings") as settings,
        patch("app.services.insights.finance.get_summary", return_value=_SUMMARY),
        patch("app.services.insights.finance.get_budget_status", return_value=_BUDGETS),
        patch(
            "app.services.insights.call_groq_text",
            new_callable=AsyncMock,
            return_value="ok",
        ) as call_groq_text,
        patch("app.services.insights.save_insight"),
    ):
        settings.enable_ai_insights = True
        await generate_monthly_insight(db, user, year=2026, month=9)

    assert call_groq_text.await_args.kwargs["max_tokens"] >= 600


def test_insights_email_set_falls_back_to_root_emails():
    settings = Settings(secret_key="x" * 32, root_emails="root@example.com")

    assert settings.insights_email_set == {"root@example.com"}


def test_insights_email_set_prefers_explicit_list():
    settings = Settings(
        secret_key="x" * 32,
        root_emails="root@example.com",
        insights_emails=" Alvo@Example.com ,outro@example.com ",
    )

    assert settings.insights_email_set == {"alvo@example.com", "outro@example.com"}


@pytest.mark.asyncio
async def test_script_generates_only_for_eligible_emails():
    """Cada insight custa ~2.500 tokens/dia: o job não pode varrer todos os usuários."""
    user = SimpleNamespace(id=1, email="alvo@example.com")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [user]

    with (
        patch("app.scripts.generate_insights.settings") as settings,
        patch("app.scripts.generate_insights.SessionLocal", return_value=db),
        patch(
            "app.scripts.generate_insights.generate_monthly_insight",
            new_callable=AsyncMock,
            return_value=object(),
        ) as generate,
    ):
        settings.enable_ai_insights = True
        settings.groq_api_key = "chave"
        settings.insights_email_set = {"alvo@example.com"}
        await _run()

    where = " ".join(
        str(
            clause.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for clause in db.query.return_value.filter.call_args.args
    )
    assert "alvo@example.com" in where
    generate.assert_awaited_once_with(db, user)


@pytest.mark.asyncio
async def test_script_noop_without_eligible_users():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with (
        patch("app.scripts.generate_insights.settings") as settings,
        patch("app.scripts.generate_insights.SessionLocal", return_value=db),
        patch(
            "app.scripts.generate_insights.generate_monthly_insight",
            new_callable=AsyncMock,
        ) as generate,
    ):
        settings.enable_ai_insights = True
        settings.groq_api_key = "chave"
        settings.insights_email_set = set()
        await _run()

    generate.assert_not_awaited()
