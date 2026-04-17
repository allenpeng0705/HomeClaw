import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { fetchAuthStatus } from "../api/auth";

/**
 * /app/ — send users to setup, login, or the classic dashboard (until the SPA owns it).
 */
export function EntryGate() {
  const [phase, setPhase] = useState<"load" | "setup" | "login" | "dash">("load");

  useEffect(() => {
    let cancelled = false;
    fetchAuthStatus()
      .then((s) => {
        if (cancelled) return;
        if (!s.admin_configured) setPhase("setup");
        else if (!s.logged_in) setPhase("login");
        else setPhase("dash");
      })
      .catch(() => {
        if (!cancelled) setPhase("login");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (phase === "dash") {
      window.location.assign("/dashboard");
    }
  }, [phase]);

  if (phase === "load") {
    return (
      <div className="card-centered">
        <p className="muted">Loading…</p>
      </div>
    );
  }
  if (phase === "setup") return <Navigate to="/setup" replace />;
  if (phase === "login") return <Navigate to="/login" replace />;
  return (
    <div className="card-centered">
      <p className="muted">Opening dashboard…</p>
    </div>
  );
}
