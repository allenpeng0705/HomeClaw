# Portal: HomeClaw configuration and onboarding web server.
# Runs locally (127.0.0.1); provides settings UI, install guide, start Core/Channels.
# See docs_design/CorePortalDesign.md and docs_design/CorePortalImplementationPlan.md.

from core.portal.app import app
from core.portal import config

__all__ = ["app", "config"]
