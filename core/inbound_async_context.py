"""Async POST /inbound: propagate poll request_id into plugin layer (bridge streaming previews)."""
from contextvars import ContextVar
from typing import Optional

ASYNC_INBOUND_REQUEST_ID: ContextVar[Optional[str]] = ContextVar("async_inbound_request_id", default=None)
