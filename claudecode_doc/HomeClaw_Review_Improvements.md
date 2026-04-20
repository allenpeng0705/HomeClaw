# HomeClaw Code Review: Intent Router, Skill Router, Hybrid Router & Companion App

## 1. Intent Router Analysis

**File:** `base/intent_router.py`

### Current Implementation
- 1035 lines with multiple pre-emptive keyword checks before semantic routing
- Categories: `search_web`, `list_files`, `get_file_link`, `read_document`, `create_slides`, `create_html_slides`, `generate_pdf`, `summarize_to_page`, `send_email`, `schedule_remind`, `open_url`, `memory`, `knowledge_base`, `image`, `weather`, `news_digest`, `stock_monitor`, `greeting`, `identity_capabilities`, `general_chat`
- Modes: `static` (keyword only), `semantic` (vector only), `hybrid` (semantic + fallback to classifier)
- Tool verification phase (Phase 3.3) via `verify_tool_selection()`

### Strengths
1. **Comprehensive keyword pre-empts** - Weather, list_files, greeting, stock queries are caught before semantic to avoid embedding misclassifications
2. **Multi-language support** - Chinese phrases integrated throughout (`天气`, `提醒我`, `知识库`, etc.)
3. **Category tools filtering** - After routing, can filter tools/skills per category
4. **Recent context support** - Includes last N messages in router prompt
5. **Graceful fallbacks** - On parse failure/timeout returns `general_chat`
6. **Tool verification** - Optional LLM check before executing sensitive tools

### Issues & Improvements

#### Issue 1: Redundant Weather Checks ~~(DONE)~~
Weather was checked **twice** (lines 415-429 and lines 569-585) before semantic routing. The second check was unreachable in `semantic` and `hybrid` modes because the first early weather preempt returns before hot intents is reached. The `_wx` guard was effectively always True (never False when it mattered).

**Fix:** Removed the `_wx` weather-keyword computation and `not _wx` guard from hot intents (former lines 573-581). Simplified `if "search_web" in categories and not _wx:` to `if "search_web" in categories:`. Updated comment to explain that weather queries are caught by the early preempt before reaching hot intents.

#### Issue 2: Hardcoded Category List
`DEFAULT_CATEGORIES` is a static list at the module level. If new categories are added to intent category docs, this list may become stale.

**Fix:** Consider loading categories dynamically from `config/intent_category/*.md` or merge with config at startup.

#### Issue 3: Pattern Matching is Brittle
`_match_doc_category_patterns()` uses `re.search()` on user-provided patterns from YAML. Invalid regex in category docs could cause silent failures (caught but logged only).

**Fix:** Add validation of regex patterns at load time with a warning.

#### Issue 4: LLM Classifier Prompt Repetition
The system prompt in lines 830-833 is repeated with slight variations. The prompt includes the same instruction about HTML slides in both `recent_block` and non-recent_block cases.

**Fix:** DRY up the prompt construction.

#### Issue 5: No Cache for Semantic Router Results
`_route_semantic_intent()` is called potentially multiple times per request (once in semantic mode, once in hybrid mode). If semantic returns None, it's re-computed.

**Fix:** Cache semantic results within a single request context.

#### Issue 6: Tool Verification is Underutilized
`verify_tool_selection()` exists but `DEFAULT_VERIFY_TOOLS = ("exec", "file_write")` - only 2 tools. This feature seems incomplete.

**Fix:** Either expand the verification to more tools or remove the feature if not production-ready.

---

## 2. Skill Router Analysis

**File:** `base/skill_router.py`

### Current Implementation
- Semantic routing using vector embeddings (`search_skills_by_query`)
- Optional reranking with local model
- Union of semantic hits + trigger-matched skills + lexical overlap
- Confidence floor fallback to full catalog
- Usage-based reranking (`skills_usage_rerank_weight`)

### Strengths
1. **Hybrid approach** - Combines semantic + trigger patterns + lexical
2. **Usage-based reranking** - Learns from user interaction patterns
3. **Reranking with body content** - Can include skill body in rerank candidates
4. **Confidence floor** - Falls back to full catalog when similarity is low
5. **Test skills support** - `TEST_ID_PREFIX` for development

