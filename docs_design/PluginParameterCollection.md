# Plugin Parameter Collection: Preset Config vs Multi-Round Dialogue

This document discusses how to handle plugin parameters that may be **missing**, **incorrect** (from profile/memory), or need **confirmation** — focusing on scenarios like "buy something for me" where the plugin requires address, phone, contact name, payment info, etc.

---

## 1. Problem Statement

**Scenario:** User says "Buy me some milk." A "buy" plugin needs:

- `address` (delivery)
- `phone` (contact)
- `contact_name` (recipient)
- `item` (from user message: "milk")
- Optionally: `payment_method`, etc.

**Challenges:**

1. **Missing info** — Profile or memory may not have address/phone. The plugin cannot run without them.
2. **Incorrect info** — Profile may have outdated address ("123 Old St") or wrong phone. Using it blindly causes failed orders.
3. **Uncertain correctness** — When we have a value (from profile, config, or memory) but **cannot confirm it is correct**, we should **confirm with the user** before using it. Never assume; if uncertain, ask.

**Two main approaches:**

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **A. Preset config** | Plugin has `config.yml` with default/required values (address, phone, contact). Same or per-user. | Simple, works offline, no multi-turn. | Static; not suitable for dynamic or per-request data. |
| **B. Multi-round dialogue** | LLM gathers params from profile, memory, user message; if missing, asks user; validates before invoking plugin. | Handles dynamic cases; user can correct. | More complex; needs validation and "ask user" flow. |

**Recommendation:** Support **both**. Preset config for simple cases (single user, fixed address). Multi-round for dynamic cases (multiple users, changing addresses, confirmation needed).

---

## 2. Current State

- **route_to_plugin** accepts `plugin_id`, optional `capability_id`, optional `parameters` (dict).
- The LLM infers parameters from user message + system prompt (profile, RAG memory, chat history).
- **No validation** before plugin invocation. If the LLM omits required params, the plugin receives incomplete data and may fail or use wrong defaults.
- **Profile** exists (`profile_get` tool, `## About the user` in prompt). LLM can use it but has no structured "fill params from profile" step.
- **Capability schema** in `plugin.yaml` defines parameters (name, type, required). Today this schema is **not** used to validate or auto-fill before calling the plugin.

---

## 3. Design: Combined Approach

### 3.1 Parameter Resolution Order and Correctness

**Principle:** If we cannot confirm whether a parameter is correct, we must confirm with the user. Do not use uncertain values blindly.

Before invoking a plugin, Core resolves each parameter in this order:

1. **Explicit (user-provided this turn)** — Value passed by the LLM from the **current** user message. Highest confidence; no confirmation needed.
2. **Profile** — If param has `profile_key` and value not in (1), use `profile[profile_key]`. **Uncertain** unless user just said it or we have explicit confirmation — treat as needing confirmation if `confirm_if_uncertain` or param is sensitive.
3. **Config** — If param has `config_key` or plugin has `default_parameters`, use that. **Uncertain** (static preset; may be stale).
4. **Missing** — If required and still no value → do **not** invoke; return "ask user" message.
5. **Uncertain** — If we have a value from (2) or (3) but the parameter is marked `confirm_if_uncertain: true` (or similar), treat as "needs confirmation" → do **not** invoke; return "confirm with user" message listing the uncertain params and their values.

### 3.2 Plugin Manifest Extensions (plugin.yaml)

```yaml
id: buy
name: Buy Plugin
description: Place orders for delivery. Use when the user wants to buy something.
type: inline
capabilities:
  - id: place_order
    name: Place order
    description: Place a delivery order.
    parameters:
      - name: item
        type: string
        required: true
        description: Item to buy (e.g. milk, bread).
        # No profile_key/config_key: must come from user message or LLM inference
      - name: address
        type: string
        required: true
        profile_key: address
        config_key: default_address
        confirm_if_uncertain: true   # When from profile/config, confirm with user before using
        description: Delivery address.
      - name: phone
        type: string
        required: true
        profile_key: phone
        confirm_if_uncertain: true
        description: Contact phone number.
      - name: contact_name
        type: string
        required: true
        profile_key: name         # Profile "name" maps to contact_name
        description: Recipient name.
      - name: payment_method
        type: string
        required: false
        profile_key: default_payment
        config_key: payment_method
        description: Payment method (e.g. card, cash).
```

### 3.3 Plugin Config (config.yml) — Preset Fallbacks

