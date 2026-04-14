"""SSE stream of workflow trace JSON lines (dev / observability)."""

from __future__ import annotations

import asyncio
import queue
from typing import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from base.util import Util
from base.workflow_trace import subscribe_trace_sse_queue, unsubscribe_trace_sse_queue


async def _workflow_trace_sse_generator(request: Request) -> AsyncIterator[bytes]:
    meta = Util().get_core_metadata()
    if not getattr(meta, "workflow_trace_sse_enabled", False):
        yield b'event: error\ndata: {"error":"workflow_trace_sse_enabled is false in core.yml"}\n\n'
        return
    q: queue.Queue = subscribe_trace_sse_queue()
    try:
        yield b": connected\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                while True:
                    line = q.get_nowait()
                    yield f"data: {line}\n\n".encode("utf-8")
            except queue.Empty:
                pass
            await asyncio.sleep(0.05)
    finally:
        unsubscribe_trace_sse_queue(q)


def get_workflow_trace_sse_handler():
    async def _handler(request: Request):
        return StreamingResponse(
            _workflow_trace_sse_generator(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return _handler