### Issues & Improvements

#### Issue 1: Skills Loaded Twice in Some Paths
When `union_trigger_matched_skills` or `union_lexical_skills` is enabled, `load_skills_from_dirs()` is called again to get `_all_skills_union`. This means skills are parsed from disk twice per request.

**Fix:** Cache the full catalog after first load and reuse within the same request.

#### Issue 2: No Priority/Weighting Between Union Sources
When a skill is found via semantic AND trigger matching, it may be added twice (though deduplicated by folder name). But there's no scoring difference - a trigger-matched skill counts the same as a high-similarity semantic hit.

**Fix:** Add scoring weights: semantic_hit_score * semantic_weight + trigger_match * trigger_weight.

#### Issue 3: `skills_max_in_prompt` Not Applied Before Reranking
Line 378: `skills_max` truncates after reranking. If reranking returns different results, the max may not be respected properly in edge cases.

**Fix:** Move truncation before final return or ensure reranking respects the cap.

#### Issue 4: Vector Store Delete on Load Failure
Line 140: `core.skills_vector_store.delete(hit_id)` - deleting from vector store because skill failed to load from disk seems aggressive. The skill file might be temporarily unavailable.

**Fix:** Log warning instead of auto-delete, or add retry logic.

#### Issue 5: No Skill Deprecation/Versioning
Skills can be added/removed but there's no mechanism to handle skill version changes affecting stored vector IDs.

**Fix:** Consider adding version hashes to skill IDs.

---

## 3. Hybrid Router Analysis

**Files:** `hybrid_router/heuristic.py`, `hybrid_router/semantic.py`, `hybrid_router/slm.py`, `hybrid_router/perplexity.py`

### Current Implementation
- **Layer 1 (Heuristic):** Keyword matching + long-input rule (4000+ char → cloud)
- **Layer 2 (Semantic):** `semantic-router` library with HomeClaw embedding encoder
- **Layer 3 (SLM):** Small local classifier or perplexity probe on main local model
- 3-layer cascade with configurable enable/disable per layer
- Metrics tracking via `hybrid_router/metrics.py`

### Strengths
1. **Cascade design** - Falls through layers, each more sophisticated
2. **Configurable defaults** - Each layer can be disabled independently
3. **Vision override** - Automatically routes to cloud when request has images but local doesn't support vision
4. **Per-tool retry logic** - `prefer_local_after_tools_in_mix_cloud` retries cloud→local for long outputs
5. **Usage metrics** - Tracks local/cloud usage for reporting

### Issues & Improvements

#### Issue 1: Heuristic Layer Uses Simple Substring Matching ~~(DONE)~~
```python
if _normalize(kw) in normalized_query:  # substring match
```
This produced false positives (e.g., "python" matched "pythonista", "cpu" matched "CPU prices").

**Fix:** Added `_keyword_needs_word_boundary()` helper. Single-word ASCII letter-only keywords (e.g. `cpu`, `password`) now use word-boundary regex (`\bcpu\b`) to avoid false positives. Keywords with spaces, non-ASCII (Chinese), digits, underscores, or special chars (e.g. `api_key`, `.pdf`, `take a screenshot`) continue to use substring matching. Invalid regex patterns fall back to substring match.

#### Issue 2: Heuristic Rules File is Massive (3600+ lines)
The `config/hybrid/heuristic_rules.yml` is very large and hard to maintain.

**Fix:** Consider auto-generating from semantic router feedback or organizing into categories.

#### Issue 3: Semantic Router Cache Key is Too Simple ~~(DONE)~~
Cache key is just `routes_path or "default"`. If utterances change, cache is stale until process restart.

**Fix:** Added `_semantic_router_cache_key()` that includes the routes file's mtime in the cache key. When the file changes, the mtime changes → new cache key → fresh router built. Commit `c0d0687`.

#### Issue 4: SLM Layer Assumes Same Model Format
`resolve_slm_model_ref()` handles both llama.cpp and Ollama, but the parsing logic in `slm.py` line 46-56 is convoluted - it tries multiple URL construction methods.

