from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
            "app.services.insights.call_claude",
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
            "app.services.insights.call_claude",
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
