# How to use the LLM catalog (`llm.yml`)

HomeClaw lists **local** and **cloud** models in **`config/llm.yml`** (merged when **`core.yml`** sets **`llm_config_file: llm.yml`**). That list is your **catalog**: every row is a named ref you can point **`main_llm`**, **`embedding_llm`**, **`vision_llm`**, mix-mode legs, or **`sessions_spawn`** at.

---

## 1. The two kinds of refs

| Prefix | Example | Meaning |
|--------|---------|--------|
| **`local_models/<id>`** | `local_models/main_vl_model_4B` | GGUF (or **`type: ollama`**) on a **host:port** you set per entry. |
| **`cloud_models/<id>`** | `cloud_models/Gemini-2.5-Flash` | LiteLLM / provider model on that entry’s **host:port**. |

The **`id`** is the slug after the prefix; it must be **unique** within `local_models` or `cloud_models`.

---

## 2. What to put in each local row

| Field | Required | Notes |
|--------|----------|--------|
| **`id`** | Yes | Stable name; ref = `local_models/<id>`. |
| **`path`** | Yes (llama.cpp) | GGUF path **relative to `model_path`**, or Ollama model name if **`type: ollama`**. |
| **`host`**, **`port`** | Yes | **One unique port** per llama-server you might run **at the same time**. |
| **`capabilities`** | No | Coarse tags for routing, e.g. `[Chat]`, `[embedding]`, `[Math]`. Used with **`sessions_spawn`** + **`capability`** only (tags, not prose). |
| **`description`** | No | Short prose: strengths, size, latency, best use cases. Returned in **`models_list`** and, when **`tools.llm_catalog_inject_enabled`** is true (default), **appended to the `models_list` and `sessions_spawn` tool descriptions** in the main prompt so the model sees every ref’s capabilities + description without an extra tool call. Automatic embedding-based routing is **not** implemented yet. |
| **`alias`** | No | Display name in logs / **`models_list`**. |
| **`available`** | No | Default **`true`**. Set **`false`** if the row is a **placeholder** (no GGUF yet): still valid if you set **`main_llm`** explicitly later; **skipped** for automatic capability picking. |
| **`mmproj`**, **`supported_media`** | No | Vision models: mmproj + e.g. `[image]`. |

---

## 3. Typical workflow

1. **Add or edit rows** under **`local_models:`** and **`cloud_models:`** in **`llm.yml`** (one row per model you care about).
2. **Put GGUF files** under your **`model_path`** (often **`models/`**) to match each **`path`** when that model should actually run.
3. **Point active roles** in **`core.yml`** (or merged LLM block), for example:
   - **`main_llm`**: `local_models/your_chat_id` or `cloud_models/your_cloud_id`
   - **`embedding_llm`**: usually `local_models/...` with **`capabilities: [embedding]`** or a cloud embedding id
   - **`vision_llm`**: if main is not vision-capable
   - Mix mode: **`main_llm_local`**, **`main_llm_cloud`**, plus hybrid router / classifier **`model`** ref if enabled
4. **Restart Core** (or reload config the way you usually do) after changing **`main_llm`** / **`embedding_llm`**.
5. **Check health**: `python -m main doctor` — confirms **main** and **embedding** reachability, not every catalog row.

You do **not** need every catalog row to have a file on disk **until** you assign that ref to a running role or call it via **`sessions_spawn`**.

---

## 4. Placeholders (`available: false`)

Use when the row documents a model you will add later:

```yaml
- id: my_future_7b
  alias: Future 7B
  path: SomeModel-Q4_K_M.gguf
  host: 127.0.0.1
  port: 5040
  capabilities: [Chat]
  available: false
```

- **`models_list`** still shows the row with **`available: false`**.
- **`get_llm_ref_by_capability` / spawn by `capability` only** will **not** pick this row.
- **`sessions_spawn`** with explicit **`llm_name: local_models/my_future_7b`** can still be tried (may fail until the file exists).

When the GGUF is installed, remove **`available: false`** or set **`available: true`**.

---

## 5. Selecting a model by **capability** — what triggers it, how it works

### 5.1 What Core does **not** do

- **Normal chat** (every user message) always uses the configured **`main_llm`** (and mix-mode routing when enabled). Core **does not** scan `capabilities` on each message to switch the main model.
- **Embedding / RAG** uses **`embedding_llm`**, not the capability list.
- There is **no** background job that “loads a model because a capability matched” by itself.