```yaml
id: buy
description: Place delivery orders.

# Optional: default values for parameters (used when not in profile or LLM args)
default_parameters:
  address: "123 Main St, City"
  contact_name: "John"
  payment_method: "card"

# Or per-capability:
capabilities:
  place_order:
    default_parameters:
      address: "123 Main St"
```

Preset config is useful when:

- Single primary user with fixed address
- Shared household config
- Quick setup without profile learning

**Use defaults directly (no confirmation):** When you trust the preset values, add:

```yaml
# Option A: Use all default_parameters directly without asking or confirming
use_defaults_directly: true

# Option B (recommended): Per-parameter allowlist — only these are used directly when filled from config
use_default_directly_for: [address, phone, contact_name]
```

- **Option A** `use_defaults_directly: true` — All params filled from `default_parameters` are used directly; skip confirmation.
- **Option B** `use_default_directly_for: [address, phone]` — Only the listed params, when filled from config, are used directly. Others still follow `confirm_if_uncertain`. **Recommended:** explicit control over which params use config directly.
- If neither is set: values from config are treated as uncertain when `confirm_if_uncertain` is true; we ask the user.

### 3.4 Registration: When Using use_default_directly_for (Option B)

When using **Option B** (`use_default_directly_for`), the listed parameters have trusted defaults in config. The registration logic for them:

**Do not pass default values to Core. Skip those params in the schema exposed to the LLM.**

| What | Behavior |
|------|----------|
| **Registration payload** | Include capability parameters (name, type, required, profile_key, config_key, confirm_if_uncertain). Do not include `default_parameters` values. Params in `use_default_directly_for` are registered (schema only); their values stay in config. |
| **Schema exposed to LLM** | Params in `use_default_directly_for` that have a value in config can be omitted from the parameters list — the executor fills them from config. The LLM only sees params the user must provide (e.g. item). |
| **Executor** | Reads config at runtime; merges `default_parameters` for params in `use_default_directly_for`; uses them directly without confirmation. |

**Why Option B:** Explicit per-parameter control; only the params you list use config directly. Sensitive values stay in config, not in Core. Config changes take effect without re-registration.

### 3.5 route_to_plugin Executor: Validation and "Ask User" Flow

**Before invoking the plugin:**

1. **Resolve params**: Merge (LLM args → profile [by profile_key] → config [by config_key]).
2. **Validate completeness**: For each required parameter, check that the resolved value is non-empty.
3. **Validate certainty**: For params with `confirm_if_uncertain: true`, if the value came from profile or config (not from the current user message), check config: if `use_defaults_directly: true` or param is in `use_default_directly_for`, treat as certain (use directly). Otherwise treat as uncertain → do **not** invoke; require confirmation.
4. **If all required params present and certain (or not marked confirm_if_uncertain)** → invoke plugin, return result (or ROUTING_RESPONSE_ALREADY_SENT).
5. **If any required param missing** → do **not** invoke. Return a structured message for the LLM:

   ```
   Plugin "buy" (place_order) requires parameters that are missing:
   - address (not in message, profile, or config)
   - phone (not in message or profile)
   
   Parameters we have:
   - item: milk (from user message)
   - contact_name: John (from profile)
   
   Please ask the user for: delivery address, phone number.
   ```

6. **If any param uncertain (from profile/config, confirm_if_uncertain)** → do **not** invoke. Return:
   ```
   Plugin "buy" (place_order) has parameters that need confirmation before use:
   - address: "123 Main St" (from profile) — please confirm with the user
   - phone: "555-0000" (from config) — please confirm with the user

   Parameters we have (no confirmation needed):
   - item: milk (from user message)
   - contact_name: John (from user message)

   Please ask the user: "I have your address as 123 Main St and phone as 555-0000. Is that correct for this order?"
   ```

8. The LLM receives this as a **tool result** (not ROUTING_RESPONSE_ALREADY_SENT). The tool loop continues; the LLM will produce a **text response** asking the user for the missing info (or confirmation). That response is sent to the user.
9. **Next user message**: User provides the missing values or confirms. The LLM (with full chat context) calls `route_to_plugin` again with complete, confirmed params.

**Key point:** The existing tool loop already supports this. We only need the executor to validate and return a descriptive "ask user" message instead of invoking the plugin when params are incomplete.

### 3.6 Implementation: Ask user and retry on next turn

