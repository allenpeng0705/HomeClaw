"""
Minimal Discord channel using Core POST /inbound.
Supports text and attachments (image, video, audio, file). Run: set DISCORD_BOT_TOKEN in channels/.env.
Add discord_<user_id> to config/user.yml (im: list) for allowed users.
"""
import base64
import os
import asyncio
from pathlib import Path
from typing import List, Optional

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

# Bot token: channels/.env or channels/discord/.env
load_dotenv(Path(__file__).resolve().parent / ".env")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not DISCORD_BOT_TOKEN:
    raise SystemExit("Set DISCORD_BOT_TOKEN in .env or environment")


async def download_attachment_to_data_url(url: str, content_type: Optional[str] = None) -> Optional[str]:
    """Download Discord attachment URL and return data URL. Never raises."""
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(url, timeout=30.0)
        if r.status_code != 200 or not r.content:
            return None
        ct = content_type or r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        b64 = base64.b64encode(r.content).decode("ascii")
        return f"data:{ct};base64,{b64}"
    except Exception:
        return None


async def post_to_core(
    user_id: str,
    user_name: str,
    text: str,
    channel_name: str = "discord",
    images: Optional[List[str]] = None,
    videos: Optional[List[str]] = None,
    audios: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
) -> dict:
    """Returns {"text": str, "images": list} so caller can send response images (e.g. from image generation)."""
    payload = {
        "user_id": user_id,
        "text": text or "(no text)",
        "channel_name": channel_name,
        "user_name": user_name,
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
    try:
        headers = Util().get_channels_core_api_headers()
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(INBOUND_URL, json=payload, headers=headers, timeout=120.0)
        data = r.json() if r.content else {}
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
        reply_images = data.get("images") or []
        return {"text": reply or "(no reply)", "images": reply_images}
    except httpx.ConnectError:
        return {"text": "Core unreachable. Is HomeClaw running?", "images": []}
    except Exception as e:
        return {"text": f"Error: {e}", "images": []}


def main():
    try:
        import discord
        from discord.ext import commands
    except ImportError:
        raise SystemExit("Install discord.py: pip install -r requirements.txt")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"Discord channel: logged in as {bot.user}, forwarding to {INBOUND_URL}")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        text = (message.content or "").strip()
        user_id = f"discord_{message.author.id}"
        user_name = message.author.display_name or str(message.author)
        images, videos, audios, files = [], [], [], []
        for att in getattr(message, "attachments", [])[:10]:
            url = getattr(att, "url", None)
            if not url:
                continue
            content_type = getattr(att, "content_type", None) or ""
            data_url = await download_attachment_to_data_url(url, content_type)
            if not data_url:
                continue
            ct = (content_type or "").lower()
            if "image/" in ct:
                images.append(data_url)
            elif "video/" in ct:
                videos.append(data_url)
            elif "audio/" in ct:
                audios.append(data_url)
            else:
                files.append(data_url)
        if not text and not (images or videos or audios or files):
            return
        if not text:
            text = "Image" if images else "Video" if videos else "Audio" if audios else "File" if files else "(no text)"

        async with message.channel.typing():
            result = await post_to_core(
                user_id,
                user_name,
                text,
                images=images if images else None,
                videos=videos if videos else None,
                audios=audios if audios else None,
                files=files if files else None,
            )
        reply_text = result.get("text", "") or "(no reply)"
        reply_images = result.get("images") or []
        from io import BytesIO
        files_to_send = []
        for i, data_url in enumerate(reply_images[:5]):
            raw = Util.data_url_to_bytes(data_url)
            if raw:
                files_to_send.append(discord.File(BytesIO(raw), filename=f"image_{i}.png"))
        try:
            if files_to_send:
                await message.reply(content=reply_text[:2000] if reply_text else None, files=files_to_send)
            elif reply_text:
                await message.reply(reply_text[:2000])
        except discord.HTTPException:
            if files_to_send:
                await message.channel.send(content=reply_text[:2000] if reply_text else None, files=files_to_send)
            elif reply_text:
                await message.channel.send(reply_text[:2000])

    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
