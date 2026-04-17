import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAuthStatus, postLogin } from "../api/auth";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchAuthStatus()
      .then((s) => {
        if (!s.admin_configured) {
          window.location.replace("/app/setup");
        } else if (s.logged_in) {
          window.location.assign("/dashboard");
        }
      })
      .catch(() => {});
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await postLogin(username.trim(), password);
      window.location.assign("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
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
      <h1 className="title">Welcome back</h1>
      <p className="subtitle">Sign in with your Portal admin account.</p>
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
            autoComplete="current-password"
            required
            placeholder="••••••••"
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Signing in…" : "Log in"}
        </button>
      </form>
      <p className="footer-note">
        First time? <Link to="/setup">Create admin account</Link>
      </p>
    </div>
  );
}
