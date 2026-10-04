import json

import pytest

from app.agent import brain


class FakeDB:
    pass


def _tool_call(name, args):
    return {
        "id": f"call-{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


@pytest.mark.asyncio
async def test_hallucinated_money_without_tool_is_blocked():
    async def llm(messages, tools):
        return {"role": "assistant", "content": "Você gastou R$ 9.999,99."}

    result = await brain.run(db=FakeDB(), user_id=1, message="quanto gastei?", llm=llm)

    assert "9.999,99" not in result.response
    assert "reformular" in result.response


@pytest.mark.asyncio
async def test_retry_corrects_hallucination_when_value_is_known(monkeypatch):
    def fake_run_read(spec, db, user_id, args):
        return {"summary": "Total: R$ 123,45"}

    monkeypatch.setattr(brain, "run_read", fake_run_read)

    state = {"n": 0}

    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return {"role": "assistant", "content": None, "tool_calls": [_tool_call("get_summary", {})]}
        state["n"] += 1
        if state["n"] == 1:
            return {"role": "assistant", "content": "Você gastou R$ 999,99."}
        return {"role": "assistant", "content": "Você gastou R$ 123,45."}

    result = await brain.run(db=FakeDB(), user_id=1, message="resumo", llm=llm)

    assert result.response == "Você gastou R$ 123,45."
    assert state["n"] == 2


@pytest.mark.asyncio
async def test_money_from_tool_is_accepted(monkeypatch):
    def fake_run_read(spec, db, user_id, args):
        return {"summary": "Total: R$ 123,45"}

    monkeypatch.setattr(brain, "run_read", fake_run_read)

    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return {"role": "assistant", "content": None, "tool_calls": [_tool_call("get_summary", {})]}
        return {"role": "assistant", "content": "Você gastou R$ 123,45 no total."}

    result = await brain.run(db=FakeDB(), user_id=1, message="resumo", llm=llm)

    assert result.response == "Você gastou R$ 123,45 no total."


@pytest.mark.asyncio
async def test_history_money_is_considered_known():
    async def llm(messages, tools):
        return {"role": "assistant", "content": "Como combinado, R$ 50,00."}

    history = [{"role": "assistant", "content": "O valor é R$ 50,00."}]
    result = await brain.run(
        db=FakeDB(), user_id=1, message="e aí?", llm=llm, history=history
    )

    assert result.response == "Como combinado, R$ 50,00."
