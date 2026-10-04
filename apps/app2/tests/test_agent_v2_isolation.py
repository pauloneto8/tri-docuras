from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent import brain, runner


class FakeDB:
    pass


def _brain_result(**overrides):
    result = brain.BrainResult(
        response=overrides.pop("response", "ok"),
        pending_plan=overrides.pop("pending_plan", {}),
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def test_agent_v2_enabled_requires_flag_and_user():
    with patch.object(runner.settings, "enable_agent_v2", True), patch.object(
        runner.settings, "agent_v2_users", "5"
    ):
        assert runner._agent_v2_enabled(5) is True
        assert runner._agent_v2_enabled(6) is False

    with patch.object(runner.settings, "enable_agent_v2", False), patch.object(
        runner.settings, "agent_v2_users", "5"
    ):
        assert runner._agent_v2_enabled(5) is False


@pytest.mark.asyncio
async def test_process_message_v2_passes_user_and_stores_plan():
    session = {}
    result = _brain_result(
        response="Confirma?",
        pending_plan={"actions": [{"tool": "create_category", "arguments": {"name": "X"}}]},
    )
    with patch.object(brain, "run", AsyncMock(return_value=result)) as run_mock:
        response = await runner._process_message_v2(FakeDB(), 42, "crie X", session)

    assert response is not None
    assert response.needs_confirmation
    assert session["agent_v2_plan"]["actions"][0]["tool"] == "create_category"
    assert run_mock.await_args.kwargs["user_id"] == 42


@pytest.mark.asyncio
async def test_process_message_v2_confirm_flow():
    session = {
        "agent_v2_plan": {"actions": [{"tool": "x", "arguments": {}}], "created_at": "2099-01-01T00:00:00Z"}
    }
    with patch("app.agent.confirm.confirm_plan", return_value={"ok": True, "results": [{"ok": True, "message": "feito"}]}) as confirm_mock:
        response = await runner._process_message_v2(FakeDB(), 1, "sim", session)

    assert response.message == "feito"
    assert "agent_v2_plan" not in session
    confirm_mock.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_v2_cancel_flow():
    session = {
        "agent_v2_plan": {"actions": [{"tool": "x", "arguments": {}}], "created_at": "2099-01-01T00:00:00Z"}
    }
    response = await runner._process_message_v2(FakeDB(), 1, "não", session)

    assert "cancelei" in response.message
    assert "agent_v2_plan" not in session


@pytest.mark.asyncio
async def test_process_message_falls_through_when_v2_disabled():
    with patch.object(runner, "_agent_v2_enabled", return_value=False), patch.object(
        runner, "_process_message_v2", AsyncMock()
    ) as v2_mock, patch.object(
        runner, "_resolve_intent", AsyncMock(return_value=(None, "test"))
    ), patch.object(runner, "build_intent_context", MagicMock(return_value={})):
        response = await runner.process_message(FakeDB(), 1, "oi")

    v2_mock.assert_not_awaited()
    assert "Não consegui entender" in response.message


@pytest.mark.asyncio
async def test_process_message_v2_failure_falls_back_to_legacy():
    with patch.object(runner, "_agent_v2_enabled", return_value=True), patch.object(
        brain, "run", AsyncMock(side_effect=RuntimeError("boom"))
    ), patch.object(runner, "_resolve_intent", AsyncMock(return_value=(None, "test"))), patch.object(
        runner, "build_intent_context", MagicMock(return_value={})
    ):
        response = await runner.process_message(FakeDB(), 1, "oi")

    assert "Não consegui entender" in response.message
