/**
 * MemOS standalone HTTP server for HomeClaw.
 * Run from vendor/memos after copying MemOS source (src/, package.json, etc.) here.
 * Uses same MemOS core (store, worker, engine, capture) without OpenClaw.
 *
 * Endpoints:
 *   GET  /health                  — 200 if ready
 *   POST /memory/add              — body: { messages: [{ role, content }], sessionKey?, agentId? }
 *   POST /memory/search           — body: { query, maxResults?, minScore?, agentId? }
 *   GET  /memory/task/:id/summary — task summary (Goal, Key Steps, Result, Key Details)
 *   POST /memory/skill_search     — body: { query, scope?, agentId? } → FTS + vector + LLM relevance
 *   GET  /memory/skill/:id           — skill metadata + SKILL.md content
 *   GET  /memory/tasks                — list tasks (query: agentId?, status?, limit?, offset?)
 *   POST /memory/write_public         — body: { content, summary? } — write public memory (visible to all)
 *   PUT  /memory/skill/:id/visibility — body: { visibility: "public"|"private" } — skill publish/unpublish
 *   POST /memory/reset                  — clear all memories (and tasks/skills if store supports it). Used by HomeClaw /memory/reset.
 *
 * Optional: set MEMOS_VIEWER_PORT (e.g. 18799) to start the Memory Viewer UI on a second port.
 * Config: memos-standalone.json in cwd, or MEMOS_CONFIG path. Port: MEMOS_STANDALONE_PORT (default 39201).
 */
import * as fs from "fs";
import * as path from "path";
import * as http from "http";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { v4: uuid } = require("uuid");

const DEFAULT_PORT = 39201;
const EVIDENCE_TAG = "STORED_MEMORY";

function loadConfig(): Record<string, unknown> {
  const configPath =
    process.env.MEMOS_CONFIG ||
    path.join(process.cwd(), "memos-standalone.json");
  if (fs.existsSync(configPath)) {
    try {
      const raw = fs.readFileSync(configPath, "utf-8");
      return JSON.parse(raw) as Record<string, unknown>;
    } catch (e) {
      console.warn("[memos-standalone] Config load failed:", e);
    }
  }
  const stateDir = process.env.MEMOS_STATE_DIR || path.join(process.cwd(), "data");
  return {
    storage: { dbPath: path.join(stateDir, "memos.db") },
    embedding: { provider: "local" },
    recall: { maxResultsDefault: 20, minScoreDefault: 0.45 },
  };
}

