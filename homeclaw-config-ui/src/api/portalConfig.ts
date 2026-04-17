const STORAGE_KEY = "homeclaw_portal_secret";

export function getStoredPortalSecret(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setStoredPortalSecret(secret: string): void {
  try {
    if (secret) {
      sessionStorage.setItem(STORAGE_KEY, secret);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* ignore */
  }
}

export type ConfigName =
  | "llm"
  | "skills_and_plugins"
  | "core"
  | "user"
  | "memory_kb"
  | "friend_presets"
  | "peers";

function headers(secret: string): HeadersInit {
  const h: Record<string, string> = { Accept: "application/json" };
  if (secret) {
    h["X-Portal-Secret"] = secret;
  }
  return h;
}

export async function fetchConfig(
  name: ConfigName,
  secret: string
): Promise<unknown> {
  const res = await fetch(`/api/config/${name}`, {
    method: "GET",
    headers: headers(secret),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 500)}`);
  }
  return res.json() as Promise<unknown>;
}

/** Portal PATCH returns `{ "result": "ok" }`; call GET again to see merged config. */
export async function patchConfig(
  name: ConfigName,
  body: unknown,
  secret: string
): Promise<void> {
  const res = await fetch(`/api/config/${name}`, {
    method: "PATCH",
    headers: {
      ...Object.fromEntries(
        Object.entries(headers(secret) as Record<string, string>)
      ),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 500)}`);
  }
}
