"""
Minimal Discord channel using Core POST /inbound.
Run: set DISCORD_BOT_TOKEN in channels/.env; core connection from channels/.env (core_host, core_port or CORE_URL).
Add discord_<user_id> to config/user.yml (im: list) for allowed users.
"""
import os
import asyncio
from pathlib import Path

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


async def post_to_core(user_id: str, user_name: str, text: str, channel_name: str = "discord") -> str:
    payload = {
        "user_id": user_id,
        "text": text,
        "channel_name": channel_name,
        "user_name": user_name,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(INBOUND_URL, json=payload, timeout=120.0)
        data = r.json()
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
    except Exception as e:
        reply = f"Error: {e}"
    return reply or "(no reply)"


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
        if not message.content or not message.content.strip():
            return
        text = message.content.strip()
        user_id = f"discord_{message.author.id}"
        user_name = message.author.display_name or str(message.author)

        async with message.channel.typing():
            reply = await post_to_core(user_id, user_name, text)
        try:
            await message.reply(reply[:2000] if len(reply) > 2000 else reply)
        except discord.HTTPException:
            await message.channel.send(reply[:2000] if len(reply) > 2000 else reply)

    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
