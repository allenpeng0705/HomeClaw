"""
Inbound API routes: POST /inbound remains in core.py (complex stream/async logic).
GET /inbound/result is here for polling async inbound results.
POST /inbound/cancel lets the client (e.g. Companion) cancel an ongoing async request.
"""
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def get_inbound_result_handler(core):
    """Return async handler for GET /inbound/result. Uses core._inbound_async_results and TTL."""

    async def inbound_result(request_id: str = ""):
        """
        Poll result of an async POST /inbound (when async: true). Query: request_id=... from the 202 response.
        Returns 202 + {status: "pending"} while processing; 200 + {status: "done"|"cancelled", text, format, images?, error?} when done/cancelled; 404 when request_id unknown or expired. Pending entries use a longer TTL (default 30 min) so long-running requests stay pollable; done/cancelled entries expire after 5 min.
        """
        request_id = (request_id or "").strip()
        if not request_id:
            return JSONResponse(status_code=400, content={"error": "Missing request_id"})
        now = time.time()
        ttl = getattr(core, "_inbound_async_results_ttl_sec", 300)
        pending_ttl = getattr(core, "_inbound_async_pending_ttl_sec", 1800)  # 30 min: don't expire "pending" too soon so long-running requests stay pollable
        # Core sets _inbound_async_results in __init__; default {} only to avoid AttributeError before init
        results = getattr(core, "_inbound_async_results", {})
        # Expire only: (1) done/cancelled results older than ttl (so client had time to fetch), (2) pending older than pending_ttl (leak guard)
        expired = [
            rid for rid, v in results.items()
            if (now - v.get("created_at", 0)) > (pending_ttl if v.get("status") == "pending" else ttl)
        ]
        for rid in expired:
            results.pop(rid, None)
        entry = results.get(request_id)
        if not entry:
            return JSONResponse(status_code=404, content={"error": "Unknown or expired request_id", "status": "gone"})
        if entry.get("status") == "pending":
            _lk = getattr(core, "_inbound_async_results_lock", None)
            _preview = ""
            if _lk is not None:
                with _lk:
                    _e = results.get(request_id)
                    if _e and _e.get("status") == "pending":
                        _preview = (str(_e.get("text") or "")).strip()
            else:
                _preview = (str(entry.get("text") or "")).strip()
            _body: dict = {"status": "pending", "request_id": request_id}
            if _preview:
                _body["text_preview"] = _preview
            return JSONResponse(status_code=202, content=_body)
        body = {"status": entry.get("status", "done"), "text": entry.get("text", ""), "format": entry.get("format", "plain")}
        if entry.get("error"):
            body["error"] = entry["error"]
        if entry.get("images"):
            body["images"] = entry["images"]
            body["image"] = entry.get("image") or entry["images"][0]
        return JSONResponse(content=body)

    return inbound_result


def cancel_inbound_request_handler(core):
    """Return async handler for POST /inbound/cancel. Lets Companion (or any client) cancel an ongoing async /inbound request by request_id."""

    async def cancel_inbound(request: Request):
        """
        Cancel an async POST /inbound request. Body: {"request_id": "..."} (request_id from the 202 response).
        Returns 200 + {ok: true, status: "cancelled"} when cancel was sent; 404 when request_id unknown or already finished.
        """
        body = {}
        try:
            cl = request.headers.get("content-length")
            if cl and int(cl) > 0:
                body = await request.json() or {}
        except Exception:
            pass
        if not isinstance(body, dict):
            body = {}
        request_id = (body.get("request_id") or "").strip()
        if not request_id:
            return JSONResponse(status_code=400, content={"error": "Missing request_id", "ok": False})
        tasks = getattr(core, "_inbound_async_tasks", None)
        if not isinstance(tasks, dict):
            return JSONResponse(status_code=404, content={"error": "Unknown request_id", "ok": False})
        task = tasks.get(request_id)
        if task is None:
            # Already finished or never existed; set result to cancelled so poll sees it if still pending
            results = getattr(core, "_inbound_async_results", {})
            entry = results.get(request_id)
            if entry and entry.get("status") == "pending":
                entry["status"] = "cancelled"
                entry["error"] = "Request was cancelled by the client."
            return JSONResponse(content={"ok": True, "status": "cancelled", "message": "Request not found or already finished; marked cancelled if was pending."})
        task.cancel()
        results = getattr(core, "_inbound_async_results", {})
        results[request_id] = {
            "status": "cancelled",
            "ok": False,
            "text": "",
            "format": "plain",
            "error": "Request was cancelled by the client.",
            "created_at": time.time(),
        }
        tasks.pop(request_id, None)
        return JSONResponse(content={"ok": True, "status": "cancelled"})

    return cancel_inbound
