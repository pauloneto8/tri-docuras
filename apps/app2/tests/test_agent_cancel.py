from app.services.agent_state import clear_agent_flow_state, is_cancel_message
from app.services.transaction_slots import WIZARD_KEY, ensure_transaction_slots
from app.schemas import ToolCall
from app.services.transaction_wizard import get_wizard, try_process_transaction_wizard


def test_is_cancel_message():
    assert is_cancel_message("cancelar")
    assert is_cancel_message("Cancelar")
    assert not is_cancel_message("gastei 30")


def test_clear_agent_flow_state_removes_transaction_wizard():
    session = {WIZARD_KEY: {"amount": "50", "tx_type": "expense"}}
    clear_agent_flow_state(session)
    assert get_wizard(session) is None


def test_completed_wizard_clears_on_new_message():
    session = {
        WIZARD_KEY: {
            "tx_type": "expense",
            "status": "actual",
            "amount": "50",
            "description": "mercado",
            "account_name": "Nubank",
            "category_name": "Alimentação",
            "source_message": "gastei 50 no mercado",
        }
    }

    result = try_process_transaction_wizard(
        session, "gastei 30 na farmácia", db=None, user_id=None
    )

    assert result is None
    assert get_wizard(session) is None


def test_ensure_transaction_slots_replaces_stale_amount():
    session = {
        WIZARD_KEY: {
            "tx_type": "expense",
            "amount": "50",
            "description": "mercado",
            "account_name": "Nubank",
            "category_name": "Alimentação",
            "source_message": "gastei 50",
        }
    }

    tool_call = ToolCall(
        tool="register_expense",
        arguments={"amount": "30", "description": "farmácia"},
    )

    class FakeUserDb:
        def scalars(self, *args, **kwargs):
            return self

        def all(self):
            return []

    ensure_transaction_slots(
        FakeUserDb(),
        1,
        session,
        tool_call,
        "gastei 30 na farmácia",
    )

    assert session[WIZARD_KEY]["amount"] == "30"
    assert session[WIZARD_KEY]["description"] == "Farmácia"
