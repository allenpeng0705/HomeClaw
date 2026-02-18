"""
WhatsApp Web channel: receives messages from a WhatsApp Web bridge (e.g. Baileys)
and forwards them to HomeClaw Core. Replies from Core are returned to the caller (sync).
Run: python -m channels.run whatsappweb
Core URL: channels/.env (core_host, core_port or CORE_URL).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import httpx
from loguru import logger

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
from base.util import Util

app = FastAPI(title="HomeClaw WhatsApp Web Channel")

# Payload from bridge: same shape as Core /inbound for convenience
class WebhookMessage(BaseModel):
    user_id: str
    text: str
    channel_name: Optional[str] = "whatsappweb"
    user_name: Optional[str] = None
    app_id: Optional[str] = "homeclaw"
    action: Optional[str] = "respond"
    images: Optional[List[str]] = None
    videos: Optional[List[str]] = None
    audios: Optional[List[str]] = None
    files: Optional[List[str]] = None


def core_url() -> str:
    return Util().get_channels_core_url()


@app.get("/")
def read_root():
    return {
        "channel": "whatsappweb",
        "usage": "POST /webhook with {\"user_id\": \"...\", \"text\": \"...\"} (optional: images, videos, audios, files)",
    }


@app.get("/status")
def status():
    return {"status": "OK"}


@app.post("/webhook")
async def webhook(body: WebhookMessage):
    """
    Receive message from WhatsApp Web bridge; forward to Core /inbound.
    Returns Core response (sync). Bridge should send the returned text (and optional media) back to WhatsApp.
    """
    url = f"{core_url()}/inbound"
    payload = body.model_dump(exclude_none=True)
    payload.setdefault("channel_name", "whatsappweb")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=120.0)
        if r.status_code != 200:
            logger.warning(f"Core returned {r.status_code}: {r.text}")
            return JSONResponse(status_code=r.status_code, content={"error": r.text, "text": ""})
        return r.json()
    except httpx.ConnectError as e:
        logger.error(f"Cannot reach Core at {url}: {e}")
        return JSONResponse(status_code=503, content={"error": "Core unreachable", "text": ""})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"error": str(e), "text": ""})


def main():
    import uvicorn
    port = int(os.getenv("WHATSAPPWEB_PORT", "8010"))
    host = os.getenv("WHATSAPPWEB_HOST", "0.0.0.0")
    logger.info(f"WhatsApp Web channel on {host}:{port}; Core at {core_url()}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
