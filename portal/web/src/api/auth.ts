export type AuthStatus = {
  admin_configured: boolean;
  logged_in: boolean;
  username: string | null;
};

const jsonHeaders = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const res = await fetch("/api/portal/auth/status", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Auth status failed: ${res.status}`);
  }
  return res.json() as Promise<AuthStatus>;
}

export async function postSetup(username: string, password: string): Promise<void> {
  const res = await fetch("/api/portal/auth/setup", {
    method: "POST",
    credentials: "same-origin",
    headers: jsonHeaders,
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail || res.statusText;
    throw new Error(detail);
  }
}

export async function postLogin(username: string, password: string): Promise<void> {
  const res = await fetch("/api/portal/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: jsonHeaders,
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail || "Invalid credentials";
    throw new Error(detail);
  }
}
