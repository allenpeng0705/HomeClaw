"""
External Time Plugin - HTTP server with multiple capabilities and parameters.
Run: python -m external_plugins.time.server
Then register with Core: python -m external_plugins.time.register
Core POSTs PluginRequest (with capability_id and capability_parameters) to /run; server dispatches by capability_id.
"""
from datetime import datetime
import uvicorn
from fastapi import FastAPI
from typing import Dict, Any

app = FastAPI()

COMMON_TIMEZONES = [
    "UTC", "America/New_York", "America/Los_Angeles", "America/Chicago",
    "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai",
    "Australia/Sydney", "Pacific/Auckland",
]


@app.get("/health")
def health():
    return {"status": "ok"}


def _get_time_str(tz_name: str, fmt: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.utcnow()
        tz_name = "UTC"
    if fmt and fmt.lower() in ("12", "12h"):
        time_str = now.strftime("%I:%M:%S %p")
    else:
        time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    return f"{date_str} {time_str} ({tz_name})"


@app.post("/run")
async def run(body: Dict[str, Any]):
    """Accept PluginRequest (JSON), dispatch by capability_id, return PluginResult (JSON)."""
    request_id = body.get("request_id", "")
    plugin_id = body.get("plugin_id", "time")
    cap_id = (body.get("capability_id") or "get_time").strip().lower().replace(" ", "_")
    params = body.get("capability_parameters") or {}
    tz_name = (params.get("timezone") or "").strip() or "UTC"
    fmt = (params.get("format") or "").strip() or "24h"

    if cap_id == "list_timezones":
        text = "Common timezones: " + ", ".join(COMMON_TIMEZONES)
    else:
        # get_time
        text = _get_time_str(tz_name, fmt)

    return {
        "request_id": request_id,
        "plugin_id": plugin_id,
        "success": True,
        "text": text,
        "error": None,
        "metadata": {},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3102)
