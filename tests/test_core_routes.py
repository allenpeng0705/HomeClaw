"""
Smoke tests for Core route modules (refactored from core/core.py).

These tests verify that:
  1. All route modules can be imported without circular imports or missing deps.
  2. Every handler factory function exists, is callable, and returns a callable (the actual handler).
  3. Auth helpers (verify_inbound_auth, ws_auth_ok) exist and are callable.

They do NOT start the full Core or hit real endpoints; they only check that the route layer
is wired correctly so that Core.initialize() can register routes without errors.

How to run
----------
From the project root, use pytest (do NOT use "python -m tests/test_core_routes.py"):

  # Run only these tests
  python -m pytest tests/test_core_routes.py -v

  # Run with extra output
  python -m pytest tests/test_core_routes.py -v -s

  # Run a single test
  python -m pytest tests/test_core_routes.py -v -k "test_route_modules_import"

Dependencies: pytest. Install with: pip install pytest

See also: docs_design/CoreRefactorPhaseSummary.md and docs_design/CoreRefactoringModularCore.md.
"""

import pytest
from unittest.mock import MagicMock


# Handler factories that take (core) and return a callable. get_pinggy_handler(core, get_pinggy_state) takes 2 args.
ROUTE_FACTORIES = [
    ("lifecycle", "get_register_channel_handler", ()),
    ("lifecycle", "get_deregister_channel_handler", ()),
    ("lifecycle", "get_ready_handler", ()),
    ("lifecycle", "get_pinggy_handler", (lambda: {},)),  # get_pinggy_state
    ("lifecycle", "get_shutdown_handler", ()),
    ("inbound", "get_inbound_result_handler", ()),
    ("config_api", "get_api_config_core_get_handler", ()),
    ("config_api", "get_api_config_core_patch_handler", ()),
    ("config_api", "get_api_config_users_get_handler", ()),
    ("config_api", "get_api_config_users_post_handler", ()),
    ("config_api", "get_api_config_users_patch_handler", ()),
    ("config_api", "get_api_config_users_delete_handler", ()),
    ("files", "get_files_out_handler", ()),
    ("files", "get_api_sandbox_list_handler", ()),
    ("files", "get_api_upload_handler", ()),
    ("memory_routes", "get_memory_summarize_handler", ()),
    ("memory_routes", "get_memory_reset_handler", ()),
    ("knowledge_base_routes", "get_knowledge_base_reset_handler", ()),
    ("knowledge_base_routes", "get_knowledge_base_folder_sync_config_handler", ()),
    ("knowledge_base_routes", "get_knowledge_base_sync_folder_handler", ()),
    ("plugins_api", "get_api_plugins_register_handler", ()),
    ("plugins_api", "get_api_plugins_unregister_handler", ()),
    ("plugins_api", "get_api_plugins_unregister_all_handler", ()),
    ("plugins_api", "get_api_plugins_health_handler", ()),
    ("plugins_api", "get_api_plugins_llm_generate_handler", ()),
    ("plugins_api", "get_api_plugins_memory_add_handler", ()),
    ("plugins_api", "get_api_plugins_memory_search_handler", ()),
    ("plugins_api", "get_api_plugin_ui_list_handler", ()),
    ("misc_api", "get_api_skills_clear_vector_store_handler", ()),
    ("misc_api", "get_api_testing_clear_all_handler", ()),
    ("misc_api", "get_api_sessions_list_handler", ()),
    ("misc_api", "get_api_reports_usage_handler", ()),
    ("ui_routes", "get_ui_launcher_handler", ()),
    ("websocket_routes", "get_websocket_handler", ()),
]


def test_route_modules_import():
    """All core.routes submodules can be imported without error (no circular imports)."""
    from core.routes import (
        auth,
        lifecycle,
        inbound,
        config_api,
        files,
        memory_routes,
        knowledge_base_routes,
        plugins_api,
        misc_api,
        ui_routes,
        websocket_routes,
    )
    assert auth is not None
    assert lifecycle is not None
    assert inbound is not None
    assert config_api is not None
    assert files is not None
    assert memory_routes is not None
    assert knowledge_base_routes is not None
    assert plugins_api is not None
    assert misc_api is not None
    assert ui_routes is not None
    assert websocket_routes is not None


def test_auth_helpers_exist_and_are_callable():
    """Auth module exposes verify_inbound_auth and ws_auth_ok and they are callable."""
    from core.routes import auth
    assert hasattr(auth, "verify_inbound_auth")
    assert callable(auth.verify_inbound_auth)
    assert hasattr(auth, "ws_auth_ok")
    assert callable(auth.ws_auth_ok)


@pytest.mark.parametrize("module_name,factory_name,extra_args", ROUTE_FACTORIES)
def test_handler_factory_exists_and_returns_callable(module_name, factory_name, extra_args):
    """
    Each handler factory exists on its module, is callable, and when called with a mock core
    (and any extra args, e.g. get_pinggy_state for pinggy) returns a callable (the route handler).
    """
    from core import routes
    module = getattr(routes, module_name, None)
    assert module is not None, f"Module {module_name} not found in core.routes"
    factory = getattr(module, factory_name, None)
    assert factory is not None, f"Factory {factory_name} not found on {module_name}"
    assert callable(factory), f"{module_name}.{factory_name} is not callable"

    mock_core = MagicMock()
    # Some handlers access core._inbound_async_results, _ws_sessions, etc.; provide dicts so getattr doesn't break
    mock_core._inbound_async_results = {}
    mock_core._ws_sessions = {}
    mock_core._ws_user_by_session = {}
    mock_core.plugin_manager = MagicMock()
    mock_core.get_sessions = MagicMock(return_value=[])

    handler = factory(mock_core, *extra_args)
    assert callable(handler), f"{module_name}.{factory_name}(core, ...) did not return a callable"


def test_all_factories_count():
    """Sanity check: we have the expected number of handler factories (avoids forgetting one)."""
    assert len(ROUTE_FACTORIES) >= 34, "Expected at least 34 handler factories; update ROUTE_FACTORIES if you added routes"
