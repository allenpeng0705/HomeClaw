"""
Generic webhook channel: any bot can POST minimal JSON here and get a reply.
Forwards to Core POST /inbound. No need to implement a full channel or register.
Use when Core is not directly reachable (e.g. webhook on a relay, Core on home LAN).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import httpx
from loguru import logger

# Core connection and webhook config: channels/.env only
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
from base.util import Util

app = FastAPI(title="HomeClaw Webhook Channel")


class WebhookMessage(BaseModel):
    user_id: str
    text: str
    channel_name: Optional[str] = "webhook"
    user_name: Optional[str] = None
    app_id: Optional[str] = "homeclaw"
    action: Optional[str] = "respond"
    # Optional media: data URLs (data:...;base64,...) for vision/audio/video/files
    images: Optional[list] = None
    videos: Optional[list] = None
    audios: Optional[list] = None
    files: Optional[list] = None


def core_url() -> str:
    return Util().get_channels_core_url()


@app.get("/")
def read_root():
    return {"channel": "webhook", "usage": "POST /message with {\"user_id\": \"...\", \"text\": \"...\"}"}


@app.get("/status")
def status():
    return {"status": "OK"}


@app.post("/message")
async def message(body: WebhookMessage):
    """
    Forward to Core /inbound. Same schema as Core /inbound.
    Optional: images, videos, audios, files (lists of data URLs). Ensure user_id is in config/user.yml allowlist (IM permission).
    """
    url = f"{core_url()}/inbound"
    payload = body.model_dump(exclude_none=True)
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
    port = int(os.getenv("WEBHOOK_PORT", "8005"))
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
