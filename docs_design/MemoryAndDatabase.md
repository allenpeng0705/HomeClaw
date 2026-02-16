# Memory and database configuration (core.yml)

Core uses a **relational database** (chat history, sessions, runs), a **vector database** (RAG memory), and an optional **graph database** (entities and relationships). **Cognee is always the default** for memory (and for the knowledge base when `knowledge_base.backend` is auto); the **in-house** backend (SQLite + Chroma + optional graph) remains supported—set `memory_backend: chroma` to use it. See **docs/MemoryUpgradePlan.md** and **docs/MemoryCogneeEvaluation.md** for the full memory upgrade story.

**Per-user sandbox:** Memory (RAG) and the knowledge base are **scoped by system user id** (from `config/user.yml`: each user’s `id` or `name`). Each user has their own memory and KB: add/search use that id, so data is isolated per user. See **docs/MultiUserSupport.md** for how system user id is resolved from channel identity.

**Cognee (default):** Configure via **Cognee’s `.env`** and/or the **`cognee:`** section in `core.yml`. We convert the `cognee:` section to Cognee env vars at runtime so you can keep everything in one file. `vectorDB` and `graphDB` in `core.yml` **do not** apply to Cognee.

---

## How the current vectorDB and graphDB settings work

- **`vectorDB:`** and **`graphDB:`** in `core.yml` are used **only when `memory_backend: chroma`** (in-house RAG). They are **not** used when `memory_backend: cognee`.
- When **Cognee** is selected, Cognee uses its own relational, vector, and graph stores; those are configured in **Cognee’s `.env`** (and Cognee extras), not in `core.yml`. So changing `vectorDB` or `graphDB` in `core.yml` has **no effect** on Cognee.
- **Why are supported types different?** Cognee and the in-house backend use **different config systems**: Cognee supports e.g. LanceDB, PGVector, Qdrant, Redis, FalkorDB, Neo4j, Neptune via its `.env` and `cognee[extra]`; the in-house backend supports Chroma, Qdrant, Milvus, Pinecone, Weaviate (vector) and Kuzu, Neo4j (graph) via `core.yml`. The option sets differ by design.

---

## Which config applies where

| memory_backend | Relational / vector / graph for **memory** | Where to configure |
|---------------|---------------------------------------------|--------------------|
| **cognee** (default) | Cognee’s own stores (SQLite+ChromaDB+Kuzu by default, or Postgres/other vector/Neo4j) | **`core.yml`** section **`cognee:`** (we convert to Cognee env at runtime) and/or **Cognee’s `.env`**. `core.yml` **vectorDB** and **graphDB** are **not** used for memory. |
| **chroma** | In-house: SQLite + Chroma (or Qdrant/etc.) + optional Kuzu/Neo4j | **`core.yml`**: `database:`, `vectorDB:`, `graphDB:` |

