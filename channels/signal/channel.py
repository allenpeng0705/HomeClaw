"""
Signal channel: HTTP webhook that a Signal bridge calls (e.g. signal-cli with a script).
Bridge POSTs { user_id, text }; we forward to Core /inbound and return { text }.
Bridge is responsible for sending the response back via Signal. Core connection from channels/.env only.
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

app = FastAPI(title="HomeClaw Signal Channel")
INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"


class SignalMessage(BaseModel):
    user_id: str
    text: str
    user_name: Optional[str] = None


@app.get("/")
def read_root():
    return {
        "channel": "signal",
        "usage": "Bridge POSTs to /message with {\"user_id\": \"signal_<id>\", \"text\": \"...\"}. Core connection from channels/.env.",
    }


@app.post("/message")
async def message(body: SignalMessage):
    """Bridge calls this when a Signal message arrives. We POST to Core /inbound and return the reply text."""
    payload = {
        "user_id": body.user_id if body.user_id.startswith("signal_") else f"signal_{body.user_id}",
        "text": body.text,
        "channel_name": "signal",
        "user_name": body.user_name or body.user_id,
    }
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
    port = int(os.getenv("SIGNAL_CHANNEL_PORT", "8011"))
    host = os.getenv("SIGNAL_CHANNEL_HOST", "0.0.0.0")
    print(f"Signal channel: webhook http://{host}:{port}/message (Core from channels/.env)")
    print("Run your Signal bridge so it POSTs here and sends the response back via Signal.")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
