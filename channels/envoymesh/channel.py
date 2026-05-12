"""
EnvoyMesh bridge channel: P2P chat ↔ HomeClaw Core.

Flow:
  P2P Peer → EnvoyMesh Node → POST /message (this channel) → Core /inbound → AI reply
  AI reply → Core response → POST bridge /bridge/send → EnvoyMesh Node → P2P Peer

The EnvoyMesh bridge POSTs { from, fromOwnerId, fromName, text } to this channel.
The "from" field is the sender's P2P peer ID — used as the reply routing target.
This channel forwards to Core as a standard inbound request, then POSTs Core's
reply back to the bridge's /bridge/send endpoint for signed P2P delivery.

One EnvoyMesh Node = one bridge = one instance of this channel.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

# Shared channels/.env for Core connection
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
from base.util import Util
from channels.clawcode_binding import apply_clawcode_inbound_flow

app = FastAPI(title="HomeClaw EnvoyMesh Channel")


# ── config ──────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "config.yml"
    with open(cfg_path, "r") as fh:
        return yaml.safe_load(fh) or {}

_cfg = _load_config()
BRIDGE_URL = os.getenv("ENVOYMESH_BRIDGE_URL", _cfg.get("bridge_url", "http://127.0.0.1:3031/bridge/send"))
BRIDGE_SECRET = os.getenv("ENVOYMESH_BRIDGE_SECRET", _cfg.get("bridge_secret", ""))
CHANNEL_NAME = os.getenv("ENVOYMESH_CHANNEL_NAME", _cfg.get("name", "envoymesh"))
HC_USER_ID = os.getenv("ENVOYMESH_USER_ID", _cfg.get("user_id", "AllenPeng"))


def core_url() -> str:
    return Util().get_channels_core_url()


def _bridge_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if BRIDGE_SECRET:
        headers["Authorization"] = f"Bearer {BRIDGE_SECRET}"
    return headers


# ── routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {
        "channel": CHANNEL_NAME,
        "bridge_url": BRIDGE_URL,
        "usage": "POST /message with {\"from\": \"...\", \"fromOwnerId\": \"...\", \"fromName\": \"...\", \"text\": \"...\"}",
    }


@app.get("/status")
def status():
    return {"status": "OK", "bridge_url": BRIDGE_URL}


@app.post("/message")
async def message(req: Request):
    """
    Receive P2P message from EnvoyMesh bridge, forward to Core, send reply back.

    Bridge sends: { "from": "<peerId>", "fromOwnerId": "<ownerId>",
                    "fromName": "<displayName>", "text": "<message>" }
    """
    body = await req.json()
    sender_peer_id = (body.get("from") or "").strip()
    sender_owner_id = (body.get("fromOwnerId") or "").strip()
    sender_name = (body.get("fromName") or sender_owner_id).strip()
    text = (body.get("text") or "").strip()

    if not sender_owner_id or not text:
        return JSONResponse(
            status_code=400,
            content={"error": "fromOwnerId and text are required"},
        )

    # ── 1. Build inbound payload for Core ───────────────────────────────
    # user_id = configured HomeClaw user (matches user.yml id)
    # friend_id = P2P sender identity (so Core knows who it's talking to)
    payload: dict = {
        "user_id": HC_USER_ID,
        "friend_id": sender_owner_id,
        "text": text,
        "channel_name": CHANNEL_NAME,
        "user_name": sender_name,
        "app_id": "envoymesh",
        "action": "respond",
        "reply_accepts": ["text"],
    }

    # ── 2. Check for Claw-Code commands ─────────────────────────────────
    _cc = apply_clawcode_inbound_flow(HC_USER_ID, text, payload)
    if _cc is not None:
        await _reply_to_bridge(sender_peer_id, _cc)
        return {"text": _cc, "status": "clawcode"}

    # ── 3. Forward to Core ──────────────────────────────────────────────
    core_inbound_url = f"{core_url()}/inbound"
    headers = Util().get_channels_core_api_headers()
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(
                core_inbound_url, json=payload, headers=headers, timeout=120.0
            )
        if r.status_code != 200:
            logger.warning(f"Core returned {r.status_code}: {r.text}")
            return JSONResponse(
                status_code=r.status_code,
                content={"error": r.text, "text": ""},
            )
        core_response = r.json()
    except httpx.ConnectError:
        logger.error(f"Cannot reach Core at {core_inbound_url}")
        return JSONResponse(
            status_code=503,
            content={"error": "Core unreachable", "text": ""},
        )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "text": ""},
        )

    # ── 4. Send Core's reply back to the bridge ─────────────────────────
    reply_text = (core_response.get("text") or "").strip()
    if reply_text:
        await _reply_to_bridge(sender_peer_id, reply_text)

    return {"text": reply_text, "status": "ok"}


# ── helpers ─────────────────────────────────────────────────────────────────

async def _reply_to_bridge(to: str, text: str):
    """POST the Core reply back to EnvoyMesh bridge /bridge/send."""
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(
                BRIDGE_URL,
                json={"to": to, "text": text},
                headers=_bridge_headers(),
                timeout=30.0,
            )
        if r.status_code == 200:
            logger.info(f"[envoymesh] reply sent to {to}: {text[:80]}...")
        else:
            logger.warning(f"[envoymesh] bridge returned {r.status_code}: {r.text}")
    except httpx.ConnectError:
        logger.error(f"[envoymesh] bridge unreachable at {BRIDGE_URL}")
    except Exception as e:
        logger.exception(f"[envoymesh] bridge reply failed: {e}")


# ── entry ───────────────────────────────────────────────────────────────────

def main():
    import uvicorn
    port = int(os.getenv("ENVOYMESH_PORT", str(_cfg.get("port", 8010))))
    host = os.getenv("ENVOYMESH_HOST", _cfg.get("host", "0.0.0.0"))
    logger.info(f"[envoymesh] starting on {host}:{port}, bridge → {BRIDGE_URL}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
