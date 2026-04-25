"""main_llm_chat_path / cloud_llm_chat_path for direct (non-Panda) chat completion URLs."""

import pytest

from base.util import Util


def test_openai_chat_completions_path_local_vs_cloud(util_paths):
    u = util_paths
    assert u.openai_chat_completions_path("local") == "/v1/chat/completions"
    assert u.openai_chat_completions_path("ollama") == "/v1/chat/completions"
    assert u.openai_chat_completions_path("litellm") == "/cloud/v1/chat/completions"


def test_openai_chat_completions_path_strips_and_prefixes_slash(util_paths):
    """Custom paths get normalised: leading slash added, trailing stripped."""
    util_paths._core_metadata = type(util_paths._core_metadata)(
        main_llm_chat_path="custom/chat",
        cloud_llm_chat_path="",
    )
    assert util_paths.openai_chat_completions_path("local") == "/custom/chat"
    assert util_paths.openai_chat_completions_path("litellm") == "/v1/chat/completions"


def test_normalize_llm_chat_path_from_base():
    from base.base import _normalize_llm_chat_path

    assert _normalize_llm_chat_path(None) == "/v1/chat/completions"
    assert _normalize_llm_chat_path("x/y") == "/x/y"
    assert _normalize_llm_chat_path("/z") == "/z"


def test_coerce_grammar_drops_for_litellm(util_paths):
    """litellm provider drops grammar; other providers keep it when llama_cpp.function_calling is False."""
    assert util_paths._coerce_grammar_for_chat_request("litellm", None, "gbnf") is None
    util_paths._core_metadata = type(util_paths._core_metadata)(
        completion={},
        llama_cpp={"function_calling": False},
    )
    assert util_paths._coerce_grammar_for_chat_request("local", None, "gbnf") == "gbnf"


def test_strip_grammar_when_function_calling(util_paths):
    """Grammar stripped for llama when function_calling=True; litellm keeps grammar."""
    util_paths._core_metadata = type(util_paths._core_metadata)(
        completion={},
        llama_cpp={"function_calling": True, "qwen_mode": "qwen35"},
    )
    g = "grammar text"
    assert util_paths._strip_grammar_when_llama_function_calling("local", None, g) is None
    assert util_paths._strip_grammar_when_llama_function_calling("litellm", None, g) == g


def test_strip_grammar_if_tools_in_payload():
    d = {"model": "m", "messages": [], "tools": [{"type": "function"}], "grammar": "x", "extra_body": {"grammar": "y"}}
    Util._strip_grammar_if_tools_in_payload(d, "local")
    assert "grammar" not in d
    assert "grammar" not in d.get("extra_body", {})
