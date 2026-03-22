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
| **`capabilities`** | No | Tags for routing, e.g. `[Chat]`, `[embedding]`, `[Math]`. Used with **`sessions_spawn`** + **`capability`**. |
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

## 5. Using capabilities from chat (spawn)

- The agent can call **`models_list`** to see refs, **capabilities**, and **`available`**.
- **`sessions_spawn`** with **`capability: Chat`** (for example) picks a model that lists that capability ( **`available` must not be false** ); **`main_llm`** is preferred if it shares the same tag.
- To force a specific weights file, pass **`llm_name`**: `local_models/<id>`.

---

## 6. Pitfalls

- **Duplicate `port`** on two local entries you run together → one server will fail to bind; give each concurrent model its own port.
- **`main_llm`** / **`embedding_llm`** pointing at a missing **`path`** → startup or **doctor** / first request errors for that role.
- **Ollama rows**: **`type: ollama`**; Core does not start the daemon—you run Ollama separately.

---

## See also

- [Models](models.md) — cloud vs local, multimodal, examples  
- [Model selection & lifecycle](model-selection-and-lifecycle.md) — when main vs embedding vs vision vs spawn run  
- [Core config](core-config.md) — **`llm_config_file`**, **`main_llm`**, **`embedding_llm`**  
- Repo: **`config/llm.yml`** §2–3 header comments (full field notes)
