---
name: answeroverflow
description: |
  Search indexed Discord community discussions via Answer Overflow. Find solutions to coding problems, library issues, and community Q&A that only exist in Discord conversations. Uses the Answer Overflow MCP server — no API key required.
keywords: [discord, answer overflow, community qa, search, tRPC, prisma, nextjs]
trigger:
  patterns: ["answeroverflow|answer\\s*overflow"]
  instruction: |
    The user wants to search Discord community Q&A via Answer Overflow. Use run_skill:
      run_skill(skill_name='answeroverflow-1.0.2', script='request.py', args=['search', '<query>', '[limit]'])
    To discover servers: args=['servers', '[query]', '[limit]']
    To fetch a thread: args=['thread', '<thread_id>', '[limit]']
    To find similar threads: args=['similar', '<query>', '<server_id>', '[n]']
    To explore by topic: args=['explore', '[topic]']
    Run search first to find thread IDs, then thread to get full conversation.
    Example: search "prisma connection pooling" → find thread → thread <id>
---

# Answer Overflow Skill

Search indexed Discord community discussions via [Answer Overflow](https://www.answeroverflow.com). No API key required — uses the public MCP server.

## run_skill

```text
run_skill(skill_name='answeroverflow-1.0.2', script='request.py', args=['search', 'nextjs app router'])
run_skill(..., args=['servers', 'prisma'])
run_skill(..., args=['thread', '1091112171133489162'])
```

| Action | Args | Description |
|--------|------|-------------|
| Search | `["search", "<query>", "[limit]"]` | Search all indexed Discord communities |
| Servers | `["servers", "[query]", "[limit]"]` | Discover indexed Discord servers |
| Thread | `["thread", "<thread_id>", "[limit]"]` | Fetch full thread conversation |
| Similar | `["similar", "<query>", "<server_id>", "[n]"]` | Find threads similar to query |
| Explore | `["explore", "[topic]"]` | Discover servers + top threads by topic |

## How it works

Answer Overflow indexes **public Discord support channels** and exposes them via an MCP server. This skill wraps the MCP tools:

| MCP Tool | Used by |
|----------|---------|
| `search_answeroverflow` | `search` command |
| `search_servers` | `servers` and `explore` commands |
| `get_thread_messages` | `thread` command |
| `find_similar_threads` | `similar` command |

## Typical workflow

1. **Search** for your topic:
   `["search", "prisma many-to-many relation"]`
2. Note the `threadId` from results
3. **Fetch the thread** for full context:
   `["thread", "<thread_id>"]`
4. Or **explore** a server:
   `["explore", "prisma"]` — shows servers + top threads

## Example searches

| Query | What you get |
|-------|-------------|
| `prisma connection pooling` | Prisma server threads about DB pooling |
| `nextjs app router redirect` | Next.js server threads about routing |
| `tRPC middleware auth` | tRPC server threads about auth middleware |

## Thread URL format

Threads on answeroverflow.com look like:
```
https://www.answeroverflow.com/m/<message_id>
```

The `thread_id` in commands is the numeric ID from the URL.

## Tips

- Results are real Discord conversations — context may be informal
- Threads often have back-and-forth before the solution
- Check `serverName` / `channelName` to understand the community
- Many open-source projects index their Discord support here (Prisma, tRPC, Kinde, Next.js, etc.)
- `search_servers` returns server IDs useful for filtered searches

## Limits

- Search: max 25 results per call
- Thread messages: max 100 per call
- Similar threads: max 10 per call
- No authentication required — public MCP endpoint

## Links

- **Website:** https://www.answeroverflow.com
- **MCP Docs:** https://www.answeroverflow.com/mcp
- **Discord:** https://discord.answeroverflow.com