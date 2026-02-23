# Heuristic layer: factors for local vs cloud

**Status:** Discussion. For now we **keep the heuristic simple**: keyword rules + long-input only; no extra factors.  
**Goal:** Clarify what the heuristic layer uses today and what other factors we could add later if needed.

---

## 1. Current factors

Today the heuristic layer (Layer 1) uses only:

| Factor | Config / data | Behavior |
|--------|----------------|----------|
| **Keyword rules** | `heuristic_rules.yml` → `rules[]` with `route` + `keywords` | First rule whose keyword (substring, normalized) matches the query wins. No threshold; match → use that route. |
| **Long input** | `long_input_chars`, `long_input_route` in same YAML | If `len(query) > long_input_chars`, return `long_input_route` (e.g. cloud) before checking keywords. |

So we have **two** inputs to the heuristic:

- **Query text** (user message) — for length and keyword matching.
- **Rules data** — loaded once from YAML.

The router in core only passes **query** and **rules_data**; no other context.

---

## 2. Other factors we could add

These are **candidates** for future heuristic (or a pre-heuristic) step. All should stay **cheap** (no embedding, no LLM).

| Factor | What we’d use | Route bias | Notes |
|--------|----------------|------------|--------|
| **Short query** | `len(query) <= N` (e.g. 80 chars) | Optional “short → local” for very simple one-liners (e.g. “几点了”, “screenshot”) | Overlaps with keywords; might still help when no keyword matches. Could be a single band: `short_input_chars` + `short_input_route`. |
| **Message count / turn** | `len(messages)` or “is first message” | E.g. first message only → heuristic; follow-ups might need more context → cloud | Requires core to pass `messages` (or turn index) into the router. |
| **Has media** | `request.images` or `request.files` non-empty | Often vision or “explain this image” → cloud (unless we have a strong local vision model) | Request is available in `answer_from_memory(request=request)`. We’d pass a flag like `has_images=True` into heuristic. |
| **Multiple questions** | Heuristic count of `?` or “and” / “以及” / “还有” | Multiple questions → cloud | Pure text from query; no new context. |
| **Complexity phrases** | Extra keyword-style rules | E.g. “step by step”, “explain in detail”, “compare A and B” → cloud | Already partly covered by existing cloud keywords (explain, analyze, compare). Can add more in YAML. |
| **Language / script** | e.g. “mostly CJK” vs “mostly Latin” | Weak signal; could bias default or which keyword set to prefer | Low priority; adds complexity. |

---

## 3. What we’d need to change

- **Heuristic layer API**  
  Today: `run_heuristic_layer(query, rules_data, enabled)`.  
  To support “has media” or “message count”, we’d add optional **context**: e.g. `run_heuristic_layer(query, rules_data, enabled, context=None)` with `context = {"has_images": bool, "message_count": int, "query_length": int}`. Rules could then say “if has_images and no keyword match → cloud”.

- **Rules format**  
  Option A: Keep only keywords + long_input; add **optional bands** in YAML, e.g.  
  `short_input_chars: 80`, `short_input_route: local`,  
  `has_media_route: cloud`.  
  Option B: Add a small “conditions” block per rule (e.g. “if query_length &gt; 500 and no keyword match → cloud”). Option A is simpler and stays first-match-wins.

- **Core**  
  When calling the heuristic, build `context` from `request` and `messages` (e.g. `has_images=bool(request.images)`, `message_count=len(messages)`), and pass it into `run_heuristic_layer`. Heuristic uses context only for the new bands (short_input, has_media), not for keyword matching (keyword match still wins first).

---

## 4. Recommendation

- **Keep** keyword rules + long_input as the main heuristic; they’re simple and effective.
- **Consider adding** (in order of impact vs effort):
  1. **Short-input band** — e.g. `short_input_chars: 80`, `short_input_route: local` — so very short queries that don’t match any keyword can still be biased local (optional; can default to “no short band”).
  2. **Has-media route** — if `request.images` or `request.files` is non-empty and no keyword matched, use `has_media_route` (e.g. cloud) so “explain this image” goes to cloud unless a keyword says otherwise.
  3. **Message count** — only if we see real misuse (e.g. long threads always going local); otherwise leave to semantic/perplexity.

No need for a threshold on the heuristic; “first match wins” (including long/short bands) is enough. New factors should be **additive options** in config and rules so existing deployments stay unchanged.
