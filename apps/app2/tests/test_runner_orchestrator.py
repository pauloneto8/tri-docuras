from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import process_message


@pytest.mark.asyncio
async def test_runner_routes_broad_request_to_orchestrator():
    session = {}
    db = MagicMock()

    with (
        patch("app.agent.runner.orchestrator_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.runner.looks_like_broad_request", return_value=True),
        patch(
            "app.agent.runner.run_orchestrator",
            new_callable=AsyncMock,
            return_value="Voce gastou R$ 100,00 esse mes, dentro do orcamento.",
        ) as run_orchestrator_mock,
        patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as call_intent_llm_mock,
    ):
        result = await process_message(
            db, 1, "pode revisar meus gastos do mes inteiro e sugerir cortes?", session=session
        )

    run_orchestrator_mock.assert_awaited_once_with(db, 1, "pode revisar meus gastos do mes inteiro e sugerir cortes?")
    call_intent_llm_mock.assert_not_awaited()
    assert result.source == "claude-orchestrator"
    assert "R$ 100,00" in result.message


@pytest.mark.asyncio
async def test_runner_falls_back_to_normal_flow_when_orchestrator_returns_none():
    session = {}
    db = MagicMock()
    from app.schemas import ToolCall

    tool = ToolCall(tool="get_summary", arguments={})

    with (
        patch("app.agent.runner.orchestrator_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.runner.looks_like_broad_request", return_value=True),
        patch("app.agent.runner.run_orchestrator", new_callable=AsyncMock, return_value=None),
        patch(
            "app.agent.runner.call_intent_llm",
            new_callable=AsyncMock,
            return_value=(tool, "groq"),
        ),
        patch(
            "app.agent.runner.execute_tool",
            return_value={"action": "get_summary", "result": {}},
        ),
        patch("app.agent.runner.format_tool_result", return_value="Resumo pronto."),
    ):
        result = await process_message(
            db, 1, "pode revisar meus gastos do mes inteiro e sugerir cortes?", session=session
        )

    assert result.source == "groq"
    assert "Resumo" in result.message


@pytest.mark.asyncio
async def test_runner_skips_orchestrator_when_not_configured():
    session = {}
    db = MagicMock()

    with (
        patch("app.agent.runner.orchestrator_configured", new_callable=AsyncMock, return_value=False),
        patch("app.agent.runner.run_orchestrator", new_callable=AsyncMock) as run_orchestrator_mock,
        patch(
            "app.agent.runner.call_intent_llm",
            new_callable=AsyncMock,
            return_value=(None, "groq"),
        ),
        patch("app.agent.runner.try_rule_based_parse", return_value=None),
        patch(
            "app.agent.runner.call_claude_intent_llm",
            new_callable=AsyncMock,
            return_value=(None, "claude-fallback"),
        ),
    ):
        result = await process_message(
            db, 1, "pode revisar meus gastos do mes inteiro e sugerir cortes?", session=session
        )

    run_orchestrator_mock.assert_not_awaited()
    assert "não consegui entender" in result.message.lower()
