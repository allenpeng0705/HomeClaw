#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
Answer Overflow skill script for HomeClaw run_skill.

Search indexed Discord community discussions via the Answer Overflow MCP server.
No API key required — uses the public MCP endpoint.

Usage:
  request.py search <query> [limit]          — search Answer Overflow
  request.py servers [query] [limit]          — list/search Discord servers
  request.py thread <thread_id> [limit]       — fetch thread messages
  request.py similar <query> <server_id> [n]  — find similar threads
  request.py explore [topic]                  — discover servers by topic
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

# Answer Overflow MCP endpoint
_MCP_URL = "https://www.answeroverflow.com/mcp"
_ACCEPT = "application/json, text/event-stream"
_CONTENT_TYPE = "application/json"


def _call_mcp(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call Answer Overflow MCP tool. Returns parsed JSON result or error dict."""
    import urllib.request

    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            _MCP_URL,
            data=payload,
            headers={"Accept": _ACCEPT, "Content-Type": _CONTENT_TYPE},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"success": False, "error": f"MCP request failed: {e}"}

    # SSE-encoded response: "event: message\ndata: {...json...}"
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                if isinstance(data, dict):
                    if "error" in data:
                        return {"success": False, "error": data["error"]}
                    content = data.get("result", {}).get("content", [])
                    if content and isinstance(content, list) and content[0].get("type") == "text":
                        return {"success": True, "data": json.loads(content[0]["text"])}
                    return {"success": True, "data": data.get("result", {})}
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    return {"success": False, "error": "No parseable response from MCP server"}


def cmd_search(query: str, limit: int = 10, server_id: Optional[str] = None) -> int:
    args: Dict[str, Any] = {"query": query, "limit": min(limit, 25)}
    if server_id:
        args["serverId"] = server_id
    result = _call_mcp("search_answeroverflow", args)
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    data = result["data"]
    results = data.get("results", [])
    if not results:
        print("No results found. Try a different query.")
        return 0

    print(f"## Answer Overflow search: {query}\n")
    print(f"Found {len(results)} result(s)" + (f" (has more)" if data.get("hasMore") else ""))
    print()

    for i, r in enumerate(results, 1):
        title = r.get("threadTitle", "(no title)")
        server = r.get("serverName", "")
        channel = r.get("channelName", "")
        url = r.get("url", "")
        question = r.get("question", {})
        q_content = question.get("content", "") if isinstance(question, dict) else ""
        # Truncate long question content
        if len(q_content) > 300:
            q_content = q_content[:297] + "..."
        solution = r.get("solution")
        solved = "✓ solution" if solution else ""

        print(f"### {i}. {title}")
        if server or channel:
            print(f"- [{server}] #{channel} {solved}")
        if q_content:
            print(f"  {q_content[:400]}")
        if url:
            print(f"  🔗 {url}")
        print()

    print(f"*Run `request.py thread <thread_id>` to fetch full conversation.*")
    return 0


def cmd_servers(query: str = "", limit: int = 25) -> int:
    result = _call_mcp("search_servers", {"query": query, "limit": min(limit, 100)})
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    data = result["data"]
    servers = data.get("servers", [])
    if not servers:
        print("No servers found." if query else "No servers available.")
        return 0

    print(f"## Discord servers on Answer Overflow\n")
    for s in servers:
        name = s.get("name", "")
        desc = s.get("description", "")
        members = s.get("memberCount", 0)
        sid = s.get("id", "")
        print(f"- **{name}** ({members:,} members)")
        if desc:
            print(f"  {desc[:200]}")
        print(f"  ID: `{sid}` | 🔗 https://www.answeroverflow.com/c/{name.lower().replace(' ', '-')}")
        print()
    return 0


def cmd_thread(thread_id: str, limit: int = 50) -> int:
    result = _call_mcp("get_thread_messages", {"threadId": thread_id, "limit": min(limit, 100)})
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    data = result["data"]
    messages = data.get("messages", [])
    if not messages:
        print("No messages found for this thread.")
        return 0

    thread_title = ""
    for m in messages:
        if m.get("isThreadMessage"):
            thread_title = m.get("content", "")[:120]
            break

    print(f"## Thread: {thread_title or thread_id}\n")
    print(f"Total messages: {len(messages)}\n")

    for m in messages:
        author = m.get("authorName", "unknown")
        role = m.get("authorRole", "")
        timestamp = m.get("timestamp", "")
        content = m.get("content", "")
        is_solution = m.get("isSolution", False)
        is_thread_msg = m.get("isThreadMessage", False)

        role_str = f" [{role}]" if role else ""
        solved_tag = " ✅ SOLUTION" if is_solution else ""
        thread_tag = " [thread]" if is_thread_msg else ""

        ts_str = ""
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                ts_str = f" ({dt.strftime('%Y-%m-%d %H:%M')})"
            except Exception:
                pass

        print(f"**{author}**{role_str}{ts_str}{solved_tag}{thread_tag}")
        print(f"{content}")
        print()
    return 0


def cmd_similar(query: str, server_id: str, limit: int = 5) -> int:
    result = _call_mcp("find_similar_threads", {"query": query, "serverId": server_id, "limit": min(limit, 10)})
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    data = result["data"]
    threads = data.get("similarThreads", []) or data.get("threads", [])
    if not threads:
        print("No similar threads found.")
        return 0

    print(f"## Similar threads (server: {server_id})\n")
    for t in threads:
        title = t.get("threadTitle", t.get("title", ""))
        sid = t.get("serverId", "")
        url = t.get("url", "")
        snippet = t.get("snippet", "") or t.get("content", "")[:200]
        print(f"- **{title}**")
        if snippet:
            print(f"  {snippet[:200]}")
        if url:
            print(f"  🔗 {url}")
        print()
    return 0


def cmd_explore(topic: str = "") -> int:
    """Discover servers by topic, then show top threads."""
    q = topic.strip() if topic.strip() else "programming"
    result = _call_mcp("search_servers", {"query": q, "limit": 10})
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    servers = result["data"].get("servers", [])
    if not servers:
        print(f"No servers found for topic: {topic}")
        return 0

    print(f"## Servers related to: {q}\n")
    for s in servers:
        name = s.get("name", "")
        members = s.get("memberCount", 0)
        sid = s.get("id", "")
        print(f"- **{name}** ({members:,} members) — ID: `{sid}`")

    print("\nTop thread from each server:")
    for s in servers[:5]:
        name = s.get("name", "")
        sid = s.get("id", "")
        r = _call_mcp("search_answeroverflow", {"query": q, "serverId": sid, "limit": 1})
        results = r.get("data", {}).get("results", [])
        if results:
            top = results[0]
            title = top.get("threadTitle", "")
            url = top.get("url", "")
            print(f"\n  [{name}] {title}")
            if url:
                print(f"  🔗 {url}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  request.py search <query> [limit]       — search Answer Overflow", file=sys.stderr)
        print("  request.py servers [query] [limit]      — list/discover servers", file=sys.stderr)
        print("  request.py thread <thread_id> [limit]   — fetch thread messages", file=sys.stderr)
        print("  request.py similar <query> <server_id> [n] — find similar threads", file=sys.stderr)
        print("  request.py explore [topic]              — discover servers + top threads", file=sys.stderr)
        return 1

    cmd = sys.argv[1].strip().lower()

    if cmd == "search":
        if len(sys.argv) < 3:
            print("Error: search requires <query>", file=sys.stderr)
            return 1
        query = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        return cmd_search(query, limit)

    if cmd == "servers":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 25
        return cmd_servers(q, limit)

    if cmd == "thread":
        if len(sys.argv) < 3:
            print("Error: thread requires <thread_id>", file=sys.stderr)
            return 1
        tid = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        return cmd_thread(tid, limit)

    if cmd == "similar":
        if len(sys.argv) < 4:
            print("Error: similar requires <query> <server_id>", file=sys.stderr)
            return 1
        q = sys.argv[2]
        sid = sys.argv[3]
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        return cmd_similar(q, sid, n)

    if cmd == "explore":
        topic = sys.argv[2] if len(sys.argv) > 2 else ""
        return cmd_explore(topic)

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())