Core implements a **pending plugin call** flow so the app can ask for missing parameters and retry without relying on the LLM to call the tool again:

1. **Resolver** (`base/plugin_param_resolver.py`) returns a third value `ask_user_data` when params are missing or uncertain: `{"missing": ["node_id"]}` or `{"uncertain": [...]}`.
2. **route_to_plugin** (`tools/builtin.py`): When validation returns `ask_user_data` with `missing`, Core builds a **user-friendly question** (e.g. "Which node should I use? (e.g. test-node-1)"), stores a **pending plugin call** per session (`plugin_id`, `capability_id`, `params` so far, `missing`), and returns that question as the assistant reply. The user sees the question instead of a raw error.
3. **Pending storage** (`core/core.py`): `get_pending_plugin_call(app_id, user_id, session_id)` / `set_pending_plugin_call` / `clear_pending_plugin_call` keyed by session so the next message in the same session can retry.
4. **Next turn** (`answer_from_memory`): At the start of handling a user message, Core checks for a pending plugin call. If there is one and the user's message looks like a value for the **single** missing parameter (e.g. "test-node-1"), Core merges it into params, clears pending, **invokes the plugin** with the merged params, and returns the plugin result. No extra LLM call is required for the retry.

This makes the app robust: when the LLM omits a required param (e.g. `node_id` for "record a video"), the user gets a clear question and can reply with the value; Core then completes the action. Plugins can also return a structured "ask user" response (e.g. `ask_user: true`, `missing_parameters: ["node_id"]`); Core can be extended to handle that the same way (store pending and show the message).

---

## 4. Confirmation Flow: When Uncertain, Confirm with User

**Rule:** If we cannot confirm whether a parameter is correct, we must confirm with the user. Do not use uncertain values to invoke the plugin.

**When is a value uncertain?** When it comes from profile or config, and the user has not explicitly provided or confirmed it in the current conversation. The user may have moved, changed their phone, or the config may be stale.

**Parameter attribute `confirm_if_uncertain`:** Mark parameters that should be confirmed when their value comes from profile or config:

```yaml
- name: address
  confirm_if_uncertain: true   # Always confirm when source is profile/config
- name: payment_method
  confirm_if_uncertain: true
```

**Executor behavior:** When a param has `confirm_if_uncertain: true` and its value was filled from profile or config (not from the current user message), do **not** invoke the plugin. Return a "confirm with user" message listing those params and their values. The LLM then asks the user to confirm; once the user confirms (or provides corrected values), the next `route_to_plugin` call can proceed.

---

## 5. Profile Key Mapping and Memory

**Profile keys** (from UserProfileDesign.md): `name`, `address`, `phone`, `birthday`, `families`, etc. Plugins declare `profile_key` to map their parameter names to profile keys.

**Memory (RAG):** The LLM already has RAG context. If the user said "my address is 456 New Rd" in a past conversation, that might be in RAG. The LLM can infer and pass it. We don't need a special "memory_key" in the schema — the main prompt already includes RAG. The executor only auto-fills from **profile** (and config); the LLM handles memory via normal reasoning.

**When profile is wrong:** The user can correct ("actually my new address is …"). That goes to chat. On the next `profile_update` (or explicit "remember"), the profile is updated. The executor doesn't "verify" correctness; it only fills missing values. **Correctness is ensured by the confirmation rule:** when we cannot confirm a value is correct, we ask the user.

---

## 6. Implementation Outline

### 6.1 Manifest Schema (plugin.yaml)

- Add optional `profile_key` and `config_key` to each parameter in capabilities.
- Add optional `confirm_if_uncertain: true` — when value comes from profile/config, require user confirmation before invoking.
- Add optional `default_parameters` (or per-capability) in config.yml.

### 6.2 route_to_plugin Executor

1. Resolve parameters: LLM args → profile (by profile_key) → config (by config_key). Track **source** per param (user_message | profile | config).
2. Validate required parameters are non-empty.
3. For params with `confirm_if_uncertain: true`: if source is profile or config, do **not** invoke; return "confirm with user" message.
4. If invalid/missing: return descriptive "ask user" string. Do not invoke plugin.
5. If all valid and certain: invoke plugin; post-process and send response.

### 6.3 Profile Access in Executor

The executor has `ToolContext` with `request` and `system_user_id`. Use `profile_store.get_profile(system_user_id)` to read profile. Merge by `profile_key` into params before validation.

### 6.4 Config Access