Capability tags matter when **something in the stack explicitly asks for a capability** — today that path is the **`sessions_spawn`** tool (and **`models_list`** only *lists* tags for the agent).

### 5.2 What **does** trigger capability selection

1. The **main agent** (with tools on) decides to call **`sessions_spawn`**.
2. The tool call includes **`capability`** (e.g. `"Chat"`, `"Math"`) and **omits** **`llm_name`** (if **`llm_name`** is set, capability is ignored for resolution).

Then Core runs **`get_llm_ref_by_capability(capability)`** and passes the resulting ref into **`run_spawn`** (`base/util.py`).

### 5.3 Resolution order (same as code today)

Matching is **case-insensitive** on capability strings. Rows with **`available: false`** are **skipped**.

1. If **`main_llm`** resolves to an entry that lists the capability → use **`main_llm`** (so the “default brain” wins when it already has that tag).
2. Else scan **`local_models`** in YAML order → first **available** row whose **`capabilities`** contains the tag → ref `local_models/<id>`.
3. Else scan **`cloud_models`** the same way → `cloud_models/<id>`.
4. If nothing matches → **`sessions_spawn`** returns an error (“No model found with capability …”); use **`models_list`** to see **`model_details.capabilities`**.

There is **no** `priority` field in the resolver yet (planned in [LocalModelLoadPolicy…](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/LocalModelLoadPolicyAndCapabilityRouting.md)); ties after main are “first in list.”

### 5.4 After a ref is chosen — what “load” means

Core does **not** implement “load arbitrary GGUF by capability” for every local ref.

- **`run_spawn`** issues **one** chat completion to that ref: `openai_chat_completion(messages, llm_name=…)`.
- **Cloud** models: HTTP to the configured LiteLLM/host; no local weight load.
- **Local** llama.cpp: traffic goes to that entry’s **`host:port`**. The **llama-server for that port must already be listening** (unless that ref is the same process Core already started for **main** / **classifier** / etc.). Core **does** start **main**, **embedding**, **classifier** (mix), and can start **vision** on demand — it does **not** auto-start every other **`local_models`** row on first spawn.
- **Ollama** rows: your Ollama daemon must be running.

So: capability selection picks **which configured endpoint to call**; **you** still ensure the right server is up for that ref (or use main / cloud for spawn targets you know are reachable).

### 5.5 Quick comparison

| Mechanism | Uses `capabilities`? | Loads weights? |
|-----------|----------------------|----------------|
| Default chat | No (uses **`main_llm`**) | Main server at Core startup (local) |
| **`sessions_spawn`** + **`llm_name`** | No | Target’s server must be up (or cloud) |
| **`sessions_spawn`** + **`capability`** | Yes (resolver above) | Same as row for resolved ref |
| **`models_list`** | Lists tags only | No |

---

## 6. Pitfalls

- **Duplicate `port`** on two local entries you run together → one server will fail to bind; give each concurrent model its own port.
- **`main_llm`** / **`embedding_llm`** pointing at a missing **`path`** → startup or **doctor** / first request errors for that role.
- **Ollama rows**: **`type: ollama`**; Core does not start the daemon—you run Ollama separately.
- **Spawn by capability** to a **secondary local** port → if Core never starts that server, start **llama-server** yourself on that port or spawn to **main** / **cloud** instead.

---

## 7. Natural language in chat → model selection, run, “release” (examples)

There is **no** separate HomeClaw service that regex-parses your sentences to pick a model. **Mapping is semantic:** the **main** LLM reads the user message (plus system prompt, tools list, and often **`models_list`** output) and decides whether to call **`sessions_spawn`**, answer directly, use other tools, etc. So phrasing matters for the **model’s** judgment, not a fixed keyword table in Core.

Below, “Assistant” means the same agent loop (main model + tools), not a second product.

### 7.1 How NL maps to selection (today)

