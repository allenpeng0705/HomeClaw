#!/usr/bin/env python3
"""
Bridge: connect signal-cli daemon (--http) to the HomeClaw Signal channel.
- Subscribes to signal-cli's SSE stream (GET /api/v1/events).
- For each incoming Signal message: POST to the channel /message, then send the reply back via signal-cli send (JSON-RPC).

Usage:
  1. Start the Signal channel:  python -m channels.run signal
  2. Start signal-cli daemon:    signal-cli -u +YOUR_NUMBER daemon --http=127.0.0.1:8080
  3. Run this bridge:            python channels/signal/scripts/bridge-signal-cli-to-channel.py

Env (optional):
  SIGNAL_CLI_DAEMON_HTTP   Base URL of signal-cli daemon (default http://127.0.0.1:8080)
  CHANNEL_SIGNAL_URL       Channel /message URL (default http://127.0.0.1:8011/message)
"""
import json
import os
import sys
import time
import uuid
from collections import OrderedDict
from typing import Optional, Tuple

import httpx

# Dedupe: avoid forwarding the same message twice (same source + envelope timestamp) within DEDUPE_SECONDS
DEDUPE_SECONDS = 60
_seen: OrderedDict[Tuple[str, int], float] = OrderedDict()
_MAX_SEEN = 500

# Defaults: signal-cli daemon --http=127.0.0.1:8080, Signal channel on 8011
DAEMON_HTTP = os.environ.get("SIGNAL_CLI_DAEMON_HTTP", "http://127.0.0.1:8080").rstrip("/")
CHANNEL_URL = os.environ.get("CHANNEL_SIGNAL_URL", "http://127.0.0.1:8011/message")
# Set by run_bridge() after resolving daemon path (api/v1 or v1)
_RPC_URL: Optional[str] = None
DEBUG = os.environ.get("BRIDGE_DEBUG", "").strip().lower() in ("1", "true", "yes")


def extract_message_from_receive(params: dict) -> Tuple[Optional[str], Optional[str], str]:
    """Extract (source, message_text, recipient_for_reply) from a receive notification.
    Supports: (1) HTTP SSE format {"account":"+...", "envelope":{...}}; (2) JSON-RPC params {"envelope":{...}} or {"result":{"envelope":{...}}}.
    """
    result = params.get("result") if isinstance(params.get("result"), dict) else {}
    envelope = params.get("envelope") or result.get("envelope") or {}
    if not envelope:
        return None, None, ""
    source = (envelope.get("source") or envelope.get("sourceNumber") or "").strip()
    if not source:
        return None, None, ""

    # dataMessage: 1:1 or group incoming message (signal-cli uses "message", some docs use "body")
    data_msg = envelope.get("dataMessage") or {}
    msg_text = (data_msg.get("message") or data_msg.get("body") or "").strip()

    # syncMessage.sentMessage: e.g. sync from another device; optional to handle
    if not msg_text and envelope.get("syncMessage"):
        sent = envelope["syncMessage"].get("sentMessage") or {}
        msg_text = (sent.get("message") or "").strip()
        # destination is our account; for sync we might not reply
        dest = sent.get("destination") or sent.get("destinationNumber")
        if dest:
            return source, msg_text or "(sync)", str(dest)

    return source, msg_text or "(no text)", source


def _envelope_timestamp(params: dict) -> int:
    """Envelope timestamp for deduplication (0 if missing)."""
    envelope = params.get("envelope") or {}
    data_msg = envelope.get("dataMessage") or {}
    return int(envelope.get("timestamp") or data_msg.get("timestamp") or 0)


def _dedupe_then_process(source: str, msg_text: str, recipient: str, params: dict) -> bool:
    """Return True if we should process (not a duplicate). When True, caller must post and send reply."""
    key = (source, _envelope_timestamp(params))
    now = time.monotonic()
    cutoff = now - DEDUPE_SECONDS
    # Prune old entries by timestamp
    for k in list(_seen.keys()):
        if _seen[k] < cutoff:
            del _seen[k]
    if len(_seen) > _MAX_SEEN:
        for _ in range(len(_seen) - _MAX_SEEN):
            _seen.popitem(last=False)
    if key in _seen:
        if DEBUG:
            print(f"[bridge] DEBUG skip duplicate: {source} ts={key[1]}", file=sys.stderr)
        return False
    _seen[key] = now
    return True


