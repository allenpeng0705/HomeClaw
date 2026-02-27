"""
Tests for Core refactor Phases 2–8: route_registration, initialization, inbound_handlers, session_channel, outbound, llm_loop, plugins_startup, media_utils, entry.

Run from project root with conda env (e.g. conda activate pytorch):
  python -m pytest tests/test_core_refactor_phases2_4.py -v

If the environment aborts when loading torch (via base.util, pulled in by initialization
and route_registration), run only the lightweight module tests:
  python -m pytest tests/test_core_refactor_phases2_4.py -v -k "inbound_handlers or session_channel or outbound"

These tests verify that the extracted modules exist and expose the expected functions.
They do NOT start full Core. For full regression, run the full suite when torch loads
successfully, or do a manual smoke: start Core and hit /inbound, /process, /local_chat.
"""

import pytest
from unittest.mock import MagicMock


def test_inbound_handlers_module():
    """core.inbound_handlers exposes handle_inbound_request, run_async_inbound, handle_inbound_request_impl, inbound_sse_generator."""
    from core import inbound_handlers

    assert hasattr(inbound_handlers, "handle_inbound_request")
    assert callable(inbound_handlers.handle_inbound_request)
    assert hasattr(inbound_handlers, "run_async_inbound")
    assert callable(inbound_handlers.run_async_inbound)
    assert hasattr(inbound_handlers, "handle_inbound_request_impl")
    assert callable(inbound_handlers.handle_inbound_request_impl)
    assert hasattr(inbound_handlers, "inbound_sse_generator")
    assert callable(inbound_handlers.inbound_sse_generator)


def test_initialization_module():
    """core.initialization exposes run_initialize and the _create_* helpers."""
    from core import initialization

    assert hasattr(initialization, "run_initialize")
    assert callable(initialization.run_initialize)
    assert hasattr(initialization, "_create_skills_vector_store")
    assert callable(initialization._create_skills_vector_store)
    assert hasattr(initialization, "_create_plugins_vector_store")
    assert callable(initialization._create_plugins_vector_store)
    assert hasattr(initialization, "_create_agent_memory_vector_store")
    assert callable(initialization._create_agent_memory_vector_store)
    assert hasattr(initialization, "_create_knowledge_base")
    assert callable(initialization._create_knowledge_base)
    assert hasattr(initialization, "_create_knowledge_base_cognee")
    assert callable(initialization._create_knowledge_base_cognee)


def test_route_registration_module():
    """core.route_registration exposes register_all_routes."""
    from core import route_registration

    assert hasattr(route_registration, "register_all_routes")
    assert callable(route_registration.register_all_routes)


def test_route_registration_register_all_routes_with_mock_core():
    """register_all_routes(core) runs without error when core has .app and ._pinggy_state_getter."""
    from core.route_registration import register_all_routes

    app = MagicMock()
    core = MagicMock()
    core.app = app
    core._pinggy_state_getter = lambda: {"public_url": None, "connect_url": None, "qr_base64": None, "error": None}
    register_all_routes(core)
    # Should have registered routes (exception_handler and add_api_route / post decorators)
    assert app.exception_handler.called or app.add_api_route.called


# --- Phase 5: session_channel and outbound ---


def test_session_channel_module():
    """core.session_channel exposes last-channel, location, session/chat helpers."""
    from core import session_channel

    assert hasattr(session_channel, "_persist_last_channel")
    assert callable(session_channel._persist_last_channel)
    assert hasattr(session_channel, "_latest_location_path")
    assert callable(session_channel._latest_location_path)
    assert hasattr(session_channel, "_normalize_location_to_address")
    assert callable(session_channel._normalize_location_to_address)
    assert hasattr(session_channel, "_set_latest_location")
    assert callable(session_channel._set_latest_location)
    assert hasattr(session_channel, "_get_latest_location")
    assert callable(session_channel._get_latest_location)
    assert hasattr(session_channel, "_get_latest_location_entry")
    assert callable(session_channel._get_latest_location_entry)
    assert hasattr(session_channel, "get_run_id")
    assert callable(session_channel.get_run_id)
    assert hasattr(session_channel, "get_latest_chat_info")
    assert callable(session_channel.get_latest_chat_info)
    assert hasattr(session_channel, "get_latest_chats")
    assert callable(session_channel.get_latest_chats)
    assert hasattr(session_channel, "get_latest_chats_by_role")
    assert callable(session_channel.get_latest_chats_by_role)
    assert hasattr(session_channel, "_resolve_session_key")
    assert callable(session_channel._resolve_session_key)
    assert hasattr(session_channel, "get_session_id")
    assert callable(session_channel.get_session_id)
    assert hasattr(session_channel, "get_system_context_for_plugins")
    assert callable(session_channel.get_system_context_for_plugins)


