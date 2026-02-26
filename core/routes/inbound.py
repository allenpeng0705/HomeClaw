"""
Inbound API routes: POST /inbound remains in core.py (complex stream/async logic).
GET /inbound/result is here for polling async inbound results.
"""
import time
from fastapi.responses import JSONResponse


def get_inbound_result_handler(core):
    """Return async handler for GET /inbound/result. Uses core._inbound_async_results and TTL."""

    async def inbound_result(request_id: str = ""):
        """
        Poll result of an async POST /inbound (when async: true). Query: request_id=... from the 202 response.
        Returns 202 + {status: "pending"} while processing; 200 + {status: "done", text, format, images?, error?} when done; 404 when request_id unknown or expired (TTL 5 min).
        """
        request_id = (request_id or "").strip()
        if not request_id:
            return JSONResponse(status_code=400, content={"error": "Missing request_id"})
        now = time.time()
        ttl = getattr(core, "_inbound_async_results_ttl_sec", 300)
        # Core sets _inbound_async_results in __init__; default {} only to avoid AttributeError before init
        results = getattr(core, "_inbound_async_results", {})
        expired = [rid for rid, v in results.items() if (now - v.get("created_at", 0)) > ttl]
        for rid in expired:
            results.pop(rid, None)
        entry = results.get(request_id)
        if not entry:
            return JSONResponse(status_code=404, content={"error": "Unknown or expired request_id", "status": "gone"})
        if entry.get("status") == "pending":
            return JSONResponse(status_code=202, content={"status": "pending", "request_id": request_id})
        body = {"status": "done", "text": entry.get("text", ""), "format": entry.get("format", "plain")}
        if entry.get("error"):
            body["error"] = entry["error"]
        if entry.get("images"):
            body["images"] = entry["images"]
            body["image"] = entry.get("image") or entry["images"][0]
        return JSONResponse(content=body)

    return inbound_result
