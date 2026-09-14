from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.orchestrator import looks_like_broad_request, run_orchestrator


class TestLooksLikeBroadRequest:
    def test_detects_broad_review_request(self):
        assert looks_like_broad_request(
            "pode revisar meus gastos desse mes inteiro e sugerir onde eu posso cortar?"
        )

    def test_rejects_short_message(self):
        assert not looks_like_broad_request("revise")

    def test_rejects_message_with_explicit_amount(self):
        assert not looks_like_broad_request(
            "corrige o lancamento de ontem, o valor certo eh 45,90 reais por favor"
        )

    def test_rejects_message_without_broad_verb(self):
        assert not looks_like_broad_request(
            "quanto eu tenho na conta corrente do banco do brasil hoje em dia?"
        )


@pytest.mark.asyncio
async def test_run_orchestrator_returns_none_when_not_configured():
    with patch("app.agent.orchestrator.settings") as mock_settings:
        mock_settings.enable_ai_orchestrator = False
        mock_settings.anthropic_api_key = ""
        result = await run_orchestrator(MagicMock(), 1, "revise meus gastos do mes inteiro")
    assert result is None


@pytest.mark.asyncio
async def test_run_orchestrator_returns_text_without_money_mentions():
    fake_final = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Seus gastos do mes estao dentro do orcamento.")]
    )
    fake_runner = MagicMock()
    fake_runner.until_done = AsyncMock(return_value=fake_final)
    mock_client = MagicMock()
    mock_client.beta.messages.tool_runner.return_value = fake_runner

    with (
        patch("app.agent.orchestrator.settings") as mock_settings,
        patch("app.agent.orchestrator.AsyncAnthropic", return_value=mock_client),
    ):
        mock_settings.enable_ai_orchestrator = True
        mock_settings.anthropic_api_key = "sk-test"
        mock_settings.anthropic_model_reasoning = "claude-sonnet-5"
        result = await run_orchestrator(MagicMock(), 1, "revise meus gastos do mes inteiro")

    assert result == "Seus gastos do mes estao dentro do orcamento."
    mock_client.beta.messages.tool_runner.assert_called_once()
    _, kwargs = mock_client.beta.messages.tool_runner.call_args
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["max_iterations"] == 5
    tool_names = {tool.name for tool in kwargs["tools"]}
    assert tool_names == {
        "list_transactions",
        "get_summary",
        "get_budget_status",
        "list_categories",
        "list_invoices",
    }


@pytest.mark.asyncio
async def test_run_orchestrator_accepts_value_a_tool_actually_returned():
    """Simula o SDK chamando a ferramenta `get_summary` antes da resposta final —
    o valor citado no texto precisa bater com o que a ferramenta devolveu."""

    def fake_tool_runner(**kwargs):
        # `tool_runner(...)` nao e awaited na producao — quem dispara as chamadas
        # de ferramenta e o `await runner.until_done()` a seguir.
        async def _until_done():
            tool = next(t for t in kwargs["tools"] if t.name == "get_summary")
            await tool.func()  # popula known_values via a closure real de execute_tool
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Voce gastou R$ 100,00 no periodo.")]
            )

        fake_runner = MagicMock()
        fake_runner.until_done = AsyncMock(side_effect=_until_done)
        return fake_runner

    mock_client = MagicMock()
    mock_client.beta.messages.tool_runner.side_effect = fake_tool_runner

    with (
        patch("app.agent.orchestrator.settings") as mock_settings,
        patch("app.agent.orchestrator.AsyncAnthropic", return_value=mock_client),
        patch(
            "app.agent.orchestrator.execute_tool",
            return_value={"action": "get_summary", "result": {"expense": "R$ 100,00"}},
        ),
    ):
        mock_settings.enable_ai_orchestrator = True
        mock_settings.anthropic_api_key = "sk-test"
        mock_settings.anthropic_model_reasoning = "claude-sonnet-5"
        result = await run_orchestrator(MagicMock(), 1, "revise meus gastos do mes inteiro")

    assert result == "Voce gastou R$ 100,00 no periodo."


@pytest.mark.asyncio
async def test_run_orchestrator_discards_response_with_unknown_value():
    fake_final = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Voce gastou R$ 999,99 no total.")]
    )
    fake_runner = MagicMock()
    fake_runner.until_done = AsyncMock(return_value=fake_final)
    mock_client = MagicMock()
    mock_client.beta.messages.tool_runner.return_value = fake_runner

    with (
        patch("app.agent.orchestrator.settings") as mock_settings,
        patch("app.agent.orchestrator.AsyncAnthropic", return_value=mock_client),
    ):
        mock_settings.enable_ai_orchestrator = True
        mock_settings.anthropic_api_key = "sk-test"
        mock_settings.anthropic_model_reasoning = "claude-sonnet-5"
        result = await run_orchestrator(MagicMock(), 1, "revise meus gastos do mes inteiro")

    assert result is not None
    assert "R$ 999,99" not in result


@pytest.mark.asyncio
async def test_run_orchestrator_returns_none_on_api_error():
    with (
        patch("app.agent.orchestrator.settings") as mock_settings,
        patch("app.agent.orchestrator.AsyncAnthropic", side_effect=RuntimeError("boom")),
    ):
        mock_settings.enable_ai_orchestrator = True
        mock_settings.anthropic_api_key = "sk-test"
        result = await run_orchestrator(MagicMock(), 1, "revise meus gastos do mes inteiro")

    assert result is None