**Fix:** Simplify URL construction using a helper in `base.util`.

#### Issue 5: Perplexity Threshold is Hardcoded ~~(DONE)~~
`threshold: float = -0.6` in `run_perplexity_probe_async()`. This threshold may need tuning per model.

**Fix:** Already resolved - threshold is configurable via `hybrid_router.slm.perplexity_threshold` in `config/llm.yml` (set to `-0.4` by default). The code at `llm_loop.py:1458` reads: `probe_threshold = float(slm_cfg.get("perplexity_threshold") or -0.6)`.

#### Issue 6: No Fallback Chain Customization
If Layer 1 matches, Layer 2 and 3 are skipped. There's no config to change this cascade order.

**Fix:** Add config option for cascade mode: `all` (try all), `first-match` (current), `required-confidence` (each layer must meet threshold).

#### Issue 7: Layer 2 (Semantic) Uses Different Embedding
The semantic router uses `HomeClawEmbeddingEncoder` which calls `Util().embedding()`. This is the same embedding model, but the encoder wraps it with sync/async handling that could have race conditions.

**Fix:** Review the ThreadPoolExecutor usage in `__call__` - `asyncio.run` in a thread pool could create new event loops unexpectedly.

---

## 4. Companion App Analysis

**Files:** `clients/HomeClawApp/lib/core_service.dart`, etc.

### Current Implementation
- Flutter with Material Design 3
- **CoreService** singleton manages all API connections
- WebSocket for real-time messaging
- REST API for friends, chat history, skills, etc.
- Hive for local chat history storage
- SharedPreferences for settings
- Support for multi-instance (multiple HomeClaw Cores)
- Federation with E2E encryption (X25519 + AES-256-GCM)
- Dev Bridge for Cursor/Claude Code/Trae integration
- Claw-Code sessions
- Skills marketplace via ClawHub
- Native plugin for notifications, camera, screen recording

### Strengths
1. **Comprehensive feature set** - Chat, federation, skills, admin UI
2. **Offline-first** - Local Hive storage for chat history
3. **Multi-instance** - Can connect to multiple HomeClaw Cores
4. **E2E encryption** - X25519 key exchange + AES-256-GCM for federated messages
5. **Rich media support** - Images, audio, voice messages
6. **Dev Bridge** - IDE integration for project browsing
7. **Push notifications** - Via Firebase Cloud Messaging

### Issues & Improvements

#### Issue 1: No State Management Library
Uses raw `StatefulWidget` + `StreamSubscription`. This becomes hard to maintain at 2000+ line ChatScreen.

**Fix:** Consider using Provider, Riverpod, or BLoC for state management. At minimum, extract ChatScreen into smaller widgets.

#### Issue 2: CoreService is a God Class
`CoreService` handles: WebSocket, REST API, authentication, settings, push notifications, federation, encryption, etc. (~2400+ lines).

**Fix:** Split into multiple services: `ApiService`, `WebSocketService`, `AuthService`, `FederationService`, `SettingsService`.

#### Issue 3: Chat Screen is 2000+ Lines
`chat_screen.dart` is massive and handles many concerns.

**Fix:** Extract into smaller widgets: `MessageBubble`, `QuickActions`, `VoiceInput`, `AttachmentPicker`, `AITypingIndicator`.

#### Issue 4: Error Handling is Inconsistent
Some API calls show user-friendly errors, others silently fail.

**Fix:** Create a centralized error handling approach with consistent user-facing messages.

#### Issue 5: No Unit Tests
The app has no tests in the repo.

**Fix:** Add widget tests and service tests. At minimum, test CoreService API calls with mock responses.

#### Issue 6: WebSocket Reconnection Logic
If WebSocket disconnects, reconnection logic may not handle all edge cases (network changes, long idle periods).

**Fix:** Add exponential backoff with jitter, and consider a心跳 ping/pong check.

#### Issue 7: QR Code Connection Has No Validation
The `homeclaw://connect?url=...&api_key=...` URL scheme doesn't validate the URL format before attempting connection.

