"""
Minimal Telegram channel using Core POST /inbound.
Run: set TELEGRAM_BOT_TOKEN in channels/.env; core connection from channels/.env (core_host, core_port or CORE_URL).
Add telegram_<chat_id> to config/user.yml (im: list) for allowed users.
"""
import os
import asyncio
from typing import Optional
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


async def send_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text}, timeout=30)


async def handle_message(chat_id: int, user_name: str, text: str):
    user_id = f"telegram_{chat_id}"
    payload = {
        "user_id": user_id,
        "text": text,
        "channel_name": "telegram",
        "user_name": user_name or user_id,
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
                if not msg or "text" not in msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = msg["text"].strip()
                if not text:
                    continue
                from_user = msg.get("from", {})
                user_name = from_user.get("first_name", "") or from_user.get("username", "")
                asyncio.create_task(handle_message(chat_id, user_name, text))
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
