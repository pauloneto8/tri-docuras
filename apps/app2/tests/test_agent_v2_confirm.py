from datetime import datetime, timedelta, timezone

from app.agent import confirm


def _plan():
    return {
        "actions": [
            {"tool": "create_category", "arguments": {"name": "Pets", "type": "expense"}},
            {"tool": "register_expense", "arguments": {"description": "Ração", "amount": "35.90"}},
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_confirm_plan_executes_all_actions(monkeypatch):
    executed = []

    def fake_execute(db, user_id, tool_call):
        executed.append((user_id, tool_call.tool, tool_call.arguments))
        return {"action": tool_call.tool, "result": {"ok": True}}

    monkeypatch.setattr(confirm, "execute_tool", fake_execute)
    monkeypatch.setattr(confirm, "format_tool_result", lambda action, result: f"feito:{action}")

    outcome = confirm.confirm_plan(object(), 5, _plan())

    assert outcome["ok"] is True
    assert [e[1] for e in executed] == ["create_category", "register_expense"]
    assert all(e[0] == 5 for e in executed)
    assert [r["message"] for r in outcome["results"]] == [
        "feito:create_category",
        "feito:register_expense",
    ]


def test_confirm_plan_continues_after_failure(monkeypatch):
    def fake_execute(db, user_id, tool_call):
        if tool_call.tool == "create_category":
            raise ValueError("categoria duplicada")
        return {"action": tool_call.tool, "result": {"ok": True}}

    monkeypatch.setattr(confirm, "execute_tool", fake_execute)
    monkeypatch.setattr(confirm, "format_tool_result", lambda action, result: "ok")

    outcome = confirm.confirm_plan(object(), 1, _plan())

    assert outcome["ok"] is False
    assert outcome["results"][0]["ok"] is False
    assert outcome["results"][1]["ok"] is True


def test_confirm_plan_empty_returns_error():
    outcome = confirm.confirm_plan(object(), 1, {"actions": []})
    assert outcome["ok"] is False
    assert outcome["results"] == []


def test_cancel_plan():
    assert confirm.cancel_plan(object(), 1, _plan()) == {"ok": True, "cancelled": True}


def test_is_expired():
    fresh = {"created_at": datetime.now(timezone.utc).isoformat()}
    old = {
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    }
    assert confirm.is_expired(fresh) is False
    assert confirm.is_expired(old) is True
    assert confirm.is_expired({}) is False