For inline plugins, `plugin.config` is loaded from `config.yml`. For external plugins, the descriptor may include config. Executor reads `default_parameters` and `use_defaults_directly` / `use_default_directly_for` from plugin config at runtime and merges. Default values are **not** passed to Core during registration; they stay in config only.

---

## 7. Example Flows

### Flow 1: Preset Config (Simple) — use_defaults_directly

- Config: `default_parameters: { address: "123 Main St", contact_name: "John", phone: "555-0000" }` and `use_defaults_directly: true`
- User: "Buy milk"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk"})`
- Executor: Resolves address, contact_name, phone from config. `use_defaults_directly` is true, so no confirmation. All required present. Invokes plugin.
- Plugin runs, returns "Order placed for milk."

### Flow 2: Profile + One Missing (Multi-Round)

- Profile: `{ name: "John", address: "123 Main St" }` (no phone)
- User: "Buy milk"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk"})`
- Executor: Resolves item, address, contact_name from args + profile. Phone missing. Returns:
  - "Plugin buy (place_order) needs: phone. Have: item=milk, address=123 Main St, contact_name=John. Ask user for phone number."
- LLM generates: "I can place that order for milk. What's your phone number for the delivery?"
- User: "555-1234"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk", phone: "555-1234"})`
- Executor: Item and phone from user message (certain). Address, contact_name from profile — if `confirm_if_uncertain` on those, executor would return "confirm" message. Assume address/contact_name not marked for confirmation here. Invokes plugin. Done.

### Flow 2b: Profile Values Need Confirmation (Uncertain)

- Profile: `{ address: "123 Main St", phone: "555-0000", name: "John" }`; address/phone have `confirm_if_uncertain: true`
- User: "Buy milk"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk"})`
- Executor: All required params resolvable (from profile), but address and phone are uncertain. Returns:
  - "Plugin buy (place_order) needs confirmation: address='123 Main St' (from profile), phone='555-0000' (from profile). Please confirm with the user before placing the order."
- LLM generates: "I'd like to place that order for milk. I have your address as 123 Main St and phone as 555-0000. Is that correct?"
- User: "Yes" or "Actually use 456 Oak Ave, 555-1234"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk", address: "456 Oak Ave", phone: "555-1234", contact_name: "John"})` (user confirmed or corrected)
- Executor: Params from user message (certain). Invokes plugin. Done.

### Flow 3: All Missing (Multi-Round)

- No profile, no config.
- User: "Buy milk"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk"})`
- Executor: Missing address, phone, contact_name. Returns ask-user message.
- LLM: "To deliver the milk, I need your address, phone number, and name. Could you provide those?"
- User: "123 Oak Ave, 555-1234, I'm John"
- LLM: `route_to_plugin(plugin_id=buy, parameters={item: "milk", address: "123 Oak Ave", phone: "555-1234", contact_name: "John"})`
- Executor: All present. Invoke. Done.

---

## 8. Summary

| Aspect | Design |
|--------|--------|
| **Preset config** | `config.yml` can define `default_parameters` per plugin or per capability. Executor merges these when param is missing from LLM args and profile. |
| **Profile mapping** | Each parameter can have `profile_key` (e.g. `profile_key: address`). Executor fills from `profile[profile_key]` when not in args. |
| **Validation** | Before invoking, executor validates required params. If any missing, return descriptive "ask user" message instead of invoking. |
| **Multi-round** | LLM receives the "ask user" message as tool result, generates natural question, sends to user. Next turn, LLM calls route_to_plugin again with full params. No new tools or stateful flows. |
| **Confirmation** | **Rule:** If we cannot confirm a parameter is correct, we confirm with the user. Add `confirm_if_uncertain: true` to params; when value comes from profile/config, executor returns "confirm with user" message — unless `use_defaults_directly` (or `use_default_directly_for`) in config says to use them directly. |
| **use_defaults_directly** | In config.yml: `use_defaults_directly: true` or `use_default_directly_for: [address, phone]`. When set, params filled from config are used directly without asking the user. |
| **Registration (Option B)** | When using `use_default_directly_for`: do not pass default values to Core. Registration = capability schema only. Default values stay in config.yml; executor reads at runtime. Params in `use_default_directly_for` can be omitted from the LLM-facing parameter list. |

This design supports both preset config (simple, static) and multi-round dialogue (dynamic, user-provided) within the existing tool loop and plugin architecture.
