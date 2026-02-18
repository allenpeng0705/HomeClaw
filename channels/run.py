"""
Run a channel by name.

Usage: python -m channels.run <channel_name>

All channels live under channels/<name>/ and expose channel.py with main().
Run from repo root so that channels/ and config/ are on the path.

Supported channels: webhook, telegram, discord, slack, whatsapp, whatsappweb, matrix, wechat,
tinode, line, google_chat, signal, imessage, teams, webchat, zalo, feishu, dingtalk, bluebubbles.

Before calling the channel's main(), sys.argv is set to [argv[0]] so the channel
name is not seen by the channel's code (e.g. Tinode's argparse in work() uses
defaults instead of failing on the extra "tinode" argument).
"""
import sys
import importlib
from pathlib import Path

# Ensure project root on path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Channels that have channel.py with main() (inbound or full). Must match directory names.
CHANNELS = [
    "webhook",
    "telegram",
    "discord",
    "slack",
    "whatsapp",
    "whatsappweb",
    "matrix",
    "wechat",
    "tinode",
    "line",
    "google_chat",
    "signal",
    "imessage",
    "teams",
    "webchat",
    "zalo",
    "feishu",
    "dingtalk",
    "bluebubbles",
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m channels.run <channel_name>")
        print("Channels:", ", ".join(CHANNELS))
        sys.exit(1)
    name = sys.argv[1].strip().lower()
    if name not in CHANNELS:
        print(f"Unknown channel: {name}")
        print("Channels:", ", ".join(CHANNELS))
        sys.exit(1)
    try:
        mod = importlib.import_module(f"channels.{name}.channel")
    except ImportError as e:
        print(f"Cannot load channel '{name}': {e}")
        sys.exit(1)
    if not hasattr(mod, "main"):
        print(f"Channel '{name}' has no main()")
        sys.exit(1)
    # Leave only argv[0] so the channel's argparse (e.g. Tinode's work()) doesn't see the channel name
    _argv = sys.argv
    sys.argv = [_argv[0]]
    try:
        mod.main()
    finally:
        sys.argv = _argv


if __name__ == "__main__":
    main()
