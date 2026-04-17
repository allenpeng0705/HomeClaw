import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchConfig,
  getStoredPortalSecret,
  patchConfig,
  setStoredPortalSecret,
  type ConfigName,
} from "./api/portalConfig";

const CONFIG_NAMES: { id: ConfigName; label: string }[] = [
  { id: "llm", label: "LLM" },
  { id: "skills_and_plugins", label: "Skills & plugins" },
  { id: "core", label: "Core" },
  { id: "user", label: "User" },
  { id: "memory_kb", label: "Memory / KB" },
  { id: "friend_presets", label: "Friend presets" },
  { id: "peers", label: "Peers" },
];

function stringifyJson(data: unknown): string {
  return JSON.stringify(data, null, 2);
}

export default function App() {
  const [secret, setSecret] = useState(getStoredPortalSecret);
  const [active, setActive] = useState<ConfigName>("llm");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const activeLabel = useMemo(
    () => CONFIG_NAMES.find((c) => c.id === active)?.label ?? active,
    [active]
  );

  const load = useCallback(async () => {
    setStatus(null);
    setLoading(true);
    try {
      const data = await fetchConfig(active, secret);
      setText(stringifyJson(data));
      setStatus("Loaded.");
    } catch (e) {
      setText("");
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [active, secret]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setStatus(null);
    setLoading(true);
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(text) as unknown;
      } catch {
        setStatus("Invalid JSON — fix syntax before saving.");
        setLoading(false);
        return;
      }
      await patchConfig(active, parsed, secret);
      const data = await fetchConfig(active, secret);
      setText(stringifyJson(data));
      setStatus("Saved.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>HomeClaw configuration</h1>
        <p className="subtitle">
          Edit YAML-backed configs via the Portal API. Run Portal (
          <code>python3 -m main portal</code>) and this UI together; dev server
          proxies <code>/api</code> to Portal.
        </p>
      </header>

      <section className="panel">
        <label className="field">
          <span>Portal secret</span>
          <input
            type="password"
            autoComplete="off"
            placeholder="Same as portal_secret in config"
            value={secret}
            onChange={(e) => {
              const v = e.target.value;
              setSecret(v);
              setStoredPortalSecret(v);
            }}
          />
        </label>
        <p className="hint">
          Required for API access unless you are logged into Portal in the same
          browser (cookie). This app stores the secret in session storage only.
        </p>
      </section>

      <nav className="tabs" aria-label="Config files">
        {CONFIG_NAMES.map((c) => (
          <button
            key={c.id}
            type="button"
            className={c.id === active ? "tab active" : "tab"}
            onClick={() => setActive(c.id)}
          >
            {c.label}
          </button>
        ))}
      </nav>

      <div className="toolbar">
        <span className="active-name">{activeLabel}</span>
        <button type="button" onClick={() => void load()} disabled={loading}>
          Reload
        </button>
        <button type="button" onClick={() => void save()} disabled={loading}>
          Save
        </button>
      </div>

      {status && (
        <div className={status.startsWith("Loaded") || status === "Saved." ? "msg ok" : "msg err"}>
          {status}
        </div>
      )}

      <textarea
        className="editor"
        spellCheck={false}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={loading}
        aria-label={`JSON for ${active}`}
      />

      <footer className="footer">
        <p>
          Saving sends a PATCH merge for <code>{active}</code> (same behavior as
          Portal&apos;s config API).
        </p>
      </footer>
    </div>
  );
}