def send_via_daemon(recipient: str, text: str) -> bool:
    """Send a message via signal-cli daemon JSON-RPC."""
    url = _RPC_URL or f"{DAEMON_HTTP}/api/v1/rpc"
    payload = {
        "jsonrpc": "2.0",
        "method": "send",
        "params": {"recipient": [recipient], "message": text},
        "id": str(uuid.uuid4()),
    }
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            r = client.post(url, json=payload)
        if r.status_code != 200:
            print(f"[bridge] send failed: HTTP {r.status_code} {r.text}", file=sys.stderr)
            return False
        data = r.json()
        if data.get("error"):
            print(f"[bridge] send error: {data['error']}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[bridge] send exception: {e}", file=sys.stderr)
        return False


def post_to_channel(user_id: str, text: str, user_name: str = "") -> dict:
    """POST to HomeClaw Signal channel; returns { text, images? }."""
    payload = {
        "user_id": user_id if user_id.startswith("signal_") else f"signal_{user_id}",
        "text": text,
        "user_name": user_name or user_id,
    }
    try:
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            r = client.post(CHANNEL_URL, json=payload)
        data = r.json() if r.content else {}
        return {"text": data.get("text", ""), "images": data.get("images")}
    except Exception as e:
        print(f"[bridge] channel POST failed: {e}", file=sys.stderr)
        return {"text": f"Error: {e}", "images": []}