- **database:** in `core.yml` is always used for **Core’s** chat history, sessions, and runs (regardless of memory_backend). When `memory_backend: chroma`, the in-house memory also uses it for its history audit. When `memory_backend: cognee`, Cognee uses its own relational store (from `cognee:` or Cognee `.env`), not `core.yml` database.
- **vectorDB:** and **graphDB:** in `core.yml` are used **only** when `memory_backend: chroma`. For Cognee, use the **`cognee:`** section in `core.yml` and/or Cognee’s `.env` (see [docs.cognee.ai](https://docs.cognee.ai/)).

---

## How to configure Cognee

When `memory_backend: cognee`, **all** memory storage (relational, vector, graph) is controlled by **Cognee**. You can configure it in **one** of two ways (or both; `core.yml` values override `.env` for this process):

### Option A: `cognee:` section in `core.yml` (recommended)

Under **`cognee:`** in `config/core.yml` you can set relational, vector, graph, llm, and embedding. At runtime we convert these to Cognee env vars so Cognee picks them up. No separate `.env` needed unless you want to override or add vars.

| core.yml path | Cognee env var(s) |
|---------------|-------------------|
| `cognee.relational.provider` | `DB_PROVIDER` (sqlite \| postgres) |
| `cognee.relational.name` | `DB_NAME` |
| `cognee.relational.host` / `port` / `username` / `password` | `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD` (postgres) |
| `cognee.vector.provider` | `VECTOR_DB_PROVIDER` (chroma \| lancedb \| qdrant \| pgvector \| redis \| falkordb \| neptune_analytics) |
| `cognee.vector.url` / `port` / `key` | `VECTOR_DB_URL`, `VECTOR_DB_PORT`, `VECTOR_DB_KEY` |
| `cognee.graph.provider` | `GRAPH_DATABASE_PROVIDER` (kuzu \| kuzu-remote \| neo4j \| neptune \| neptune_analytics) |
| `cognee.graph.url` / `username` / `password` | `GRAPH_DATABASE_URL`, `GRAPH_DATABASE_USERNAME`, `GRAPH_DATABASE_PASSWORD` (neo4j) |
| `cognee.llm.provider` / `model` / `endpoint` / `api_key` | `LLM_PROVIDER`, `LLM_MODEL`, `LLM_ENDPOINT`, `LLM_API_KEY` |
| `cognee.embedding.provider` / `model` / `endpoint` / `api_key` | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_ENDPOINT`, `EMBEDDING_API_KEY` |
| `cognee.env` (key-value dict) | Any Cognee env var by name (passthrough) |

Leave a key empty or omit the `cognee:` section to rely on Cognee’s `.env` or defaults.

**LLM and embedding:** If you leave **`cognee.llm`** and **`cognee.embedding`** endpoint/model empty, we **auto-fill** them from Core’s **main_llm** and **embedding_llm** using the **same resolved host/port** as the chroma-based memory and Core (via `Util().main_llm()` and `Util().embedding_llm()`). The endpoint format is the **OpenAI-compatible base URL** `http://{host}:{port}/v1` (Cognee/LiteLLM then call `/chat/completions` and `/embeddings` on it), matching how we use `http://host:port/v1/chat/completions` and `http://host:port/v1/embeddings` elsewhere. So with default Cognee and empty llm/embedding, Cognee uses your existing LLM and embedding servers — no extra config needed.

### Option B: Cognee `.env` file

1. **In `core.yml`**: set `memory_backend: cognee` (and optionally `use_memory: true`). Do **not** expect `vectorDB` or `graphDB` in `core.yml` to affect Cognee.
2. **Create a `.env`** in your project root (or where Cognee is run) and set Cognee env vars there:
   - **LLM / embedding**: `LLM_*`, `EMBEDDING_*` (e.g. `LLM_PROVIDER`, `LLM_MODEL`, `LLM_ENDPOINT`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_ENDPOINT`). See [LLM Providers](https://docs.cognee.ai/setup-configuration/llm-providers), [Embedding Providers](https://docs.cognee.ai/setup-configuration/embedding-providers).
   - **Relational**: `DB_PROVIDER=sqlite` (default) or `DB_PROVIDER=postgres` + `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME`. See [Relational Databases](https://docs.cognee.ai/setup-configuration/relational-databases).
   - **Vector**: `VECTOR_DB_PROVIDER`, `VECTOR_DB_URL`, etc. See [Vector Stores](https://docs.cognee.ai/setup-configuration/vector-stores).
   - **Graph**: `GRAPH_DATABASE_PROVIDER`, `GRAPH_DATABASE_URL`, etc. See [Graph Stores](https://docs.cognee.ai/setup-configuration/graph-stores).
3. **Install Cognee**: `pip install cognee` (and optional extras such as `cognee[postgres]`, `cognee[chromadb]`, etc. if you use those backends).

Summary: **Cognee can be configured in `core.yml` under `cognee:` (we convert to env at runtime) and/or in Cognee’s `.env`.** Values set in `core.yml` cognee override `.env` for this process.

---

## What we support (detailed)

### memory_backend: cognee (default)

When `memory_backend: cognee`, the memory engine is **Cognee**. Cognee is configured via its own **`.env`** file (and optional Cognee config); see [docs.cognee.ai](https://docs.cognee.ai/) for full setup.

| Store       | Cognee default (easy install) | Cognee enterprise options |
|------------|--------------------------------|----------------------------|
| **Relational** | **SQLite** (file-based, no extra service) | **Postgres** — production, multi-process; set `DB_PROVIDER=postgres`, `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME`. Install: `pip install "cognee[postgres]"`. See [Relational Databases](https://docs.cognee.ai/setup-configuration/relational-databases). |
| **Vector**     | **ChromaDB** (local, default)           | **LanceDB**, **PGVector**, **Qdrant**, **Redis**, **FalkorDB**, **Neptune Analytics**. Configure via Cognee `.env` and extras (e.g. `pip install "cognee[qdrant]"`). See [Vector Stores](https://docs.cognee.ai/setup-configuration/vector-stores). |
| **Graph**      | **Kuzu** (file-based, no extra service)  | **Kuzu-remote**, **Neo4j**, **Neptune** / **Neptune Analytics**. Configure via Cognee `.env` and extras. See [Graph Stores](https://docs.cognee.ai/setup-configuration/graph-stores). |

- **Summary**: Cognee uses **SQLite + ChromaDB + Kuzu** by default (zero extra services). For scale, you can switch to **Postgres** (relational), **Qdrant / LanceDB / PGVector** (vector), and **Neo4j** (graph) by configuring Cognee’s `.env` and installing the corresponding Cognee extras.
- **Dataset scope**: Our adapter maps `(user_id, agent_id)` to a Cognee dataset name; add/search are scoped per dataset.

### memory_backend: chroma (in-house RAG)

When `memory_backend: chroma`, memory uses our **in-house** stack. All of the following are configured in **`config/core.yml`** (sections `database:`, `vectorDB:`, `graphDB:`).

| Store       | Default (easy install) | Enterprise options |
|------------|-------------------------|--------------------|
| **Relational** | **SQLite** (history audit; `database/` under data path) | **Postgres**, MySQL — set `database.backend` and `database.url` in `core.yml`. |
| **Vector**     | **Chroma** (local; `vectorDB.backend: chroma`)         | **Qdrant** (ready), Milvus, Pinecone, Weaviate (config present; adapters may be stubs). Configure under `vectorDB:` in `core.yml`. |
| **Graph**      | **Kuzu** (optional; file-based) or none                | **Neo4j** — set `graphDB.backend: neo4j` and Neo4j URL/credentials in `core.yml`. |

- **Summary**: In-house default is **SQLite + Chroma + optional Kuzu**. You can switch to Postgres/MySQL (relational), Qdrant (vector), and Neo4j (graph) via `core.yml` only; no Cognee involved.

---

## Relational database (chat history, sessions, runs)

Used by **Core** for chat history, sessions, and runs. When `memory_backend: chroma`, the in-house memory also uses this config for its history audit. When `memory_backend: cognee`, Cognee uses its own relational store (see Cognee `.env`).

**All relational DB actions use the same backend.** The single `database.backend` and `database.url` (or `MEMORY_DB_URI`) setting controls every table: chat history, sessions, runs, last-channel store, TAM cron jobs, and TAM one-shot reminders. So if you set `backend: postgresql` and a Postgres URL, all of these use Postgres; if you use `backend: sqlite` (default), all use SQLite.

Configure under `database:` in `core.yml`:

```yaml
database:
  backend: sqlite   # sqlite | mysql | postgresql
  url: ""           # empty = default (database/chats.db)
```

- **sqlite** (default): `url` can be empty; uses `database/chats.db` under the data path. Easiest for local/deploy.
- **mysql**: set `backend: mysql` and `url: "mysql+pymysql://user:password@host:3306/dbname"`. Requires `pip install pymysql`.
- **postgresql**: set `backend: postgresql` and `url: "postgresql+psycopg2://user:password@host:5432/dbname"`. Requires `pip install psycopg2-binary`.

You can also set the environment variable `MEMORY_DB_URI` to override the relational DB URL (any backend).

## Vector database (RAG memory)

Used only when **`memory_backend: chroma`**. When `memory_backend: cognee`, Cognee uses its own vector store (Chroma or other; see Cognee `.env`).

Configure under `vectorDB:` in `core.yml`:

```yaml
vectorDB:
  backend: chroma   # chroma | qdrant | milvus | pinecone | weaviate
  Chroma:
    # used when backend: chroma
    path: ""
    # ... (host, port, etc. for server mode)
  Qdrant:
    host: localhost
    port: 6333
    url: ""
    api_key: ""
  Milvus:
    host: localhost
    port: 19530
    uri: ""
  Pinecone:
    api_key: ""
    environment: ""
    index_name: memory
  Weaviate:
    url: http://localhost:8080
    api_key: ""
```

- **chroma** (default): Local persistent store; `path` empty uses the data path. No extra service needed.
- **qdrant**: Set `backend: qdrant` and configure `Qdrant` (url or host/port). Requires `pip install qdrant-client`. Implemented and ready to use.
- **milvus**, **pinecone**, **weaviate**: Config blocks are read; adapters are stubs. Set `backend` to `chroma` or `qdrant` until those backends are implemented (see `memory/vector_stores/*.py`).

## Memory backend (memory_backend)

**Cognee is always the default.** Both backends are supported. Configure under `memory_backend` in `core.yml`:

- **cognee** (default): Use Cognee as the memory engine (more stable and powerful). Requires `pip install cognee` and Cognee env (`.env` or `cognee:` in core.yml). Dataset scope: `(user_id, agent_id)` → dataset name. If the key is omitted, Cognee is used.
- **chroma**: In-house RAG: Chroma (vector) + SQLite (history) + optional graph (Kuzu or Neo4j). Entity/relation extraction on add; graph-aware search expansion. Set explicitly to use the in-house stack.

## Graph database (graphDB)

Configure under `graphDB:` in `core.yml` (used only when `memory_backend: chroma`):

- **backend**: `kuzu` (default, file-based) | `neo4j` (enterprise). Optional: `pip install kuzu` or `neo4j`.
- **Kuzu**: `path` — empty uses `database/graph_kuzu`.
- **Neo4j**: `url`, `username`, `password` — e.g. `bolt://localhost:7687`.

When graph is enabled, memories are enriched with entities/relationships and search can expand via 1-hop related memories.

## Summary

| Component       | Default (cognee) | Enterprise (cognee) | Default (chroma) | Enterprise (chroma) |
|----------------|------------------|---------------------|------------------|---------------------|
| **memory_backend** | cognee           | —                   | chroma           | —                   |
| **Relational** | SQLite           | Postgres (Cognee `.env`) | SQLite        | MySQL, PostgreSQL (`database:` in core.yml) |
| **Vector**     | ChromaDB         | Qdrant, LanceDB, PGVector (Cognee `.env` + extras) | Chroma | Qdrant (ready), Milvus/Pinecone/Weaviate (core.yml) |
| **Graph**      | Kuzu             | Neo4j (Cognee `.env`) | Kuzu (opt.)   | Neo4j (`graphDB:` in core.yml) |

- **Cognee**: Default stack is SQLite + ChromaDB + Kuzu. For enterprise, configure Postgres, vector DB, and Neo4j via Cognee’s `.env` and [docs.cognee.ai](https://docs.cognee.ai/).
- **Chroma (in-house)**: Default stack is SQLite + Chroma + optional Kuzu. For enterprise, configure `database:`, `vectorDB:`, and `graphDB:` in `core.yml`.

Changing backends is done by editing `core.yml` (in-house) or Cognee’s `.env` (Cognee); install the required driver or Cognee extra when needed.

---

## RAG vs document analysis: how the system finishes the task

When you ask to **analyze one document** or **ask a question based on one or more documents**, the system can finish the task in two different ways. Only one of them uses RAG by default.

### How document analysis / document Q&A works today (no RAG for document content)

- **Flow:** User says e.g. “Analyze report.pdf” or “Summarize these three files.”  
  Core builds the prompt with **RAG context** (relevant **conversation memories** from the vector DB) + chat history + your message, then calls the LLM **with tools**.
- The LLM can call **`document_read(path="report.pdf")`** (or **`file_read`**) in the **same turn**. The tool returns the document text into the conversation; the LLM then answers or summarizes from that content.
- **So:** The **document content is brought in by tools** in that turn. It is **not** retrieved from the vector database. We do **not** embed the document every time you reference it; we only **read it on demand** and use it in the current reply.

**Summary:** “Analyze this document” or “question based on these documents” is done by **tools** (`document_read` / `file_read`) in the same request. The memory system (RAG) is **not** used for the document body.

### When RAG (our memory system) is used

- **What gets embedded:** Only **user messages** (and optionally what the LLM decides to store) are put on the memory queue. `process_memory_queue` takes the **user text** and calls `mem_instance.add(...)`. So we embed **conversation content** (what the user said, and possibly selected assistant turns), **not** the contents of files you ask about.
- **When it’s used:** In **`answer_from_memory`**, Core calls **`_fetch_relevant_memories(query, ...)`** and injects those snippets into the system prompt. So RAG is used for **recalling past context** (facts, preferences, earlier conversation), not for fetching the text of a PDF or Word file you just asked about.

So we **can** reuse our memory system for **conversation memory**; document content is handled by **tools** in the same turn and is **not** automatically written into the memory/vector DB.

### If we stored documents in memory: embedding size and efficiency

If we **did** insert document content into the vector DB (e.g. “remember this document” or auto-embed after every `document_read`), we would have to control **embedding size and efficiency**:

| Concern | Approach |
|--------|----------|
| **Don’t embed whole documents** | **Chunk** documents (by paragraph or fixed token size). Store one embedding per chunk; search returns relevant chunks. |
| **Cap growth** | **Limit** chunks per document and/or per user (e.g. max N chunks per doc, max M docs per user). Evict or skip when over limit. |
| **Separate namespace** | Use a **separate collection** (or dataset/namespace) for “document memory” vs “conversation memory”. Then we can apply different policies (e.g. evict document chunks by TTL or LRU without touching conversation memory). |
| **TTL / eviction** | **Time-to-live** or **LRU eviction** for document chunks so old or rarely used document embeddings can be removed. |
| **No auto-embed on every read** | **Do not** auto-embed on every `document_read`. Only add to memory when the user explicitly asks to “remember this document” or when a dedicated “index this file” action is used. |

So: **today** we do not store document embeddings on every read, so embedding size is not blown up by documents. **If** we later add “remember this document,” we should chunk, cap, and use a separate collection (and optionally TTL/eviction) so the vector DB stays efficient and reusable for both conversation memory and optional document memory.

### Long documents: why the whole document in the prompt is a problem

When the document is **very long** (e.g. a 200‑page PDF or a large report), two things happen today:

1. **We truncate.** `document_read` (and `file_read`) use a **max_chars** limit (e.g. 64k from config). Everything beyond that is dropped, so the model never sees the rest. For huge documents, most of the content is lost.
2. **If we didn’t truncate**, we would put the **whole document** into the conversation (as the tool result). That causes:
   - **Context limit:** The model has a finite context window; a very long document can exceed it or leave little room for the answer.
   - **Useless information:** Most of the text is irrelevant to the user’s question. Putting it all in the prompt adds **noise**: the model may focus on the wrong parts, miss the actual answer, or give a worse reply. It also increases **cost** and **latency**.

So yes — **inserting the document as a whole into the system (or tool) prompt when it’s huge and full of irrelevant content is a real problem.** We should avoid it for long docs.

### How to handle very long documents: chunk and retrieve only what’s relevant

Instead of sending the whole document, we should send **only the parts that are relevant to the user’s question**. The standard approach is **RAG over the document** (chunk → embed → retrieve by query):

| Step | What to do |
|------|------------|
| **Chunk** | Split the document into smaller pieces (e.g. by section, paragraph, or fixed token size). |
| **Embed** | Optionally embed each chunk (or index by keyword). Chunks can be stored in a **temporary or session-scoped** index (or a dedicated “document” collection) so we don’t mix with conversation memory. |
| **Retrieve** | When the user asks a question, embed the **query** and run **similarity search** over the document’s chunks. Retrieve only the top‑k most relevant chunks. |
| **Prompt** | Put **only those retrieved chunks** into the prompt (or into a tool result). The model then sees mostly **useful** information, not the entire document. |

Effects:

- We **don’t** hit context limit with one huge blob.
- We **reduce noise**: the prompt contains mainly passages related to the question.
- We **can handle huge documents**: the full doc is chunked and indexed; the prompt only gets a small, relevant subset.

**Ways to implement:**

- **Option A – Tool `document_search(path, query)`:** The LLM calls this when the user asks about a long document. The tool (1) chunks the document (or uses a cached chunk index), (2) embeds the user’s query, (3) finds the most relevant chunks (e.g. via a temporary vector index or the same embedding model + in-memory similarity), (4) returns only those passages. The LLM then answers from this shortened context.
- **Option B – “Index this document” + RAG:** User says “I’m going to ask questions about report.pdf.” We chunk and index `report.pdf` into a **session- or document-scoped** vector store (separate from conversation memory). Later, when the user asks a question, we retrieve relevant chunks from that index and inject them into the prompt (or a tool result). Same idea as Option A but with an explicit “index” step and reuse across several questions.
- **Option C – Reuse existing memory with a dedicated document collection:** Same chunk + embed + retrieve flow, but store document chunks in a **separate collection** (or Cognee dataset) used only for “document memory,” with caps and TTL so it doesn’t grow forever (as in the table above). This is the **user knowledge base** approach: one dedicated collection (or dataset per user) for document chunks, separate from conversation memory.

In all cases, **long documents** are handled by **not** putting the whole file into the prompt; we **chunk** and **retrieve only relevant chunks**, so the system gets useful information without useless bulk and without blowing the context window.

### User knowledge base (Option C): when and how to delete knowledge / document embeddings and content

When you set up **one knowledge base per user** (Option C) with a dedicated collection, the knowledge base can **grow and grow**. You need clear rules for **when** to delete some knowledge and **how** to delete it (embeddings and content) so storage and search stay bounded and efficient.

#### A local knowledge base from multiple sources: documents, web search, and others

The knowledge base does not have to come only from **documents**. It can be a **single local knowledge base for the user** fed by:

| Source | How it gets in | Example |
|--------|----------------|---------|
| **Documents** | User indexes a file (PDF, Word, etc.); we chunk and embed it. | “Add report.pdf to my knowledge base.” |
| **Web search** | User asks a question; we run web search and optionally **save** the snippets or pages that were used to answer. Or user says “remember this search result.” | “Save what you found about X” or auto-save top results for “add to knowledge base” queries. |
| **Web pages (URLs)** | User provides a URL; we fetch the page, extract text, chunk and embed. | “Add this article to my knowledge base: https://…” |
| **Others** | Manual notes, pasted text, or other tools that produce text. | “Remember this: …” or a “save to knowledge base” action from chat. |

**Yes, it is possible to do this.** Use **one dedicated collection (or dataset) per user** for all such knowledge. Each chunk has:

- **Content** (the text)
- **Embedding** (vector for similarity search)
- **Metadata**: `user_id`, `source_type` (e.g. `document`, `web_search`, `url`, `manual`), `source_id` (e.g. file path, query + result URL, URL, note id), `added_at`, `last_used_timestamp`

**Retrieval** is the same regardless of source: embed the user’s question, run similarity search over the **whole** knowledge-base collection for that user, return top-k chunks. The model then sees a mix of document snippets, web snippets, and other saved content. **Eviction** (e.g. last-used timestamp + “unused for X days”) applies to **every** item in the knowledge base: documents, web-search-derived entries, URLs, and others. So one policy — “if not used for a long time, remove it” — keeps the entire local knowledge base bounded, no matter where the knowledge came from.

#### When to delete: eviction policies

| Policy | What it does | Pros | Cons |
|--------|----------------|------|------|
| **Cap (max size)** | Enforce a maximum: e.g. max chunks per user, max documents per user, or max total embeddings in the knowledge-base collection. When at or over the limit, **evict** something before (or when) adding new content. | Bounded size; predictable storage and latency. | Need a **tie-breaker** for what to evict (e.g. oldest, least recently used). |
| **TTL (time-to-live)** | Delete chunks (or whole documents) **older than X days** since they were added (or since last access). Run on a schedule (e.g. daily) or when adding. | Simple, automatic; “stale” knowledge drops out. | May remove something the user still cares about if they don’t touch it. |
| **LRU (least recently used)** | Track **last access time** per document (or per chunk). When over cap (or on a schedule), delete the **least recently used** documents/chunks first. | Keeps “active” knowledge; evicts unused first. | Requires storing and updating last_used; slightly more logic. |
| **Per-document eviction** | When over cap, evict **whole documents** (all chunks of a doc) rather than arbitrary chunks. Choose which document to drop by **oldest added** or **least recently used** document. | Clean: no orphan chunks; easier to explain (“this doc was removed”). | Coarse: one big doc counts as one unit; may evict a lot at once. |
| **User-controlled** | User explicitly says “remove this document from my knowledge base” or “clear my knowledge base.” Delete by **document_id** or delete **all** entries for that user in the knowledge-base collection. | Full control; no surprise deletions. | Knowledge base can still grow if user never cleans up. |
| **Hybrid** | Combine: e.g. **cap + LRU** (when over cap, evict least recently used documents until under cap), or **cap + TTL** (evict by age when over cap). Optional: **importance/usage** score (e.g. how often a doc was retrieved) to prefer keeping “useful” docs when evicting. | Flexible; can tune for “keep what’s used, drop the rest.” | More configuration and code. |

**Recommendation:** Start with a **cap per user** (e.g. max N documents or max M chunks) and **per-document eviction** using **LRU** (or oldest-added if you don’t track access). When the knowledge base is at cap and a new document is added, delete the **least recently used** (or oldest) **document** as a whole, then add the new one. Optionally add **TTL** so very old documents expire even if under cap. User-controlled “remove this doc” / “clear knowledge base” should always be supported.

#### How to delete: what to remove and how

| Aspect | What to do |
|--------|------------|
| **What to remove** | Remove **both** the **embedding** (vector store entry) and the **content** (text or payload stored with the chunk). If you store chunk text in the vector payload, deleting the vector row is enough. If you store content in a relational table or another store, delete those rows by the same **document_id** (or chunk_id) so you don’t leave orphan content or waste space. |
| **Scope** | Delete by **item/source id** (all chunks of one document, one web result, one URL, or one manual note — e.g. `metadata.source_id = X`), or by **user_id** (entire knowledge base for that user). Use metadata you set at index time (e.g. `user_id`, `source_id`, `source_type`, `added_at`, `last_used_at`) so the vector store (or Cognee) can target the right rows. Same logic for documents, web search, URLs, and other sources. |
| **When to run** | (1) **On add:** When adding a new document and over cap, run eviction first, then add. (2) **On schedule:** A background job (e.g. cron) runs TTL or LRU eviction periodically. (3) **On user action:** When user says “remove this document” or “clear knowledge base,” delete immediately by document_id or user_id. |

So: **decide when to delete** with a **cap + LRU (or TTL)** and optionally per-document eviction and user-controlled removal. **Decide how to delete** by removing **both embeddings and content** in the **same scope** (by document_id or user_id) and running that either **on add**, **on a schedule**, or **on user action**. That keeps the user knowledge base from growing without bound while keeping control and clarity.

#### Recommended: last-used timestamp + configurable “unused” period

A simple and effective strategy is: **record a `last_used_timestamp`** for each document (or each chunk), and **if it was not used for a long time (configurable), remove it from the system** — including **embedding**, **content**, and any other related data.

| Aspect | How to do it |
|--------|----------------|
| **Record `last_used_timestamp`** | Yes, it is possible and recommended. Store it per **document** (so all chunks of a doc share one last-used time) or per **chunk**. Store it in (1) **vector store metadata** (e.g. Chroma/Cognee allow metadata per vector row; add `last_used_at` or `last_used_timestamp`), or (2) a **relational table** keyed by `doc_id` (and optionally `chunk_id`) with a `last_used_at` column. |
| **When to update it** | **On use:** Every time the document (or chunk) is “used” — e.g. when it is **returned in a retrieval** for a user query — update `last_used_timestamp` to **now**. So: after running similarity search for the user’s question, for each chunk/doc that was retrieved, set `last_used_at = current time`. Optionally also update when the user explicitly “opens” or “views” the doc in the UI, if you have that. |
| **When to delete** | Use a **configurable** period, e.g. **“unused for X days”**. Config: e.g. `knowledge_base_unused_ttl_days` or `document_unused_ttl_days` (e.g. 30 or 90). **Delete** every document (and all its chunks) for which `last_used_timestamp < (now - X days)`. So: “if not used for 30 days, remove it.” |
| **What to remove** | Remove **from the system** everything related to that document: **embeddings** (all vector rows for that doc), **content** (chunk text in payload or in a separate table), and any **metadata** or relations (e.g. doc manifest, file path cache). No orphan data left. |
| **When to run the cleanup** | (1) **On a schedule** (e.g. daily cron or background task): scan for docs where `last_used_timestamp < now - configured_days`, then delete them. (2) Optionally **on add**: when adding a new document, run the same cleanup first so expired docs are removed before new ones are indexed. |

**Why this strategy works well:** It is **automatic** (no user action required), **fair** (only unused knowledge is removed), and **configurable** (X days can be 7, 30, 90, etc.). Actively used documents stay; stale ones are dropped. Implementing `last_used_timestamp` and a single cleanup job (or cleanup-on-add) gives you a clear, predictable policy for when and how to delete knowledge and all related things in the system.

#### Knowledge base backend: Cognee vs built-in RAG

The **database and vector database** used for the knowledge base are **selectable** so you can use the same stack as your main memory:

| `knowledge_base.backend` | Meaning | Where data lives |
|--------------------------|---------|-------------------|
| **auto** (default) | Use the **same** backend as `memory_backend`. | **Cognee**: Cognee’s relational + vector + graph (same as memory; dataset name `kb_{user_id}`). **Chroma**: `core.yml` **vectorDB** (separate collection, e.g. `homeclaw_kb`). |
| **cognee** | Force Cognee for the KB. | Cognee’s stores (same as when memory is Cognee). Requires Cognee configured (e.g. `cognee:` in `core.yml` or Cognee `.env`). |
| **chroma** | Force built-in RAG (Chroma / Qdrant / etc.) for the KB. | `core.yml` **vectorDB** and **collection_name**; same as skills/memory when `memory_backend: chroma`. |

- With **memory_backend: cognee** and **knowledge_base.backend: auto** (default), the KB uses **Cognee** (same DB and vector store as conversation memory).
- With **memory_backend: chroma** and **knowledge_base.backend: auto**, the KB uses the **built-in** vector store from **vectorDB** and **knowledge_base.collection_name**.
- You can override: e.g. **memory_backend: cognee** with **knowledge_base.backend: chroma** to keep conversation memory on Cognee but store the KB in your own Chroma/vectorDB.

**Cognee KB and graph search:** When the KB backend is Cognee, KB content goes through the same pipeline as Cognee memory: **add** → **cognify** (chunking, embedding, and entity/relationship extraction into the graph). Cognee’s **search** defaults to **GRAPH_COMPLETION**, so **graph search applies to knowledge base content too**.

**Knowledge base reset:** To clear the entire knowledge base (all users, all sources), call **POST or GET** `http://<core_host>:<core_port>/knowledge_base/reset`. Same style as `/memory/reset`; no auth by default—protect in production if needed.

**Cognee KB remove and growth control:** We use **one Cognee dataset per (user_id, source_id)** so `remove_by_source_id` deletes that dataset (whole document). To **prevent Cognee from growing without bound**, we keep a small **sidecar DB** (e.g. `database/kb_cognee_meta.db`) that stores `(user_id, source_id, added_at)` for each KB source. Then:
- **cleanup_unused(user_id, unused_days)** removes sources whose **added_at** is older than `unused_days` (age-based TTL). So old, unused data is evicted even though Cognee doesn’t track last_used.
- **Automatic cleanup:** Cleanup runs **automatically at the start of every add** for that user: we call cleanup_unused with `unused_ttl_days` before adding, so old entries are evicted whenever new content is added. There is no separate scheduled job; if no one adds to the KB for a long time, old data stays until the next add (or until something explicitly calls cleanup_unused).
- We then optionally enforce a **cap** (if **max_sources_per_user** is set): evict the oldest sources until under the cap before adding. So Cognee stays bounded by both **age** and **count**.

#### When is the knowledge base used? (summary)

The knowledge base is used **only when**:

1. **Config**: `knowledge_base.enabled` is **true** in `config/core.yml` (default is **false**). If `enabled: false`, the KB is never created and never queried.
2. **Retrieval (read)** happens in two ways:
   - **Automatic injection**: On every user message that goes through **`answer_from_memory`**, Core runs a vector search, **filters results by threshold** (see below), and only injects chunks that pass into the system prompt. If **none** pass the threshold, **no** KB block is added—that is expected (not every message is about the knowledge base).
   - **As tools (for complex tasks)**: The LLM can also call **`knowledge_base_search`** (query), **`knowledge_base_add`** (insert or summarize into KB), and **`knowledge_base_remove`** (remove by source_id) when it needs to complete a complex task—e.g. insert a doc, summarize, or query explicitly.
3. **Threshold filtering**: Only chunks that meet the configured **similarity** threshold are injected. Set **`retrieval_min_score`** (0–1, higher = more relevant); only chunks with `score >= retrieval_min_score` are injected. If no chunks pass, the reply has no KB block. (Chroma returns distance; we normalize to similarity internally.)
4. **Add/remove** happen **only** when the user (or LLM following the user) explicitly asks to save or remove content, e.g. “add this to my knowledge base” or via **`knowledge_base_add`** / **`knowledge_base_remove`**. Nothing is auto-added from `document_read` or `web_search`.

So: **enable** the KB with `knowledge_base.enabled: true`. Automatic injection uses a **threshold** so only relevant chunks are injected (zero is fine). The KB is also available **as tools** for complex tasks (query, add, remove).

#### Implementation: when and how to use the knowledge base

The user knowledge base (Option C) is implemented with a **selectable backend** (see above). Config is under **`knowledge_base:`** in `core.yml` (`enabled`, `backend`, `collection_name`, `retrieval_min_score` — plus chroma-only `chunk_size`, `chunk_overlap`, `unused_ttl_days`, `embed_timeout`, `store_timeout`).

| Aspect | Behavior |
|--------|----------|
| **When we retrieve** | (1) **Automatic**: We run a vector search in `answer_from_memory`, **filter by similarity** (`retrieval_min_score`, 0–1); only chunks with score ≥ threshold are injected; if none pass, no KB block is added. (2) **As tools**: The LLM can call **`knowledge_base_search`** (query), **`knowledge_base_add`** (insert/summarize), **`knowledge_base_remove`** (remove by source) for complex tasks. |
| **When we add** | **Only on explicit user/LLM action.** We do **not** auto-add on every `document_read` or `web_search`. The user (or LLM following the user) must say e.g. “add this to my knowledge base” or call the **`knowledge_base_add`** tool with content, `source_type`, and optional `source_id`. So the KB grows only when the user chooses to save something. |
| **Long and multi-document** | **Yes.** Long documents are **chunked** before being added; answers use **only retrieved chunks**, so the prompt gets relevant parts instead of the whole file. Multi-document is the same: multiple sources (files, URLs, web snippets) are stored with different `source_id`s; retrieval returns the most relevant chunks across all of them. So the knowledge base **does** address the document analysis and handling problem for long and multi-document use cases. |
| **Stability** | **No step should hang the system.** All KB operations use **timeouts** (embed, store, search) and **try/except**. On failure we return an **empty list** (search), an **error string** (add, remove, cleanup), or **skip** (e.g. in `answer_from_memory` we log and continue without KB context). The main reply and tool loop **never** block on a broken KB; we always have a safe fallback. |

#### How add works: filtering, chunking, and embedding

When you add a document or web content to the knowledge base, the pipeline is:

| Step | Built-in (chroma) | Cognee |
|------|-------------------|--------|
| **1. Filter useless content** | We **prepare** the text: strip HTML (script/style/tags), collapse whitespace, drop boilerplate lines. Only substantive text is passed on. | Same: we run the same **prepare** step so Cognee receives clean text, not raw HTML or nav junk. |
| **2. Chunk** | We split the prepared text into overlapping chunks (`chunk_size` / `chunk_overlap` in config), breaking at paragraph/line/sentence. | **Cognee does it:** we send the prepared string to `cognee.add()` then **cognify**; Cognee handles chunking. |
| **3. Embed** | We embed each chunk with our embedding model and store vectors + metadata. | **Cognee does it:** cognify produces embeddings and writes to Cognee’s vector store. |
| **4. Graph / store** | N/A (vector only). | **Cognee does it:** cognify also does entity/relationship extraction and writes to the graph; search can use graph (e.g. GRAPH_COMPLETION). |

So: **we only do the first step** (filter HTML and noise). With **Cognee**, Cognee does chunking, embedding, and graph for us. With **built-in (chroma)**, we do chunking and embedding ourselves in our code.

#### Deletion: whole document (all chunks)

**Built-in (chroma) KB:** When you delete by **source_id**, we delete **the whole document** (all chunks with that `(user_id, source_id)`). **cleanup_unused** evicts by **source_id** (entire documents unused for X days).

**Cognee KB:** We use **one dataset per (user_id, source_id)**. Deletion by **source_id** is implemented by calling Cognee’s **list_datasets** and **delete_dataset**: we find the dataset for that source and delete it, removing the whole document. So deletion semantics match the built-in KB (whole document removed).
