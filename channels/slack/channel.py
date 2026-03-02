"""
Minimal Slack channel using Core POST /inbound (Socket Mode: no public URL needed).
Supports text and file attachments. Run: set SLACK_APP_TOKEN, SLACK_BOT_TOKEN in channels/.env.
Add slack_<user_id> to config/user.yml (im: list) for allowed users.
"""
import base64
import os
import signal
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx
from loguru import logger

# Core connection: channels/.env only (build URL from env we load so path is unambiguous)
_channel_env = _root / "channels" / ".env"
load_dotenv(_channel_env)
from base.util import Util
# Build Core URL from this .env so we don't depend on Util().root_path() resolution
if os.environ.get("CORE_URL"):
    CORE_URL = (os.environ.get("CORE_URL") or "").rstrip("/")
else:
    _host = os.environ.get("core_host", "127.0.0.1")
    _core_port = os.environ.get("core_port", "9000")
    CORE_URL = f"http://{_host}:{_core_port}"
# Port for log messages (parse from URL so 502 hints use the actual port)
try:
    _parsed = urlparse(CORE_URL)
    _core_port = str(_parsed.port) if _parsed.port else (os.environ.get("core_port", "9000"))
except Exception:
    _core_port = os.environ.get("core_port", "9000")
INBOUND_URL = f"{CORE_URL}/inbound"

# Bot tokens: channels/.env or channels/slack/.env (loaded after CORE_URL so they cannot override core_host/core_port)
load_dotenv(Path(__file__).resolve().parent / ".env")
# Log Core URL so you can verify channel uses the same port as browser (e.g. http://127.0.0.1:10056)
logger.info("Slack channel Core URL: {} (POST {} for messages)", CORE_URL, INBOUND_URL)
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # xapp-...
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-...

if not SLACK_APP_TOKEN or not SLACK_BOT_TOKEN:
    raise SystemExit("Set SLACK_APP_TOKEN and SLACK_BOT_TOKEN in .env or environment")


def download_slack_file_to_data_url(url: str, bot_token: str, content_type: Optional[str] = None) -> Optional[str]:
    """Download Slack file URL (with auth) and return data URL. Never raises."""
    try:
        headers = {"Authorization": f"Bearer {bot_token}"}
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            r = client.get(url, headers=headers)
        if r.status_code != 200 or not r.content:
            return None
        ct = content_type or r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        b64 = base64.b64encode(r.content).decode("ascii")
        return f"data:{ct};base64,{b64}"
    except Exception:
        return None


