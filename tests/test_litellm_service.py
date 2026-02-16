"""
Quick tests for the LiteLLM service (chat completions non-stream and stream).
Uses mocks so no real API keys or network calls are required.

Run from project root (after installing deps + pytest, pytest-asyncio, httpx):
  python -m pytest tests/test_litellm_service.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from llm.litellmService import LiteLLMService, _response_to_dict


@pytest.fixture
def app():
    with patch("base.util.Util.set_api_key_for_llm"):
        service = LiteLLMService()
        return service.app


@pytest.mark.asyncio
async def test_response_to_dict_model_dump():
    """_response_to_dict uses model_dump when available (Pydantic v2)."""
    obj = MagicMock()
    obj.model_dump.return_value = {"choices": [{"message": {"content": "hi"}}]}
    del obj.to_json
    assert _response_to_dict(obj) == {"choices": [{"message": {"content": "hi"}}]}
    obj.model_dump.assert_called_once_with(exclude_none=True)


@pytest.mark.asyncio
async def test_response_to_dict_to_json():
    """_response_to_dict falls back to to_json when model_dump is missing."""
    obj = MagicMock()
    del obj.model_dump  # no model_dump (e.g. Pydantic v1)
    obj.to_json.return_value = '{"foo": "bar"}'
    assert _response_to_dict(obj) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_chat_completions_non_stream(app):
    """POST /v1/chat/completions with stream=False returns JSON with choices."""
    mock_response = MagicMock()
    mock_response.model_dump.return_value = {
        "id": "test-id",
        "object": "chat.completion",
        "model": "test-model",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
        ],
    }
    mock_response.to_json.side_effect = AttributeError

    with patch("llm.litellmService.acompletion", new_callable=AsyncMock) as m:
        m.return_value = mock_response

        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                },
            )

    assert r.status_code == 200
    data = r.json()
    assert "choices" in data
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["content"] == "Hello"


@pytest.mark.asyncio
async def test_chat_completions_stream(app):
    """POST /v1/chat/completions with stream=True collects chunks and returns rebuilt JSON."""
    # One chunk that stream_chunk_builder can turn into a full response
    chunk = MagicMock()
    chunk.model_dump.return_value = {
        "id": "chunk-1",
        "object": "chat.completion.chunk",
        "model": "test",
        "choices": [{"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}],
    }

    async def stream_chunks():
        yield chunk

    with patch("llm.litellmService.acompletion", new_callable=AsyncMock) as m:
        m.return_value = stream_chunks()

        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            )

    assert r.status_code == 200
    data = r.json()
    # stream_chunk_builder produces a full completion-shaped response
    assert "choices" in data
