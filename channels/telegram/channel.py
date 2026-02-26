"""
Minimal Telegram channel using Core POST /inbound.
Supports text, photo, video, audio, voice, document. Run: set TELEGRAM_BOT_TOKEN in channels/.env.
Add telegram_<chat_id> to config/user.yml (im: list) for allowed users.
"""
import base64
import os
import asyncio
from typing import Optional, List, Tuple
from pathlib import Path

# Project root on path
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx

# Core connection: channels/.env only
load_dotenv(_root / "channels" / ".env")
from base.util import Util
CORE_URL = Util().get_channels_core_url()
INBOUND_URL = f"{CORE_URL}/inbound"

# Bot token: channels/.env or channels/telegram/.env
load_dotenv(Path(__file__).resolve().parent / ".env")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env or environment")


async def get_updates(offset: Optional[int]):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    payload = {"timeout": 30}
    if offset is not None:
        payload["offset"] = offset
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=payload, timeout=35)
    return r.json()


async def get_file_data_url(file_id: str, mime_prefix: str = "image/jpeg") -> Optional[str]:
    """Get file by file_id from Telegram, download, return data URL or None. Never raises."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
                params={"file_id": file_id},
                timeout=15.0,
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("ok"):
            return None
        file_path = (data.get("result") or {}).get("file_path")
        if not file_path:
            return None
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        async with httpx.AsyncClient() as client:
            r2 = await client.get(download_url, timeout=30.0)
        if r2.status_code != 200 or not r2.content:
            return None
        b64 = base64.b64encode(r2.content).decode("ascii")
        return f"data:{mime_prefix};base64,{b64}"
    except Exception:
        return None


def _extract_media_from_message(msg: dict) -> Tuple[str, List[str], List[str], List[str], List[str]]:
    """Return (text, images, videos, audios, files). Never raises."""
    text = (msg.get("text") or msg.get("caption") or "").strip()
    images, videos, audios, files = [], [], [], []
    # Photo: list of PhotoSize; take largest
    if "photo" in msg and msg["photo"]:
        photo_list = msg["photo"]
        largest = max(photo_list, key=lambda p: p.get("file_size") or 0)
        file_id = largest.get("file_id")
        if file_id:
            images.append(file_id)
    if "video" in msg and msg["video"]:
        file_id = (msg["video"] or {}).get("file_id")
        if file_id:
            videos.append(file_id)
    if "audio" in msg and msg["audio"]:
        file_id = (msg["audio"] or {}).get("file_id")
        if file_id:
            audios.append(file_id)
    if "voice" in msg and msg["voice"]:
        file_id = (msg["voice"] or {}).get("file_id")
        if file_id:
            audios.append(file_id)
    if "document" in msg and msg["document"]:
        file_id = (msg["document"] or {}).get("file_id")
        if file_id:
            files.append(file_id)
    return text, images, videos, audios, files


async def send_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text[:4096]}, timeout=30)


async def handle_message(
    chat_id: int,
    user_name: str,
    text: str,
    image_file_ids: Optional[List[str]] = None,
    video_file_ids: Optional[List[str]] = None,
    audio_file_ids: Optional[List[str]] = None,
    file_file_ids: Optional[List[str]] = None,
):
    user_id = f"telegram_{chat_id}"
    images, videos, audios, files = [], [], [], []
    if image_file_ids:
        for fid in image_file_ids[:5]:
            data_url = await get_file_data_url(fid, "image/jpeg")
            if data_url:
                images.append(data_url)
    if video_file_ids:
        for fid in video_file_ids[:3]:
            data_url = await get_file_data_url(fid, "video/mp4")
            if data_url:
                videos.append(data_url)
    if audio_file_ids:
        for fid in audio_file_ids[:3]:
            data_url = await get_file_data_url(fid, "audio/mpeg")
            if data_url:
                audios.append(data_url)
    if file_file_ids:
        for fid in file_file_ids[:3]:
            data_url = await get_file_data_url(fid, "application/octet-stream")
            if data_url:
                files.append(data_url)
    if not text:
        text = "Image" if images else "Video" if videos else "Audio" if audios else "File" if files else "(no text)"
    payload = {
        "user_id": user_id,
        "text": text,
        "channel_name": "telegram",
        "user_name": user_name or user_id,
    }
    if images:
        payload["images"] = images
    if videos:
        payload["videos"] = videos
    if audios:
        payload["audios"] = audios
    if files:
        payload["files"] = files
    try:
        headers = Util().get_channels_core_api_headers()
        async with httpx.AsyncClient() as client:
            r = await client.post(INBOUND_URL, json=payload, headers=headers, timeout=120.0)
        data = r.json()
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
    except Exception as e:
        reply = f"Error: {e}"
    await send_message(chat_id, reply or "(no reply)")


async def poll():
    offset = None
    while True:
        try:
            resp = await get_updates(offset)
            if not resp.get("ok"):
                print("Telegram API error:", resp)
                await asyncio.sleep(5)
                continue
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                from_user = msg.get("from", {})
                user_name = from_user.get("first_name", "") or from_user.get("username", "")
                text, img_ids, vid_ids, aud_ids, file_ids = _extract_media_from_message(msg)
                # If only media (no text), img_ids/vid_ids/aud_ids/file_ids are file_ids to resolve later
                has_media = bool(img_ids or vid_ids or aud_ids or file_ids)
                if not text and not has_media:
                    continue
                # Pass file_ids; handle_message will resolve to data URLs
                asyncio.create_task(
                    handle_message(
                        chat_id,
                        user_name,
                        text,
                        image_file_ids=img_ids or None,
                        video_file_ids=vid_ids or None,
                        audio_file_ids=aud_ids or None,
                        file_file_ids=file_ids or None,
                    )
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            print("Poll error:", e)
            await asyncio.sleep(5)


def main():
    print("Telegram channel: forwarding to", INBOUND_URL)
    print("Add telegram_<chat_id> to config/user.yml (im: [...] ) for allowed users.")
    asyncio.run(poll())


if __name__ == "__main__":
    main()