def post_to_core_sync(
    user_id: str,
    user_name: str,
    text: str,
    images: Optional[List[str]] = None,
    videos: Optional[List[str]] = None,
    audios: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
) -> dict:
    """Returns {"text": str, "images": list} so the caller can post text and upload response images (e.g. from image generation)."""
    payload = {
        "user_id": user_id,
        "text": text or "(no text)",
        "channel_name": "slack",
        "user_name": user_name,
        "async": False,  # Slack channel expects sync response (Core returns 200 + {text}; we do not poll)
        "reply_accepts": ["text", "image"],
    }
    if images:
        payload["images"] = images
    if videos:
        payload["videos"] = videos
    if audios:
        payload["audios"] = audios
    if files:
        payload["files"] = files
    _preview = (text or "(no text)")[:80]
    if len(text or "") > 80:
        _preview += "..."
    logger.info("slack → core: user_id={} text={!r} url={}", user_id, _preview, INBOUND_URL)
    reply = ""
    try:
        api_key = (os.environ.get("CORE_API_KEY") or "").strip()
        headers = {"x-api-key": api_key, "Authorization": f"Bearer {api_key}"} if api_key else {}
        r = None
        retry_delays = (10, 20, 30)  # seconds: 3 retries (total wait up to 60s) after Core restart
        for attempt in range(1 + len(retry_delays)):
            try:
                # trust_env=False so we connect directly to Core (no HTTP_PROXY); browser and channel must see same server
                with httpx.Client(timeout=120.0, trust_env=False) as client:
                    r = client.post(INBOUND_URL, json=payload, headers=headers)
                break
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt < len(retry_delays):
                    delay = retry_delays[attempt]
                    logger.warning(
                        "slack → core: connection failed (attempt {}), retrying in {}s (Core may be starting): {}",
                        attempt + 1, delay, e,
                    )
                    time.sleep(delay)
                else:
                    logger.warning("slack → core: connection failed after {} attempts url={} error={}", attempt + 1, INBOUND_URL, e)
                    raise
        text = (r.text or "").strip() if r else ""
        if not text:
            # Probe same host:port to see what is actually answering (Core returns JSON for GET /ready)
            try:
                with httpx.Client(timeout=3.0, trust_env=False) as c:
                    probe = c.get(f"{CORE_URL}/ready", headers=headers)
                logger.warning(
                    "slack ← core: empty body status={} url={}. Same host GET /ready -> status={} body_len={}. "
                    "502 = Bad Gateway: a proxy/tunnel may be on this port instead of Core. "
                    "Run Core first (python -m main start). Ensure config/core.yml port matches channels/.env core_port (e.g. {}). Check: netstat -ano | findstr :{}",
                    getattr(r, "status_code", 0), INBOUND_URL, probe.status_code, len(probe.text or ""), _core_port, _core_port,
                )
            except Exception as pe:
                logger.warning(
                    "slack ← core: empty body status={} url={}. Probe /ready failed: {}. Another process may be on this port; start only Core (python -m main start) then run Slack channel.",
                    getattr(r, "status_code", 0), INBOUND_URL, pe,
                )
            reply = "Request failed (502 Bad Gateway). Run Core first (python -m main start). Ensure config/core.yml port and channels/.env core_port match (e.g. {}).".format(_core_port) if (r and r.status_code == 502) else ("Request failed (empty response)" if (r and r.status_code != 200) else "(no reply)")
        else:
            try:
                data = r.json()
            except ValueError:
                body_preview = text[:120] + ("..." if len(text) > 120 else "")
                logger.warning(
                    "slack ← core: non-JSON status={} body={!r}",
                    r.status_code, body_preview,
                )
                reply = f"Request failed (non-JSON response, status {r.status_code})"
            else:
                reply = data.get("text", "")
                if not reply and r.status_code != 200:
                    reply = data.get("error", "Request failed")
                if r.status_code == 202 and data.get("request_id"):
                    logger.warning(
                        "slack ← core: Core returned 202 (async); Slack channel expects sync. Poll GET /inbound/result?request_id={} or ensure no client sends async: true.",
                        data.get("request_id", "")[:12],
                    )
                    reply = reply or "Core is processing in background (async mode); reply will not appear here."
                response_images = data.get("images") or []
                _out_preview = (reply or "(no reply)")[:80] + ("..." if len(reply or "") > 80 else "")
                logger.info("slack ← core: user_id={} reply={!r} images={}", user_id, _out_preview, len(response_images))
                return {"text": reply or "(no reply)", "images": response_images}
            # ValueError or empty body / not text: reply already set
            return {"text": reply or "(no reply)", "images": []}
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        logger.warning("slack → core: connection failed url={} error={}", INBOUND_URL, e)
        reply = "Core unreachable. If you just restarted Core, try your message again or restart the Slack channel (python -m channels.run slack)."
    except Exception as e:
        logger.warning("slack → core: request failed error={}", e)
        reply = f"Error: {e}"
    return {"text": reply or "(no reply)", "images": []}


