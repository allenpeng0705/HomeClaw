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
import hashlib
import os
import sys
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

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

# Shared pooled client for outbound Core + bridge — fewer TCP/TLS handshakes on sustained P2P traffic.
_http_client: Optional[httpx.AsyncClient] = None

# Dedup cache: recent message hashes → (text, timestamp). Prevents duplicate processing
# when the bridge retries. LRU-ordered; max 200 entries before eviction.
_dedup_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
_DEDUP_MAX = 200


@asynccontextmanager
async def _lifespan(_: FastAPI):
    global _http_client
    _http_client = httpx.AsyncClient(
        trust_env=False,
        limits=httpx.Limits(max_connections=48, max_keepalive_connections=16),
        timeout=httpx.Timeout(310.0, connect=25.0),
    )
    try:
        yield
    finally:
        cli = _http_client
        if cli is not None:
            await cli.aclose()
        _http_client = None


app = FastAPI(title="HomeClaw EnvoyMesh Channel", lifespan=_lifespan)


def _shared_http() -> httpx.AsyncClient:
    http = _http_client
    if http is None:
        raise RuntimeError("EnvoyMesh channel HTTP pool not initialized (lifespan not run)")
    return http


# ── config ──────────────────────────────────────────────────────────────────

# Module-level config cache. Set by _reload_config(); may be overridden by
# _core_overrides (set by Core before calling main()/run_channel()).
_cfg: dict = {}
BRIDGE_URL: str = ""
BRIDGE_SECRET: str = ""
CHANNEL_NAME: str = ""
HC_USER_ID: str = ""

# Config overrides from Core (populated before main()/run_channel() is called).
_core_overrides: Optional[dict] = None


def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "config.yml"
    with open(cfg_path, "r") as fh:
        return yaml.safe_load(fh) or {}


def _reload_config() -> None:
    """(Re)load config from disk and environment. Called once at module load
    and again by run_channel() if Core overrides are passed."""
    global _cfg, BRIDGE_URL, BRIDGE_SECRET, CHANNEL_NAME, HC_USER_ID
    _cfg = _load_config()
    # Env vars take precedence over config.yml, then Core overrides take final precedence
    BRIDGE_URL = os.getenv("ENVOYMESH_BRIDGE_URL", _cfg.get("bridge_url", "http://127.0.0.1:3031/bridge/send"))
    BRIDGE_SECRET = os.getenv("ENVOYMESH_BRIDGE_SECRET", _cfg.get("bridge_secret", ""))
    CHANNEL_NAME = os.getenv("ENVOYMESH_CHANNEL_NAME", _cfg.get("name", "envoymesh"))
    HC_USER_ID = os.getenv("ENVOYMESH_USER_ID", _cfg.get("user_id", "AllenPeng"))
    # Apply Core overrides (highest precedence after env vars)
    if _core_overrides:
        BRIDGE_URL = _core_overrides.get("bridge_url", BRIDGE_URL)
        BRIDGE_SECRET = _core_overrides.get("bridge_secret", BRIDGE_SECRET)
        CHANNEL_NAME = _core_overrides.get("name", CHANNEL_NAME)
        HC_USER_ID = _core_overrides.get("user_id", HC_USER_ID)

_reload_config()


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
        # Deliver error to P2P sender if we can
        if sender_owner_id and sender_peer_id:
            try:
                await _reply_to_bridge(sender_peer_id, "Error: message must include fromOwnerId and text.")
            except Exception:
                pass
        return JSONResponse(
            status_code=400,
            content={"error": "fromOwnerId and text are required"},
        )

    # ── dedup check: skip duplicate messages within the cache window ────
    _msg_hash = hashlib.sha256(f"{sender_owner_id}:{text}".encode()).hexdigest()
    if _msg_hash in _dedup_cache:
        _cached_text, _cached_ts = _dedup_cache[_msg_hash]
        # Move to end (LRU: most recent)
        _dedup_cache.move_to_end(_msg_hash)
        logger.debug("[envoymesh] duplicate message from {} skipped: {}", sender_owner_id, text[:60])
        return {"text": _cached_text, "status": "ok", "warning": "deduplicated"}
    # Evict oldest if at capacity
    while len(_dedup_cache) >= _DEDUP_MAX:
        _dedup_cache.popitem(last=False)
    import time
    _dedup_cache[_msg_hash] = ("", time.time())  # placeholder, filled after reply

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
        _sent = await _reply_to_bridge(sender_peer_id, _cc)
        if not _sent:
            logger.warning("[envoymesh] ClawCode reply failed to reach bridge, but CLI result returned inline")
        _dedup_cache[_msg_hash] = (_cc, time.time())
        return {"text": _cc, "status": "clawcode"}

    # ── 3. Forward to Core ──────────────────────────────────────────────
    core_inbound_url = f"{core_url()}/inbound"
    headers = Util().get_channels_core_api_headers()
    try:
        r = await _shared_http().post(core_inbound_url, json=payload, headers=headers, timeout=300.0)
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
        _sent = await _reply_to_bridge(sender_peer_id, reply_text)
        if not _sent:
            logger.warning("[envoymesh] Core reply to bridge failed for {}", sender_peer_id)

    _dedup_cache[_msg_hash] = (reply_text, time.time())
    return {"text": reply_text, "status": "ok"}


# ── helpers ─────────────────────────────────────────────────────────────────

async def _reply_to_bridge(to: str, text: str) -> bool:
    """POST the Core reply back to EnvoyMesh bridge /bridge/send.

    Returns True if the bridge acknowledged the message, False otherwise.
    """
    try:
        r = await _shared_http().post(
            BRIDGE_URL,
            json={"to": to, "text": text},
            headers=_bridge_headers(),
            timeout=30.0,
        )
        if r.status_code == 200:
            logger.info(f"[envoymesh] reply sent to {to}: {text[:80]}...")
            return True
        else:
            logger.warning(f"[envoymesh] bridge returned {r.status_code}: {r.text}")
            return False
    except httpx.ConnectError:
        logger.error(f"[envoymesh] bridge unreachable at {BRIDGE_URL}")
        return False
    except Exception as e:
        logger.exception(f"[envoymesh] bridge reply failed: {e}")
        return False


# ── entry points ────────────────────────────────────────────────────────────

def run_channel(config_overrides: Optional[dict] = None) -> None:
    """Start the EnvoyMesh channel with optional config overrides from Core.

    Args:
        config_overrides: dict with optional keys bridge_url, bridge_secret,
                          name, user_id, port, host. Set by Core when auto-starting.
    """
    global _core_overrides
    if config_overrides:
        _core_overrides = config_overrides
        _reload_config()
    import uvicorn
    port = int(os.getenv("ENVOYMESH_PORT", str(_cfg.get("port", 8010))))
    host = os.getenv("ENVOYMESH_HOST", _cfg.get("host", "0.0.0.0"))
    if config_overrides:
        port = int(config_overrides.get("port", port))
        host = config_overrides.get("host", host)
    logger.info(f"[envoymesh] starting on {host}:{port}, bridge → {BRIDGE_URL}, user → {HC_USER_ID}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    run_channel()


if __name__ == "__main__":
    main()
