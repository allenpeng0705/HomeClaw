"""Panda Gateway URL routing when panda.enabled is true (see config/llm.yml panda:)."""

import pytest

from base.util import Util


@pytest.fixture
def util_with_panda(monkeypatch):
    # Avoid importing torch in has_gpu_cuda during Util(); sandbox may abort on torch load.
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    Util._instance = None
    u = Util()

    class _Meta:
        panda = {
            "enabled": True,
            "host": "10.0.1.2",
            "port": 9090,
            "paths": {
                "main_llm": "/v1/chat",
                "cloud_llm": "/v1/cloud",
                "embedding": "/v1/embeddings",
            },
            "timeout_seconds": 45,
        }

    monkeypatch.setattr(u, "core_metadata", _Meta())
    return u


def test_panda_openai_chat_urls(util_with_panda):
    u = util_with_panda
    assert u.panda_openai_chat_url("local") == "http://10.0.1.2:9090/v1/chat"
    assert u.panda_openai_chat_url("ollama") == "http://10.0.1.2:9090/v1/chat"
    assert u.panda_openai_chat_url("litellm") == "http://10.0.1.2:9090/v1/cloud"


def test_panda_embedding_and_completions_urls(util_with_panda):
    u = util_with_panda
    assert u.panda_openai_embedding_url() == "http://10.0.1.2:9090/v1/embeddings"
    assert u.panda_openai_completions_url() == "http://10.0.1.2:9090/v1/completions"
    assert u.panda_ollama_embed_url() == "http://10.0.1.2:9090/api/embed"


def test_panda_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    Util._instance = None
    u = Util()

    class _Meta:
        panda = {"enabled": False}

    monkeypatch.setattr(u, "core_metadata", _Meta())
    assert u.panda_openai_chat_url("litellm") is None
    assert u.panda_openai_embedding_url() is None


def test_panda_http_timeout_override(util_with_panda):
    assert util_with_panda.panda_http_timeout_seconds() == 45
    t = util_with_panda._client_timeout_for_llm_http()
    assert t.total == 45