**Fix:** Add URL format validation before attempting to connect.

#### Issue 8: Skills Search Could Be Improved
Searching ClawHub marketplace seems basic.

**Fix:** Add filters (category, rating, install count), sorting options, and search history.

#### Issue 9: No Dark Mode Toggle
The app doesn't have an explicit dark mode setting (follows system by default).

**Fix:** Add explicit dark/light/system mode toggle in settings.

#### Issue 10: Push Notification Deep Links
When tapping a push notification, the app routes to chat. But if the app is already open, the behavior may be inconsistent.

**Fix:** Test and document the deep link behavior for all notification types.

---

## 5. Cross-Cutting Concerns

### Issue: Intent Router and Skill Router Are Independent ~~(DONE)~~
These two routers didn't share context. If intent router routed to `weather`, the skill router might not load the weather skill if semantic similarity was below threshold. The `get_skills_filter_for_category` was used only to FILTER results, not to AUGMENT them.

**Fix:** Phase 3.1 category filtering now does TWO passes: (1) keep only skills whose folder is in the category allowlist, (2) add missing allowed skills directly from the catalog. This ensures that when intent router selects a category (e.g. "weather"), those skills are included even if semantic search gave them low similarity scores.

### Issue: Hybrid Router Metrics Are In-Memory Only
`hybrid_router/metrics.py` uses module-level dictionaries. Stats are lost on restart.

**Fix:** Persist metrics to database for long-term analysis.

### Issue: No A/B Testing Infrastructure
There's no way to test routing changes with a subset of users.

**Fix:** Add experiment ID to routing decisions for canary testing.

---

## 6. Recommended Priority Order

### High Priority
1. ~~**Intent Router:** Fix duplicate weather check (Issue 1)~~ - DONE
2. **Skill Router:** Fix double-load issue (Issue 1) - Low impact; existing safeguards mitigate
3. ~~**Companion App:** Split CoreService~~ - DONE (widget extraction phase)
4. ~~**Companion App:** Extract ChatScreen widgets~~ - DONE (widget extraction phase)

### Medium Priority
5. ~~**Hybrid Router:** Fix semantic cache key (Issue 3)~~ - DONE (mtime-based invalidation)
6. ~~**Hybrid Router:** Heuristic substring matching (Issue 1)~~ - DONE (word boundaries for single-word ASCII keywords)
7. ~~**Intent Router:** Add pattern validation (Issue 3)~~ - DONE (regex validation at load time already implemented)
8. ~~**Skill Router:** Add weighted scoring (Issue 2)~~ - DONE (union_trigger_baseline_score already implemented at skill_router.py:312)
9. ~~**Intent/Skill Router integration**~~ - DONE (Phase 3.1 now augments category skills, not just filters)
10. **Companion App:** Add state management (Issue 1) - High complexity; breaking changes

### Low Priority
11. ~~**Hybrid Router:** Make perplexity threshold configurable (Issue 5)~~ - DONE (already configurable)
12. **Hybrid Router:** Add cascade customization (Issue 6) - Significant restructuring; current first-match cascade is simple and effective
13. ~~**Intent Router:** Cache semantic results (Issue 5)~~ - DONE (not needed; semantic/hybrid modes are mutually exclusive branches, each calls _route_semantic_intent at most once per request)
14. **Companion App:** Add unit tests (Issue 5) - Manual testing during companion app development
15. ~~**Hybrid Router:** SLM URL construction (Issue 4)~~ - Low impact; current 3-tier fallback chain is reasonable

---

## 7. Files to Modify

| Component | File | Priority |
|-----------|------|----------|
| Intent Router | `base/intent_router.py` | High |
| Skill Router | `base/skill_router.py` | High |
| Hybrid Router | `hybrid_router/heuristic.py` | Medium |
| Hybrid Router | `hybrid_router/semantic.py` | Medium |
| Companion App | `lib/core_service.dart` | High |
| Companion App | `lib/screens/chat_screen.dart` | High |
| Companion App | `lib/core_service.dart` | Medium |
