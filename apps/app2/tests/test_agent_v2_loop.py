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


def _msg(content=None, tool_calls=None):
    payload = {"role": "assistant", "content": content}
    if tool_calls:
        payload["tool_calls"] = tool_calls
    return payload


@pytest.mark.asyncio
async def test_plain_response_without_tools():
    async def llm(messages, tools):
        return _msg("Olá! Posso ajudar com suas finanças.")

    result = await brain.run(db=FakeDB(), user_id=1, message="oi", llm=llm)

    assert result.response.startswith("Olá!")
    assert result.pending_plan == {}
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_read_tool_executed_then_answer(monkeypatch):
    calls = {"n": 0}

    def fake_run_read(spec, db, user_id, args):
        calls["n"] += 1
        assert user_id == 7
        return {"accounts": [{"name": "Conta", "balance": "R$ 10,00"}]}

    monkeypatch.setattr(brain, "run_read", fake_run_read)

    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return _msg(None, [_tool_call("list_accounts", {})])
        return _msg("Você tem R$ 10,00 na conta.")

    result = await brain.run(db=FakeDB(), user_id=7, message="saldo?", llm=llm)

    assert calls["n"] == 1
    assert result.response == "Você tem R$ 10,00 na conta."
    assert result.tool_calls[0]["tool"] == "list_accounts"


@pytest.mark.asyncio
async def test_write_tool_becomes_pending_plan(monkeypatch):
    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return _msg(
                "Vou criar.",
                [_tool_call("create_category", {"name": "Pets", "type": "expense"})],
            )
        return _msg("Confirma a criação da categoria?")

    result = await brain.run(
        db=FakeDB(), user_id=1, message="crie categoria Pets", llm=llm
    )

    assert result.needs_confirmation
    actions = result.pending_plan["actions"]
    assert actions == [
        {"tool": "create_category", "arguments": {"name": "Pets", "type": "expense"}}
    ]
    assert result.pending_plan["created_at"]


@pytest.mark.asyncio
async def test_plano_com_data_sobe_serializavel_em_json():
    """O plano pendente vai para o cookie de sessão e para o JSONB do canal.

    `RegisterExpenseInput` tem campos `date`, e o `model_dump` do pydantic
    devolve `datetime.date` — com um deles dentro, `json.dumps` da sessão
    estourava e a resposta do chat virava 500 (a mensagem já ficava salva no
    banco, então o usuário só via o erro).
    """
    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return _msg(
                None,
                [
                    _tool_call(
                        "register_expense",
                        {
                            "amount": "35.00",
                            "description": "ifood",
                            "card_name": "Ourocard",
                            "transaction_date": "2026-10-04",
                            "payment_date": "2026-10-04",
                        },
                    )
                ],
            )
        return _msg("Confirma?")

    result = await brain.run(
        db=FakeDB(), user_id=1, message="gastei 35 no ifood ontem", llm=llm
    )

    assert result.needs_confirmation
    assert json.loads(json.dumps(result.pending_plan)) == result.pending_plan
    argumentos = result.pending_plan["actions"][0]["arguments"]
    assert argumentos["transaction_date"] == "2026-10-04"
    assert argumentos["payment_date"] == "2026-10-04"


@pytest.mark.asyncio
async def test_invalid_write_arguments_are_reported_back(monkeypatch):
    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return _msg(None, [_tool_call("create_category", {"type": "expense"})])
        tool_content = next(
            m["content"] for m in messages if m.get("role") == "tool"
        )
        return _msg(tool_content)

    result = await brain.run(
        db=FakeDB(), user_id=1, message="crie categoria", llm=llm
    )

    assert not result.needs_confirmation
    assert "error" in result.response


@pytest.mark.asyncio
async def test_duplicate_read_not_executed_twice(monkeypatch):
    calls = {"n": 0}

    def fake_run_read(spec, db, user_id, args):
        calls["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(brain, "run_read", fake_run_read)

    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return _msg(None, [_tool_call("list_accounts", {}), _tool_call("list_accounts", {})])
        return _msg("pronto")

    await brain.run(db=FakeDB(), user_id=1, message="x", llm=llm)

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_and_loop_continues(monkeypatch):
    async def llm(messages, tools):
        if not any(m.get("role") == "tool" for m in messages):
            return _msg(None, [_tool_call("does_not_exist", {})])
        return _msg("não conheço essa ferramenta")

    result = await brain.run(db=FakeDB(), user_id=1, message="x", llm=llm)

    assert result.response == "não conheço essa ferramenta"


@pytest.mark.asyncio
async def test_iteration_limit_without_answer_falls_back(monkeypatch):
    monkeypatch.setattr(brain, "MAX_TOOL_CONTENT_CHARS", 100)

    async def llm(messages, tools):
        return _msg(None, [_tool_call("list_accounts", {})])

    def fake_run_read(spec, db, user_id, args):
        return {"ok": True}

    monkeypatch.setattr(brain, "run_read", fake_run_read)

    result = await brain.run(
        db=FakeDB(), user_id=1, message="x", llm=llm, max_iterations=3
    )

    assert result.response
    assert result.metrics["iterations"] == 3


@pytest.mark.asyncio
async def test_metrics_somam_tokens_de_cada_iteracao(monkeypatch):
    """O custo da mensagem é a soma das chamadas: o orçamento do Groq free é por token."""
    def fake_run_read(spec, db, user_id, args):
        return {"ok": True}

    monkeypatch.setattr(brain, "run_read", fake_run_read)

    async def llm(messages, tools):
        reply = _msg(None, [_tool_call("list_accounts", {})]) if not any(
            m.get("role") == "tool" for m in messages
        ) else _msg("pronto")
        reply["usage"] = {
            "prompt_tokens": 3200,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 3000},
        }
        return reply

    result = await brain.run(db=FakeDB(), user_id=1, message="x", llm=llm)

    tokens = result.metrics["tokens"]
    assert tokens["prompt"] == 6400
    assert tokens["completion"] == 200
    assert tokens["cached"] == 6000
    assert tokens["total"] == 6600


@pytest.mark.asyncio
async def test_metrics_tokens_zerado_sem_usage():
    async def llm(messages, tools):
        return _msg("oi")

    result = await brain.run(db=FakeDB(), user_id=1, message="x", llm=llm)

    assert result.metrics["tokens"] == {
        "prompt": 0,
        "completion": 0,
        "cached": 0,
        "total": 0,
    }
