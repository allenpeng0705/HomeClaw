import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAuthStatus, postSetup } from "../api/auth";

export function SetupPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchAuthStatus()
      .then((s) => {
        if (s.admin_configured) {
          window.location.replace("/app/login");
        }
      })
      .catch(() => {});
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await postSetup(username.trim(), password);
      window.location.assign("/app/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card-centered">
      <img
        className="logo"
        src="/static/img/homeclaw-logo.png"
        alt="HomeClaw"
      />
      <h1 className="title">Create admin account</h1>
      <p className="subtitle">
        Set the single admin account for this Portal. You will use it to sign in
        and configure HomeClaw.
      </p>
      <form className="form" onSubmit={onSubmit}>
        <label className="field">
          <span>Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            placeholder="admin"
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
            placeholder="••••••••"
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="footer-note">
        Already set up? <Link to="/login">Sign in</Link>
      </p>
    </div>
  );
}