def test_outbound_module():
    """core.outbound exposes format, classify, and delivery functions."""
    from core import outbound

    assert hasattr(outbound, "format_outbound_text")
    assert callable(outbound.format_outbound_text)
    assert hasattr(outbound, "safe_classify_format")
    assert callable(outbound.safe_classify_format)
    assert hasattr(outbound, "outbound_text_and_format")
    assert callable(outbound.outbound_text_and_format)
    assert hasattr(outbound, "send_response_to_latest_channel")
    assert callable(outbound.send_response_to_latest_channel)
    assert hasattr(outbound, "send_response_to_channel_by_key")
    assert callable(outbound.send_response_to_channel_by_key)
    assert hasattr(outbound, "deliver_to_user")
    assert callable(outbound.deliver_to_user)
    assert hasattr(outbound, "send_response_to_request_channel")
    assert callable(outbound.send_response_to_request_channel)
    assert hasattr(outbound, "send_response_for_plugin")
    assert callable(outbound.send_response_for_plugin)


def test_outbound_format_helpers_no_core():
    """outbound_text_and_format and format helpers work with a minimal mock core (no DB)."""
    from core.outbound import format_outbound_text, safe_classify_format, outbound_text_and_format

    core = MagicMock()
    # format_outbound_text and safe_classify_format use Util().get_core_metadata() internally;
    # we only check they are callable and return strings when given simple input.
    out_text, out_fmt = outbound_text_and_format(core, "hello")
    assert isinstance(out_text, str)
    assert out_fmt in ("plain", "markdown", "link")
    out_text2, out_fmt2 = outbound_text_and_format(core, None)
    assert out_text2 == ""
    assert out_fmt2 == "plain"


# --- Phase 6: llm_loop (answer_from_memory) ---


def test_llm_loop_module():
    """core.llm_loop exposes answer_from_memory (async)."""
    from core import llm_loop

    assert hasattr(llm_loop, "answer_from_memory")
    assert callable(llm_loop.answer_from_memory)
    import asyncio
    assert asyncio.iscoroutinefunction(llm_loop.answer_from_memory)


# --- Phase 7: plugins_startup and media_utils ---


def test_plugins_startup_module():
    """core.plugins_startup exposes _discover_system_plugins, _wait_for_core_ready, _run_system_plugins_startup."""
    from core import plugins_startup

    assert hasattr(plugins_startup, "_discover_system_plugins")
    assert callable(plugins_startup._discover_system_plugins)
    assert hasattr(plugins_startup, "_wait_for_core_ready")
    assert callable(plugins_startup._wait_for_core_ready)
    assert hasattr(plugins_startup, "_run_system_plugins_startup")
    assert callable(plugins_startup._run_system_plugins_startup)
    import asyncio
    assert asyncio.iscoroutinefunction(plugins_startup._run_system_plugins_startup)
    assert asyncio.iscoroutinefunction(plugins_startup._wait_for_core_ready)


def test_media_utils_module():
    """core.media_utils exposes resize_image_data_url_if_needed, image_item_to_data_url, audio_item_to_base64_and_format, video_item_to_base64_and_format."""
    from core import media_utils

    assert hasattr(media_utils, "resize_image_data_url_if_needed")
    assert callable(media_utils.resize_image_data_url_if_needed)
    assert hasattr(media_utils, "image_item_to_data_url")
    assert callable(media_utils.image_item_to_data_url)
    assert hasattr(media_utils, "audio_item_to_base64_and_format")
    assert callable(media_utils.audio_item_to_base64_and_format)
    assert hasattr(media_utils, "video_item_to_base64_and_format")
    assert callable(media_utils.video_item_to_base64_and_format)


def test_media_utils_resize_image_no_change():
    """resize_image_data_url_if_needed returns original when max_dimension <= 0 or invalid."""
    from core.media_utils import resize_image_data_url_if_needed

    core = MagicMock()
    assert resize_image_data_url_if_needed(core, "", 100) == ""
    assert resize_image_data_url_if_needed(core, "data:image/jpeg;base64,abc", 0) == "data:image/jpeg;base64,abc"


# --- Phase 8: entry (main, Windows Ctrl handler) ---


def test_entry_module():
    """core.entry exposes main and _win_console_ctrl_handler; main is callable."""
    from core import entry

    assert hasattr(entry, "main")
    assert callable(entry.main)
    assert hasattr(entry, "_win_console_ctrl_handler")
    assert callable(entry._win_console_ctrl_handler)
    assert hasattr(entry, "_core_instance_for_ctrl_c")
    assert hasattr(entry, "_CORE_CTRL_GRACE_SEC")


def test_core_module_exposes_main():
    """core.core exposes main (for main.py: core.main)."""
    from core import core as core_module

    assert hasattr(core_module, "main")
    assert callable(core_module.main)