def run_bridge():
    # signal-cli daemon --http exposes: GET /api/v1/events (SSE), POST /api/v1/rpc, GET /api/v1/check
    # Some builds or versions might use paths without /api; try check first to confirm daemon and path
    base = DAEMON_HTTP.rstrip("/")
    events_url = None
    rpc_url = None
    for prefix in ["/api/v1", "/v1"]:
        check_url = f"{base}{prefix}/check"
        try:
            r = httpx.get(check_url, timeout=5.0, trust_env=False)
            if r.status_code == 200:
                events_url = f"{base}{prefix}/events"
                rpc_url = f"{base}{prefix}/rpc"
                break
        except Exception:
            continue
    if events_url is None or rpc_url is None:
        print(f"[bridge] Cannot reach signal-cli daemon at {base}.", file=sys.stderr)
        print(f"[bridge] 1) Start daemon with HTTP: signal-cli -u +NUMBER daemon --http=127.0.0.1:8080", file=sys.stderr)
        print(f"[bridge] 2) Your signal-cli must support 'daemon --http' (see https://github.com/AsamK/signal-cli).", file=sys.stderr)
        print(f"[bridge] 3) If /api/v1/check returns 404, your signal-cli build may not include the HTTP server; use a recent release from https://github.com/AsamK/signal-cli/releases or build from source.", file=sys.stderr)
        sys.exit(1)

    # Use the discovered RPC URL for send
    global _RPC_URL
    _RPC_URL = rpc_url

    print(f"[bridge] Connecting to signal-cli daemon SSE: {events_url}", file=sys.stderr)
    print(f"[bridge] Channel URL: {CHANNEL_URL}", file=sys.stderr)
    print("[bridge] Listening for messages. Send a Signal message to your daemon number to test.", file=sys.stderr)
    if DEBUG:
        print("[bridge] DEBUG: raw SSE lines will be logged.", file=sys.stderr)

    with httpx.Client(timeout=None, trust_env=False) as client:
        try:
            with client.stream("GET", events_url) as resp:
                if resp.status_code != 200:
                    print(f"[bridge] SSE failed: HTTP {resp.status_code} for {events_url}. Daemon may not expose events on this path.", file=sys.stderr)
                    sys.exit(1)
                buffer = ""
                data_lines: list[str] = []
                for chunk in resp.iter_text():
                    if not chunk:
                        continue
                    buffer += chunk
                    while "\n" in buffer:
                        line, _, buffer = buffer.partition("\n")
                        raw = line.strip()
                        if raw.startswith("data:"):
                            data_lines.append(line[5:].strip())
                            # Try parsing immediately (many servers send one JSON per data line, no blank line after)
                            data = data_lines[0] if len(data_lines) == 1 else "\n".join(data_lines)
                            if data and data != "[done]":
                                try:
                                    obj = json.loads(data)
                                    # signal-cli HTTP SSE sends: event: receive + data: {"account":"+...", "envelope":{...}}
                                    # JSON-RPC style sends: data: {"jsonrpc":"2.0","method":"receive","params":{"envelope":{...}}}
                                    params = obj.get("params") if obj.get("method") == "receive" else (obj if obj.get("envelope") else None)
                                    if params is not None:
                                        data_lines = []  # consume event so we don't process again on blank line
                                        source, msg_text, recipient = extract_message_from_receive(params)
                                        if not source or not recipient:
                                            if DEBUG:
                                                print(f"[bridge] DEBUG receive ignored: no source/recipient", file=sys.stderr)
                                            continue
                                        if not msg_text or msg_text == "(sync)":
                                            if DEBUG:
                                                print(f"[bridge] DEBUG receive ignored: msg_text={msg_text!r}", file=sys.stderr)
                                            continue
                                        if not _dedupe_then_process(source, msg_text, recipient, params):
                                            continue
                                        print(f"[bridge] from {source}: {msg_text[:80]}...", file=sys.stderr)
                                        user_id = f"signal_{source.replace('+', '')}"
                                        result = post_to_channel(user_id, msg_text, user_name=source)
                                        reply = (result.get("text") or "").strip()
                                        if reply:
                                            send_via_daemon(recipient, reply)
                                            print(f"[bridge] replied to {recipient}", file=sys.stderr)
                                        continue
                                    if obj.get("method") != "receive" and not obj.get("envelope") and DEBUG:
                                        print(f"[bridge] DEBUG method={obj.get('method')}, keys={list(obj.keys())}, skipping.", file=sys.stderr)
                                except json.JSONDecodeError:
                                    pass  # might be multi-line; wait for blank line
                            continue
                        if raw.startswith(":"):
                            continue  # SSE comment (e.g. keepalive)
                        if raw.startswith("event:"):
                            # Still process any accumulated data from previous event
                            pass
                        # Empty line or other: end of SSE event; process accumulated data
                        if data_lines:
                            data = "\n".join(data_lines)
                            data_lines = []
                            if data == "[done]":
                                continue
                            if DEBUG:
                                print(f"[bridge] DEBUG data: {data[:300]}...", file=sys.stderr)
                            try:
                                obj = json.loads(data)
                            except json.JSONDecodeError as e:
                                if DEBUG:
                                    print(f"[bridge] DEBUG JSON error: {e}", file=sys.stderr)
                                continue
                            # HTTP SSE: data is {"account":"+...", "envelope":{...}}; JSON-RPC: {"method":"receive","params":{...}}
                            params = obj.get("params") if obj.get("method") == "receive" else (obj if obj.get("envelope") else None)
                            if params is None:
                                if DEBUG:
                                    print(f"[bridge] DEBUG method={obj.get('method')}, keys={list(obj.keys())}, skipping.", file=sys.stderr)
                                continue
                            source, msg_text, recipient = extract_message_from_receive(params)
                            if not source or not recipient:
                                if DEBUG:
                                    print(f"[bridge] DEBUG receive event ignored: no source/recipient (params keys: {list(params.keys())})", file=sys.stderr)
                                continue
                            if not msg_text or msg_text == "(sync)":
                                if DEBUG:
                                    print(f"[bridge] DEBUG receive event ignored: msg_text={msg_text!r}", file=sys.stderr)
                                continue  # skip sync-only events for now
                            if not _dedupe_then_process(source, msg_text, recipient, params):
                                continue
                            print(f"[bridge] from {source}: {msg_text[:80]}...", file=sys.stderr)
                            user_id = f"signal_{source.replace('+', '')}"
                            result = post_to_channel(user_id, msg_text, user_name=source)
                            reply = (result.get("text") or "").strip()
                            if reply:
                                send_via_daemon(recipient, reply)
                                print(f"[bridge] replied to {recipient}", file=sys.stderr)
                        if raw:
                            if DEBUG:
                                print(f"[bridge] DEBUG other line: {raw[:100]}", file=sys.stderr)
        except httpx.ConnectError as e:
            print(f"[bridge] Cannot connect to daemon at {DAEMON_HTTP}. Start signal-cli with: signal-cli -u +NUMBER daemon --http=127.0.0.1:8080", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("[bridge] Stopped.", file=sys.stderr)


if __name__ == "__main__":
    run_bridge()