async function main() {
  const stateDir = process.env.MEMOS_STATE_DIR || path.join(process.cwd(), "data");
  const workspaceDir = path.join(stateDir, "workspace");
  try {
    fs.mkdirSync(stateDir, { recursive: true });
    fs.mkdirSync(workspaceDir, { recursive: true });
  } catch (_) {}

  const rawConfig = loadConfig();
  const log = {
    debug: (msg: string) => console.debug("[memos-standalone]", msg),
    info: (msg: string) => console.log("[memos-standalone]", msg),
    warn: (msg: string) => console.warn("[memos-standalone]", msg),
    error: (msg: string) => console.error("[memos-standalone]", msg),
  };

  const { buildContext } = await import("./src/config");
  const { SqliteStore } = await import("./src/storage/sqlite");
  const { Embedder } = await import("./src/embedding/index");
  const { IngestWorker } = await import("./src/ingest/worker");
  const { RecallEngine } = await import("./src/recall/engine");
  const { captureMessages } = await import("./src/capture/index");
  const { SkillEvolver } = await import("./src/skill/evolver");

  const ctx = buildContext(stateDir, workspaceDir, rawConfig as any, log);
  const store = new SqliteStore(ctx.config.storage!.dbPath!, log);
  const embedder = new Embedder(ctx.config.embedding, log);
  const worker = new IngestWorker(store, embedder, ctx);
  const engine = new RecallEngine(store, embedder, ctx);
  const skillCtx = { ...ctx, workspaceDir };
  const skillEvolver = new SkillEvolver(store, engine, skillCtx);
  worker.getTaskProcessor().onTaskCompleted((task: any) => {
    skillEvolver.onTaskCompleted(task).catch((err: Error) => {
      log.warn("SkillEvolver onTaskCompleted error: " + (err?.message || err));
    });
  });

  log.info("MemOS standalone ready (stateDir=" + stateDir + ", skill evolution enabled)");

  function readBody(req: http.IncomingMessage): Promise<string> {
    return new Promise((resolve, reject) => {
      const chunks: Buffer[] = [];
      req.on("data", (chunk) => chunks.push(chunk));
      req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
      req.on("error", reject);
    });
  }

  function send(res: http.ServerResponse, status: number, body: string | object, contentType = "application/json") {
    try {
      const data = typeof body === "string" ? body : JSON.stringify(body);
      if (!res.headersSent) {
        res.writeHead(status, {
          "Content-Type": contentType,
          "Content-Length": Buffer.byteLength(data, "utf-8"),
        });
      }
      res.end(data);
    } catch (e) {
      log.warn("send failed: " + (e instanceof Error ? e.message : String(e)));
    }
  }

  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url || "/";
      const method = (req.method || "GET").toUpperCase();

    if (method === "GET" && (url === "/health" || url === "/")) {
      send(res, 200, { ok: true, service: "memos-standalone" });
      return;
    }

    if (method === "POST" && url === "/memory/add") {
      try {
        const raw = await readBody(req);
        const body = JSON.parse(raw || "{}") as {
          messages?: Array<{ role: string; content: string }>;
          sessionKey?: string;
          agentId?: string;
        };
        const messages = Array.isArray(body.messages) ? body.messages : [];
        const sessionKey = (body.sessionKey || "homeclaw").toString();
        const agentId = (body.agentId || "main").toString();
        const owner = "agent:" + agentId;
        const turnId = uuid();

        if (messages.length === 0) {
          send(res, 400, { error: "messages array required" });
          return;
        }

        const captured = captureMessages(
          messages as Array<{ role: string; content: string; toolName?: string }>,
          sessionKey,
          turnId,
          EVIDENCE_TAG,
          log,
          owner
        );
        worker.enqueue(captured);
        send(res, 202, { ok: true, enqueued: captured.length, sessionKey, agentId });
      } catch (e) {
        log.error("add failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    if (method === "POST" && url === "/memory/reset") {
      try {
        if (store && typeof (store as any).reset === "function") {
          (store as any).reset();
          send(res, 200, { ok: true, message: "MemOS memory store reset." });
        } else {
          send(res, 501, { error: "Store does not support reset. Update MemOS SqliteStore to implement reset()." });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        log.error("memory reset failed: " + msg);
        try {
          send(res, 500, { error: msg });
        } catch (_) {
          try {
            if (!res.headersSent) res.writeHead(500, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: msg }));
          } catch (_) {}
        }
      }
      return;
    }

    if (method === "POST" && url === "/memory/search") {
      try {
        const raw = await readBody(req);
        const body = JSON.parse(raw || "{}") as {
          query?: string;
          maxResults?: number;
          minScore?: number;
          agentId?: string;
        };
        const query = (body.query || "").toString();
        const agentId = (body.agentId || "main").toString();
        const ownerFilter = ["agent:" + agentId, "public"];

        const result = await engine.search({
          query,
          maxResults: body.maxResults ?? 20,
          minScore: body.minScore ?? 0.45,
          ownerFilter,
        });
        send(res, 200, result);
      } catch (e) {
        log.error("search failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    const pathname = (url.split("?")[0] || "").replace(/\/+$/, "") || "/";
    const pathParts = pathname.split("/").filter(Boolean);

    if (method === "GET" && pathParts[0] === "memory" && pathParts[1] === "task" && pathParts[2] && pathParts[3] === "summary") {
      let taskId: string;
      try {
        taskId = decodeURIComponent(pathParts[2]);
      } catch (_) {
        send(res, 400, { error: "Invalid task id in path" });
        return;
      }
      try {
        const task = store.getTask(taskId);
        if (!task) {
          send(res, 404, { error: "Task not found", taskId });
          return;
        }
        send(res, 200, {
          taskId: task.id,
          sessionKey: task.sessionKey,
          title: task.title,
          summary: task.summary,
          status: task.status,
          startedAt: task.startedAt,
          endedAt: task.endedAt,
          owner: task.owner,
        });
      } catch (e) {
        log.error("task summary failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    if (method === "POST" && url === "/memory/skill_search") {
      try {
        const raw = await readBody(req);
        const body = JSON.parse(raw || "{}") as {
          query?: string;
          scope?: "mix" | "self" | "public";
          agentId?: string;
        };
        const query = (body.query || "").toString();
        const scope = (body.scope === "self" || body.scope === "public" ? body.scope : "mix") as "mix" | "self" | "public";
        const agentId = (body.agentId || "main").toString();
        const currentOwner = "agent:" + agentId;
        const hits = await engine.searchSkills(query, scope, currentOwner);
        send(res, 200, { hits });
      } catch (e) {
        log.error("skill_search failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    if (method === "GET" && pathParts[0] === "memory" && pathParts[1] === "skill" && pathParts[2] && pathParts[3] !== "visibility") {
      let skillId: string;
      try {
        skillId = decodeURIComponent(pathParts[2]);
      } catch (_) {
        send(res, 400, { error: "Invalid skill id in path" });
        return;
      }
      try {
        const skill = store.getSkill(skillId);
        if (!skill) {
          send(res, 404, { error: "Skill not found", skillId });
          return;
        }
        let content: string | null = null;
        const skillMdPath = path.join(skill.dirPath, "SKILL.md");
        if (fs.existsSync(skillMdPath)) {
          try {
            content = fs.readFileSync(skillMdPath, "utf-8");
          } catch (_) {}
        }
        if (content === null) {
          const latest = store.getLatestSkillVersion(skill.id);
          content = latest?.content ?? null;
        }
        send(res, 200, {
          skillId: skill.id,
          name: skill.name,
          description: skill.description,
          version: skill.version,
          status: skill.status,
          owner: skill.owner,
          visibility: skill.visibility,
          dirPath: skill.dirPath,
          content,
        });
      } catch (e) {
        log.error("skill get failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    if (method === "GET" && pathParts[0] === "memory" && pathParts[1] === "tasks") {
      try {
        let parsed: URL;
        try {
          parsed = new URL(url, "http://localhost");
        } catch (_) {
          send(res, 400, { error: "Invalid URL" });
          return;
        }
        const agentId = (parsed.searchParams.get("agentId") || "main").toString().slice(0, 256);
        const statusParam = parsed.searchParams.get("status");
        const status = (statusParam && ["active", "completed", "skipped"].includes(statusParam)) ? statusParam : undefined;
        const rawLimit = parseInt(parsed.searchParams.get("limit") || "50", 10);
        const limit = Number.isNaN(rawLimit) ? 50 : Math.min(100, Math.max(1, rawLimit));
        const rawOffset = parseInt(parsed.searchParams.get("offset") || "0", 10);
        const offset = Number.isNaN(rawOffset) ? 0 : Math.max(0, rawOffset);
        const owner = "agent:" + agentId;
        const { tasks, total } = store.listTasks({ owner, status, limit, offset });
        send(res, 200, { tasks: tasks || [], total: typeof total === "number" ? total : 0 });
      } catch (e) {
        log.error("tasks list failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    if (method === "POST" && url === "/memory/write_public") {
      try {
        const raw = await readBody(req);
        let body: { content?: string; summary?: string };
        try {
          body = JSON.parse(raw || "{}") as { content?: string; summary?: string };
        } catch (_) {
          send(res, 400, { error: "Invalid JSON body" });
          return;
        }
        const content = (body.content != null ? String(body.content) : "").trim();
        if (!content) {
          send(res, 400, { error: "content is required and must be non-empty" });
          return;
        }
        const summary = (body.summary != null ? String(body.summary) : content.slice(0, 200)).trim();
        const now = Date.now();
        const chunkId = uuid();
        const chunk = {
          id: chunkId,
          sessionKey: "public",
          turnId: "public-" + now,
          seq: 0,
          role: "assistant",
          content,
          kind: "paragraph",
          summary,
          taskId: null as string | null,
          skillId: null as string | null,
          owner: "public",
          dedupStatus: "active" as const,
          dedupTarget: null as string | null,
          dedupReason: null as string | null,
          createdAt: now,
          updatedAt: now,
        };
        store.insertChunk(chunk as any);
        try {
          const [emb] = await embedder.embed([summary]);
          if (emb) store.upsertEmbedding(chunkId, emb);
        } catch (err) {
          log.warn("write_public embedding failed: " + (err as Error).message);
        }
        send(res, 200, { ok: true, id: chunkId, message: "Public memory written" });
      } catch (e) {
        log.error("write_public failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    if (method === "PUT" && pathParts[0] === "memory" && pathParts[1] === "skill" && pathParts[2] && pathParts[3] === "visibility") {
      let skillId: string;
      try {
        skillId = decodeURIComponent(pathParts[2]);
      } catch (_) {
        send(res, 400, { error: "Invalid skill id in path" });
        return;
      }
      try {
        const raw = await readBody(req);
        let body: { visibility?: string };
        try {
          body = JSON.parse(raw || "{}") as { visibility?: string };
        } catch (_) {
          send(res, 400, { error: "Invalid JSON body" });
          return;
        }
        const visibility = (body.visibility != null ? String(body.visibility) : "").trim();
        if (visibility !== "public" && visibility !== "private") {
          send(res, 400, { error: "visibility must be 'public' or 'private'" });
          return;
        }
        const skill = store.getSkill(skillId);
        if (!skill) {
          send(res, 404, { error: "Skill not found", skillId });
          return;
        }
        store.setSkillVisibility(skillId, visibility as "public" | "private");
        send(res, 200, { ok: true, skillId, visibility });
      } catch (e) {
        log.error("skill visibility failed: " + (e as Error).message);
        send(res, 500, { error: (e as Error).message });
      }
      return;
    }

    send(res, 404, { error: "Not found" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.error("Request handler error: " + msg);
      try {
        send(res, 500, { error: "Internal server error" });
      } catch (_) {
        try {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Internal server error" }));
        } catch (_) {}
      }
    }
  });

  const port = parseInt(process.env.MEMOS_STANDALONE_PORT || "", 10) || DEFAULT_PORT;
  server.listen(port, "127.0.0.1", () => {
    log.info("Standalone server listening on http://127.0.0.1:" + port);
  });

  const viewerPort = parseInt(process.env.MEMOS_VIEWER_PORT || "", 10);
  if (viewerPort > 0) {
    try {
      const { ViewerServer } = await import("./src/viewer/server");
      const viewer = new ViewerServer({
        store,
        embedder,
        port: viewerPort,
        log,
        dataDir: stateDir,
        ctx,
      });
      const viewerUrl = await viewer.start();
      log.info("MemOS Memory Viewer at " + viewerUrl);
      log.info("Password reset token: " + viewer.getResetToken());
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      log.warn("ViewerServer failed to start (set MEMOS_VIEWER_PORT to enable): " + msg);
    }
  }
}

main().catch((e) => {
  console.error("memos-standalone failed to start:", e);
  process.exit(1);
});
