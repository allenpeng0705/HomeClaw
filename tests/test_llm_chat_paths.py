"""main_llm_chat_path / cloud_llm_chat_path for direct (non-Panda) chat completion URLs."""

import pytest

from base.util import Util


@pytest.fixture
def util_paths(monkeypatch):
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    Util._instance = None
    u = Util()

    class _Meta:
        main_llm_chat_path = "/v1/chat/completions"
        cloud_llm_chat_path = "/cloud/v1/chat/completions"

    monkeypatch.setattr(u, "core_metadata", _Meta())
    return u


def test_openai_chat_completions_path_local_vs_cloud(util_paths):
    u = util_paths
    assert u.openai_chat_completions_path("local") == "/v1/chat/completions"
    assert u.openai_chat_completions_path("ollama") == "/v1/chat/completions"
    assert u.openai_chat_completions_path("litellm") == "/cloud/v1/chat/completions"


def test_openai_chat_completions_path_strips_and_prefixes_slash(monkeypatch):
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    Util._instance = None
    u = Util()

    class _Meta:
        main_llm_chat_path = "custom/chat"
        cloud_llm_chat_path = ""

    monkeypatch.setattr(u, "core_metadata", _Meta())
    assert u.openai_chat_completions_path("local") == "/custom/chat"
    assert u.openai_chat_completions_path("litellm") == "/v1/chat/completions"


def test_normalize_llm_chat_path_from_base():
    from base.base import _normalize_llm_chat_path

    assert _normalize_llm_chat_path(None) == "/v1/chat/completions"
    assert _normalize_llm_chat_path("x/y") == "/x/y"
    assert _normalize_llm_chat_path("/z") == "/z"


def test_coerce_grammar_drops_for_litellm(monkeypatch):
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    Util._instance = None
    u = Util()
    assert u._coerce_grammar_for_chat_request("litellm", None, "gbnf") is None
    class _Meta:
        completion = {}
        llama_cpp = {"function_calling": False}

    monkeypatch.setattr(u, "core_metadata", _Meta())
    assert u._coerce_grammar_for_chat_request("local", None, "gbnf") == "gbnf"


def test_strip_grammar_when_function_calling(monkeypatch):
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    Util._instance = None
    u = Util()

    class _Meta:
        completion = {}
        llama_cpp = {"function_calling": True, "qwen_mode": "qwen35"}

    monkeypatch.setattr(u, "core_metadata", _Meta())
    g = "grammar text"
    assert u._strip_grammar_when_llama_function_calling("local", None, g) is None
    assert u._strip_grammar_when_llama_function_calling("litellm", None, g) == g


def test_strip_grammar_if_tools_in_payload():
    d = {"model": "m", "messages": [], "tools": [{"type": "function"}], "grammar": "x", "extra_body": {"grammar": "y"}}
    Util._strip_grammar_if_tools_in_payload(d, "local")
    assert "grammar" not in d
    assert "grammar" not in d.get("extra_body", {})
