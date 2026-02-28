# Core route modules: auth, lifecycle, inbound, config_api, etc.
# Each module provides handlers or Depends used by core.core to register routes.
# See docs_design/CoreRefactoringModularCore.md and docs_design/CoreRefactorPhaseSummary.md.

from core.routes import auth
from core.routes import lifecycle
from core.routes import inbound
from core.routes import config_api
from core.routes import files
from core.routes import memory_routes
from core.routes import knowledge_base_routes
from core.routes import plugins_api
from core.routes import misc_api
from core.routes import ui_routes
from core.routes import websocket_routes
from core.routes import companion_push_api
from core.routes import companion_auth
from core.routes import portal_proxy

__all__ = [
    "auth", "lifecycle", "inbound", "config_api", "files", "memory_routes", "knowledge_base_routes",
    "plugins_api", "misc_api", "ui_routes", "websocket_routes", "companion_push_api", "companion_auth", "portal_proxy",
]
