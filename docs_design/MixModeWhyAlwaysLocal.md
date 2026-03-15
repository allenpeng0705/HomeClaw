# Mix mode: why it often uses the local model

When `main_llm_mode: mix`, the hybrid router chooses **local** or **cloud** per request. If you feel you are "always using local", it is usually due to these three factors.

---

## 1. Default route is local

In `config/llm.yml`:

```yaml
hybrid_router:
  default_route: local
```

**Effect:** If **no** layer (heuristic, semantic, perplexity) sets a route, the request uses `default_route` → **local**.

So by default, anything that doesn’t match a rule or semantic/perplexity decision goes to local.

---

## 2. Heuristic layer runs first and has many local rules

Order of layers:

1. **Vision override** (only when the request has images and local has no vision).
2. **Layer 1: Heuristic** (keywords + long-input).
3. **Layer 2: Semantic** (only if route is still `None`).
4. **Long-query rule** (`prefer_cloud_if_long_chars`) — only if route is still `None`.
5. **Layer 3: SLM** (perplexity or classifier) — only if route is still `None`.
6. **Fallback:** `route = default_route` (local).

Heuristic uses **first match wins**. In `config/hybrid/heuristic_rules.yml` there are many **local** rules that match very common intents, for example:

- Greetings: `hello`, `你好`, `hi`, `thanks`, etc. → **local**
- File/folder: `list folder`, `folder_list`, `file_read`, `列出目录`, etc. → **local**
- Time/reminders: `remind me`, `提醒`, `what time`, `几点了` → **local**
- Memory, profile, sessions, weather, web search, etc. → **local**

So for typical short queries (“你好”, “list my files”, “remind me in 5 min”), heuristic often matches a **local** rule first and sets `route = local`. Semantic and perplexity are then **skipped** because `route` is no longer `None`. Result: you see local most of the time.

---

## 3. Long queries still use default_route (local)

Config:

```yaml
prefer_cloud_if_long_chars: 800
```

In code, when the query is longer than this and no layer has set a route yet, the router does:

```python
route = default_route   # local
route_layer = "default_route"
```

So “long” here means “use **default_route** for long queries”, not “prefer cloud”. With `default_route: local`, long queries also go to **local** unless heuristic/semantic/perplexity already chose cloud.

---

## How to use cloud more

Choose one or more of the following.

### A. Change default to cloud

In `config/llm.yml`:

```yaml
hybrid_router:
  default_route: cloud
```

- **Effect:** Any request that no layer explicitly routes will use **cloud**.
- **Trade-off:** More traffic and cost on cloud; simple/greeting queries that today fall through to local will go to cloud.

### B. Rely less on heuristic (so semantic/perplexity can choose)

In `config/llm.yml`:

```yaml
hybrid_router:
  heuristic:
    enabled: false
```

- **Effect:** Heuristic is skipped. Semantic (and then perplexity, if enabled) decide; if they don’t, `default_route` is used.
- **Trade-off:** More requests will hit semantic/perplexity; you may see more cloud for “general” or creative queries, depending on semantic routes and perplexity threshold.

### C. Lower semantic threshold

```yaml
hybrid_router:
  semantic:
    enabled: true
    threshold: 0.35   # was 0.5; lower = more matches, more cloud when similarity to cloud utterances is moderate
```

- **Effect:** Semantic layer will choose a route (local or cloud) more often; with typical cloud utterances, this can send more queries to cloud.

### D. Make “general” or creative intents go to cloud in heuristic

In `config/hybrid/heuristic_rules.yml`, add or move **cloud** rules for intents you want on cloud (e.g. “explain”, “summarize”, “translate”, “write code”). Order matters: the **first** matching rule wins. So:

- Put **cloud** rules for those intents **before** very broad **local** rules, or
- Add new cloud rules with keywords that match “general” or creative questions you want on cloud.

---

## Quick check in logs

With `show_route_in_response: true` you see labels like `[Local · heuristic]` or `[Cloud · semantic]`. That tells you:

- **Layer:** heuristic / semantic / perplexity / default_route.
- **Route:** Local vs Cloud.

If you often see `[Local · heuristic]`, heuristic is matching first and choosing local; to use cloud more, adjust default_route, disable or reorder heuristic, or tune semantic/perplexity as above.

---

## Reference

- Routing logic: `core/llm_loop.py` (hybrid router block, ~lines 210–340).
- Heuristic: `hybrid_router/heuristic.py`; rules: `config/hybrid/heuristic_rules.yml`.
- Semantic: `hybrid_router/semantic.py`; utterances: `config/hybrid/semantic_routes.yml`.
- Config: `config/llm.yml` (`main_llm_mode`, `main_llm_local`, `main_llm_cloud`, `hybrid_router`).
