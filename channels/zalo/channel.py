"""
Zalo channel: HTTP webhook that a Zalo OA bridge or adapter calls.
Bridge POSTs { user_id, text }; we forward to Core /inbound and return { text }.
Bridge is responsible for sending the response back via Zalo API. Core connection from channels/.env only.
"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

load_dotenv(_root / "channels" / ".env")
from base.util import Util

app = FastAPI(title="HomeClaw Zalo Channel")
INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"


class ZaloMessage(BaseModel):
    user_id: str
    text: Optional[str] = None
    user_name: Optional[str] = None
    images: Optional[list[str]] = None
    videos: Optional[list[str]] = None
    audios: Optional[list[str]] = None
    files: Optional[list[str]] = None


@app.get("/")
def read_root():
    return {
        "channel": "zalo",
        "usage": "Bridge POSTs to /message with {\"user_id\": \"zalo_<id>\", \"text\": \"...\"}. Core connection from channels/.env.",
    }


@app.post("/message")
async def message(body: ZaloMessage):
    """Bridge calls this when a Zalo message arrives. We POST to Core /inbound and return the reply text."""
    payload = {
        "user_id": body.user_id if body.user_id.startswith("zalo_") else f"zalo_{body.user_id}",
        "text": (body.text or "").strip() or "(no text)",
        "channel_name": "zalo",
        "user_name": body.user_name or body.user_id,
    }
    if body.images:
        payload["images"] = body.images
    if body.videos:
        payload["videos"] = body.videos
    if body.audios:
        payload["audios"] = body.audios
    if body.files:
        payload["files"] = body.files
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(INBOUND_URL, json=payload, timeout=120.0)
        data = r.json() if r.content else {}
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
    except Exception as e:
        reply = f"Error: {e}"
    return {"text": reply or "(no reply)"}


def main():
    import uvicorn
    port = int(os.getenv("ZALO_CHANNEL_PORT", "8015"))
    host = os.getenv("ZALO_CHANNEL_HOST", "0.0.0.0")
    print(f"Zalo channel: webhook http://{host}:{port}/message (Core from channels/.env)")
    print("Run your Zalo OA bridge so it POSTs here and sends the response back via Zalo API.")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