def main():
    try:
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.socket_mode.request import SocketModeRequest
    except ImportError:
        raise SystemExit("Install slack_sdk: pip install -r requirements.txt")

    web_client = WebClient(token=SLACK_BOT_TOKEN)
    # Bot user ID: ignore message events from our own replies (Slack sends events for bot messages too).
    try:
        bot_user_id = (web_client.auth_test() or {}).get("user_id", "") or ""
    except Exception:
        bot_user_id = ""
    socket_client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

    def process(client: SocketModeClient, req: SocketModeRequest):
        if req.type != "events_api":
            return
        event = req.payload.get("event", {})
        if event.get("type") != "message" or event.get("subtype"):
            return
        text = (event.get("text") or "").strip()
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        ts = event.get("ts", "")
        if not user_id or not channel_id:
            return
        if bot_user_id and user_id == bot_user_id:
            return  # ignore our own bot's messages (avoid echo loop)
        images, videos, audios, files = [], [], [], []
        for f in event.get("files") or []:
            url = f.get("url_private") or f.get("url_private_download")
            if not url:
                continue
            mimetype = (f.get("mimetype") or "").lower()
            data_url = download_slack_file_to_data_url(url, SLACK_BOT_TOKEN, f.get("mimetype"))
            if not data_url:
                continue
            if "image/" in mimetype:
                images.append(data_url)
            elif "video/" in mimetype:
                videos.append(data_url)
            elif "audio/" in mimetype:
                audios.append(data_url)
            else:
                files.append(data_url)
        if not text and not (images or videos or audios or files):
            return
        if not text:
            text = "Image" if images else "Video" if videos else "Audio" if audios else "File" if files else "(no text)"
        # Acknowledge immediately
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        try:
            u = web_client.users_info(user=user_id)
            user_name = (u.get("user") or {}).get("real_name") or user_id
        except Exception:
            user_name = user_id
        inbound_id = f"slack_{user_id}"
        _msg_preview = (text or "(media only)")[:80] + ("..." if len(text or "") > 80 else "")
        logger.info("slack received: user_id={} ({}) text={!r}", inbound_id, user_name, _msg_preview)
        result = post_to_core_sync(
            inbound_id,
            user_name,
            text,
            images=images if images else None,
            videos=videos if videos else None,
            audios=audios if audios else None,
            files=files if files else None,
        )
        reply_text = result.get("text", "") or "(no reply)"
        reply_images = result.get("images") or []
        try:
            web_client.chat_postMessage(channel=channel_id, thread_ts=ts, text=reply_text[:4000] if len(reply_text) > 4000 else reply_text)
            for i, data_url in enumerate(reply_images[:5]):
                raw = Util.data_url_to_bytes(data_url)
                if not raw:
                    continue
                ext = "png" if "png" in (data_url[:50] or "") else "jpg"
                web_client.files_upload(
                    channels=channel_id,
                    thread_ts=ts,
                    content=raw,
                    filename=f"image_{i}.{ext}",
                    title="",
                )
        except Exception as e:
            logger.warning("slack post to channel failed: {}", e)

    socket_client.socket_mode_request_listeners.append(process)
    # Channel connects to Core via HTTP (GET /ready, POST /inbound)—same as browser. No separate socket.
    logger.info("Slack channel will connect to Core at {} (GET /ready, POST /inbound). If this URL is wrong, fix core_host/core_port in channels/.env", CORE_URL)
    # Startup: wait for Core to be reachable (retry every 10s for up to 90s so "restart Core then Slack" works)
    api_key = (os.environ.get("CORE_API_KEY") or "").strip()
    h = {"x-api-key": api_key, "Authorization": f"Bearer {api_key}"} if api_key else {}
    startup_wait_sec = 90
    startup_interval_sec = 10
    core_ready = False
    for waited in range(0, startup_wait_sec, startup_interval_sec):
        try:
            with httpx.Client(timeout=5.0, trust_env=False) as c:
                probe = c.get(f"{CORE_URL}/ready", headers=h)
            if probe.text and len(probe.text.strip()) > 0 and probe.status_code == 200:
                logger.info("Core reachable: GET /ready -> status={} body_len={}", probe.status_code, len(probe.text or ""))
                core_ready = True
                break
            if probe.status_code == 502:
                logger.warning(
                    "Core at {} returned 502 (not Core—a proxy/tunnel may be on this port). "
                    "Fix: (1) Start Core (python -m main start) so it binds to the port in config/core.yml. "
                    "(2) Ensure channels/.env core_port matches (e.g. {}). Check: netstat -ano | findstr :{}",
                    CORE_URL, _core_port, _core_port,
                )
            else:
                logger.warning("Core at {} returned status={} empty={}. Retrying in {}s.", CORE_URL, probe.status_code, not (probe.text or "").strip(), startup_interval_sec)
        except Exception as e:
            logger.warning("Core not reachable at {} (waited {}s): {}. Retrying in {}s.", CORE_URL, waited, e, startup_interval_sec)
        if waited + startup_interval_sec < startup_wait_sec:
            time.sleep(startup_interval_sec)
    if not core_ready:
        logger.warning(
            "Core still not reachable at {} after {}s. "
            "Start Core (python -m main start). Ensure config/core.yml port and channels/.env core_port match (e.g. {}). Check: netstat -ano | findstr :{}",
            CORE_URL, startup_wait_sec, _core_port, _core_port,
        )

    logger.info("Slack channel: forwarding to {} (Socket Mode)", INBOUND_URL)
    socket_client.connect()
    # connect() returns immediately; keep process alive until Ctrl+C.
    _stop = False

    def _on_sig(*_args):
        nonlocal _stop
        _stop = True

    signal.signal(signal.SIGINT, _on_sig)
    signal.signal(signal.SIGTERM, _on_sig)
    try:
        while not _stop:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    logger.info("Slack channel stopped.")


if __name__ == "__main__":
    main()