| User intent (examples) | What usually happens | Model / load |
|------------------------|----------------------|--------------|
| General question, no special model ask | Reply in one turn with **`main_llm`** | Main already loaded at Core start (local) or cloud call |
| “Summarize in one short paragraph” (no other model named) | Still **main** unless the agent chooses **spawn** | Main |
| “Use a **smaller / faster** model for this subtask” / “offload to a sub-agent” | Agent may call **`sessions_spawn`** with **`capability: Chat`** or a specific **`llm_name`** after **`models_list`** | Resolved ref; **one** completion; see §5.4 for servers |
| “Use something good at **math** for this” | Agent may **`sessions_spawn`**, **`capability`** matching a tag you put in **`llm.yml`** (e.g. `Math`) | First matching **available** row after main (§5.3) |
| “Call **`local_models/…`** for this” (or paste ref from config) | Agent **`sessions_spawn`**, **`llm_name`** set to that ref | That endpoint must be reachable |
| User **sends an image** and main is not vision | Core may **start vision** llama-server on demand, run vision path, then **idle-stop** vision (config permitting) | Real **load → use → release** pattern for **vision** only today |
| “**Load** model X, answer, then **unload**” for an arbitrary GGUF | Not a built-in chat command yet; agent might explain limits or spawn once without unloading weights | **Planned** generic on-demand lifecycle — see [design doc](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/LocalModelLoadPolicyAndCapabilityRouting.md) |

### 7.2 Example dialogue A — subtask via capability (spawn)

**User:** “I don’t want to burn my big model on this. Use whatever we’ve tagged for quick chat and rewrite the following as bullet points: …”

**Assistant (typical tool path):**

1. Optionally **`models_list`** (if unsure of tags).
2. **`sessions_spawn`** with e.g. **`capability: Chat`** and **`task:`** “Rewrite as bullet points: …”.

**Core:** resolves capability → **`run_spawn`** → returns text to the tool → main model may wrap it for the user.

**“Release”:** No extra unload step; one HTTP completion ends. VRAM for a **secondary** local server stays loaded until **you** stop that server (unless that ref **is** main).

### 7.3 Example dialogue B — explicit ref after listing models

**User:** “From our catalog, use the 8B Qwen entry for this translation only: …”

**Assistant:**

1. **`models_list`** → finds e.g. `local_models/Qwen3-8B-Q5_K_M`.
2. **`sessions_spawn`** with **`llm_name: local_models/Qwen3-8B-Q5_K_M`**, **`task:`** translation text.

**Requirement:** **llama-server** (or Ollama) for that **host:port** must be running if it is not main.

### 7.4 Example dialogue C — no spawn (main only)

**User:** “What’s the capital of France?”

**Assistant:** Answers directly; **no** capability resolution; **`main_llm`** only.

### 7.5 Example D — image (vision on demand: load → use → release)

**User:** Sends a photo: “What’s in this image?”

**When** **`vision_llm`** is set and **`vision_llm_start_on_demand: true`** (typical):

1. Core ensures the **vision** llama-server is **started** if needed.
2. Image is analyzed via the vision model path.
3. Core **schedules stop** of the vision server after **`vision_llm_idle_stop_seconds`** (or immediate when that value is **0**), so VRAM can be **freed** for vision specifically.

That is the closest today’s Core comes to “chat triggered load, response, then release” **without** the user typing “load vision.”

### 7.6 Tips so NL actually triggers the right behavior

- Put **clear capability tags** on specialist rows in **`llm.yml`** (`Math`, `Chat`, …) and mention those words in the user request (the main model maps language → tool args).
- In **workspace / rules**, you can add: “When the user asks for a cheaper or secondary model, prefer **`sessions_spawn`** with **`capability: …`** or **`llm_name`** from **`models_list`**.”
- For **reliable** model choice, prefer **`llm_name`** over vague capability names if you have many Chat-tagged rows.

---

## 8. Companion friend + dedicated model (math / science)

Use **`llm_ref`** on a **friend preset** in **`config/friend_presets.yml`**, then add a friend in **`user.yml`** with **`preset: math`** (or your preset name). Chatting with that friend in the **Companion app** uses **`llm_ref`** for the whole turn (overrides mix local/cloud for that friend). Optional alias key: **`main_llm_ref`**. Use **`tools_preset: tutor`** for `time`, **`sessions_spawn`**, **`models_list`**, **`web_search`**. Uncomment the **`math`** / **`science`** examples at the bottom of **`friend_presets.yml`** and set **`llm_ref`** to a real **`llm.yml`** id. See **[Companion app](companion-app.md)** and **[Friends & Family](friends-and-family.md)**.

---

## See also

- [Models](models.md) — cloud vs local, multimodal, examples  
- [Model selection & lifecycle](model-selection-and-lifecycle.md) — when main vs embedding vs vision vs spawn run  
- [Core config](core-config.md) — **`llm_config_file`**, **`main_llm`**, **`embedding_llm`**  
- Repo: **`config/llm.yml`** §2–3 header comments (full field names)
