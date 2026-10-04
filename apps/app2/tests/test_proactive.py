from unittest.mock import MagicMock, patch

from app.services.proactive import build_daily_digest


def _db():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    return db


def test_digest_none_when_nothing_relevant():
    db = _db()
    with patch("app.services.finance.get_budget_status", return_value=[]), patch(
        "app.services.agent_reads.list_upcoming_bills",
        return_value={"planned_expenses": [], "card_invoices": []},
    ):
        assert build_daily_digest(db, 1) is None


def test_digest_includes_budget_alert_and_bill():
    db = _db()
    budgets = [
        {"category": "Lazer", "spent": "R$ 360,00", "limit": "R$ 400,00", "percent_used": 90.0},
        {"category": "Casa", "spent": "R$ 10,00", "limit": "R$ 400,00", "percent_used": 2.5},
    ]
    with patch("app.services.finance.get_budget_status", return_value=budgets), patch(
        "app.services.agent_reads.list_upcoming_bills",
        return_value={
            "planned_expenses": [
                {"description": "Luz", "amount": "R$ 120,00", "transaction_date": "2026-10-05"}
            ],
            "card_invoices": [],
        },
    ):
        text = build_daily_digest(db, 1)

    assert text.startswith("Bom dia!")
    assert "Luz" in text
    assert "Lazer" in text
    assert "Casa" not in text
