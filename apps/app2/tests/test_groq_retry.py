import httpx
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent import brain, runner
from app.agent.groq import (
    BACKOFF_BASE_SECONDS,
    MAX_ATTEMPTS,
    MAX_BACKOFF_SECONDS,
    GroqRateLimitError,
    _post_json,
    _retry_delay,
)

CHAT = {"choices": [{"message": {"content": "ok"}}]}


def _client(responses: list[httpx.Response]) -> tuple[httpx.AsyncClient, list[int]]:
    """AsyncClient com MockTransport (sem rede) que devolve as respostas na ordem."""
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return responses.pop(0)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


def _429(headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(429, json={"error": "rate limit"}, headers=headers or {})


def _record_sleeps(monkeypatch) -> list[float]:
    """Substitui asyncio.sleep por um recorder async (não espera de verdade)."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.agent.groq.asyncio.sleep", fake_sleep)
    return sleeps


@pytest.mark.asyncio
async def test_429_then_200_succeeds(monkeypatch):
    """429 followed by 200 must succeed on the second attempt."""
    sleeps = _record_sleeps(monkeypatch)

    client, calls = _client([_429(), httpx.Response(200, json=CHAT)])
    async with client:
        data = await _post_json(client, {"model": "x", "messages": []})

    assert data == CHAT
    assert len(calls) == 2
    assert len(sleeps) == 1


@pytest.mark.asyncio
async def test_retry_after_header_is_respected(monkeypatch):
    """Retry-After wins over the exponential backoff, capped at MAX_BACKOFF_SECONDS."""
    sleeps = _record_sleeps(monkeypatch)

    client, _ = _client([_429({"retry-after": "7"}), httpx.Response(200, json=CHAT)])
    async with client:
        await _post_json(client, {"model": "x", "messages": []})

    assert sleeps == [7.0]


@pytest.mark.asyncio
async def test_retry_after_above_ceiling_is_capped(monkeypatch):
    """A Retry-After larger than the ceiling does not block the agent for minutes."""
    sleeps = _record_sleeps(monkeypatch)

    client, _ = _client([_429({"retry-after": "600"}), httpx.Response(200, json=CHAT)])
    async with client:
        await _post_json(client, {"model": "x", "messages": []})

    assert sleeps == [MAX_BACKOFF_SECONDS]


def test_retry_delay_defaults_to_exponential_backoff():
    response = httpx.Response(429)
    assert _retry_delay(response, 0) == BACKOFF_BASE_SECONDS
    assert _retry_delay(response, 1) == BACKOFF_BASE_SECONDS * 2
    assert _retry_delay(response, 9) == MAX_BACKOFF_SECONDS


def test_retry_delay_ignores_invalid_retry_after():
    assert _retry_delay(httpx.Response(429, headers={"retry-after": "depois"}), 0) == (
        BACKOFF_BASE_SECONDS
    )


@pytest.mark.asyncio
async def test_persistent_429_raises_rate_limit_error_after_all_attempts(monkeypatch):
    """Exhausted retries on 429 raise GroqRateLimitError after MAX_ATTEMPTS calls."""
    sleeps = _record_sleeps(monkeypatch)

    client, calls = _client([_429() for _ in range(MAX_ATTEMPTS + 2)])
    async with client:
        with pytest.raises(GroqRateLimitError) as excinfo:
            await _post_json(client, {"model": "x", "messages": []})

    assert excinfo.value.response.status_code == 429
    assert len(calls) == MAX_ATTEMPTS
    # No sleep after the last attempt.
    assert len(sleeps) == MAX_ATTEMPTS - 1
    assert sum(sleeps) <= MAX_BACKOFF_SECONDS * (MAX_ATTEMPTS - 1)


@pytest.mark.asyncio
async def test_persistent_500_raises_plain_status_error(monkeypatch):
    """5xx exhausted keeps the generic HTTPStatusError (visible in logs as an error)."""
    _record_sleeps(monkeypatch)

    client, calls = _client(
        [httpx.Response(503, json={}) for _ in range(MAX_ATTEMPTS)]
    )
    async with client:
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await _post_json(client, {"model": "x", "messages": []})

    assert not isinstance(excinfo.value, GroqRateLimitError)
    assert len(calls) == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_non_retryable_error_is_raised_immediately(monkeypatch):
    """400 is not in RETRY_STATUS: fail fast, without retrying."""
    sleeps = _record_sleeps(monkeypatch)

    client, calls = _client([httpx.Response(400, json={"error": "bad request"})])
    async with client:
        with pytest.raises(httpx.HTTPStatusError):
            await _post_json(client, {"model": "x", "messages": []})

    assert len(calls) == 1
    assert sleeps == []

def _rate_limit_error() -> GroqRateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return GroqRateLimitError("429 do Groq", request=request, response=response)


class _FakeDB:
    pass


@pytest.mark.asyncio
async def test_rate_limit_falls_back_without_error_log(caplog):
    """Exhausted 429 returns None (legacy fallback) and logs warning, not ERROR."""
    with caplog.at_level(logging.WARNING, logger="app.agent.runner"):
        with patch.object(brain, "run", AsyncMock(side_effect=_rate_limit_error())):
            result = await runner._process_message_v2(_FakeDB(), 1, "oi", {})

    assert result is None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == []
    assert not any("Traceback" in r.getMessage() for r in caplog.records)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings and "429" in warnings[0].getMessage()
    assert str(MAX_ATTEMPTS) in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_unexpected_error_still_logs_traceback(caplog):
    """Genuine bugs keep logger.exception — only rate limit is downgraded."""
    with caplog.at_level(logging.ERROR, logger="app.agent.runner"):
        with patch.object(brain, "run", AsyncMock(side_effect=RuntimeError("boom"))):
            result = await runner._process_message_v2(_FakeDB(), 1, "oi", {})

    assert result is None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors
    assert errors[0].exc_info is not None
    assert isinstance(errors[0].exc_info[1], RuntimeError)


@pytest.mark.asyncio
async def test_user_gets_normal_answer_on_rate_limit():
    """End to end: persistent 429 answers through the legacy pipeline, never 500."""
    with patch.object(runner, "_agent_v2_enabled", return_value=True), patch.object(
        brain, "run", AsyncMock(side_effect=_rate_limit_error())
    ), patch.object(
        runner, "_resolve_intent", AsyncMock(return_value=(None, "test"))
    ), patch.object(
        runner, "build_intent_context", MagicMock(return_value={})
    ):
        response = await runner.process_message(_FakeDB(), 1, "oi")

    assert "Não consegui entender" in response.message
