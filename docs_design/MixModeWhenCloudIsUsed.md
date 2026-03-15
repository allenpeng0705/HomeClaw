# When does mix mode use the cloud model?

In **mix** mode (`main_llm_mode: mix`), the cloud model is used only in these cases:

## 1. Router selects cloud (first call)

Before the first LLM call, the hybrid router picks **local** or **cloud**. Cloud is chosen when:

- **Vision:** The request contains images and the local model does not support vision (cloud does). → `route=cloud`, layer=vision_fallback.
- **Heuristic (Layer 1):** A rule in `config/hybrid/heuristic_rules.yml` matches and has `route: cloud`. Rules are evaluated in order; **first match wins**. So if a "local" rule matches first, cloud is never chosen.
- **Long input:** Query length &gt; `long_input_chars` (e.g. 4000) and `long_input_route: cloud` in heuristic rules.
- **Semantic (Layer 2):** Query is similar enough to `cloud_utterances` in `config/hybrid/semantic_routes.yml` and score ≥ `semantic.threshold` (e.g. 0.5).
- **Layer 3 (SLM):** Perplexity or classifier model selects cloud.
- **Default when nothing else matches:** If all layers leave `route` unset, `route = default_route`. With `default_route: local` (typical), that means **local**. So with default config, most requests go to local unless one of the above selects cloud.

So if you never see cloud on the first call, either:

- No heuristic/semantic/slm rule is matching to cloud for your queries, and
- `default_route` is `local`, so any request that doesn’t match a cloud rule uses local.

## 2. Fallback after local fails (retry with cloud)

Even when the router chose **local**, we **retry with cloud** in these cases:

- The local LLM call **raised** (timeout, connection error, 500, etc.), or
- The local LLM **returned a message** but with **empty or very short content** and **no usable tool_calls** (e.g. truncated response, malformed tool_calls).

So cloud can still run as a fallback. If the local model always returns *some* valid content or tool_calls, fallback to cloud will not run.

## How to make cloud trigger more often

1. **Prefer cloud by default**  
   In `config/llm.yml` under `hybrid_router`, set:
   ```yaml
   default_route: cloud
   ```
   Then any request that doesn’t get a route from heuristic/semantic/slm will use cloud first.

2. **Add heuristic rules for your intents**  
   In `config/hybrid/heuristic_rules.yml`, add rules **before** any broad local rules so they match first, for example:
   ```yaml
   - route: cloud
     keywords:
       - 总结
       - summarize
       - slides
       - 幻灯片
       - html slides
   ```
   (Order matters: first matching rule wins.)

3. **Rely on fallback**  
   Keep `default_route: local` and `fallback_on_llm_error: true`. Cloud will be used when local fails or returns empty/no usable tool_calls.

4. **Check logs**  
   You should see an INFO line per request like:
   ```text
   Mix mode: route=local (layer=default_route) — cloud is used only when route=cloud or on fallback after local fails
   ```
   or `route=cloud (layer=heuristic)` (or semantic/perplexity/vision_fallback). When we fallback to cloud you’ll see a `[mix]` log like “retrying with cloud (cloud_models/...)”.

## Summary

- **Cloud is not used by default** when `default_route: local` and no layer selects cloud.
- **Cloud is used** when: the router sets route=cloud (vision/heuristic/semantic/slm/default_route), or when we fallback after local fails or returns empty/no usable tool_calls.
- To see cloud more often: set `default_route: cloud`, or add heuristic (or semantic) rules that match your queries to cloud.
