# Static file links (path in URL, token for one-user access)

With **static** file links, the URL path is human-readable: `core_public_url / file_static_prefix / scope / path` (e.g. `https://homeclaw.example.com/files/AllenPeng/images/ID1.jpg?token=...`). A **token is still required** so the link only grants access to that user’s sandbox (that scope+path); Core serves the file after verifying the token. No other user’s files can be accessed with that link.

---

## When to use static vs token

| Style   | Config                | Link form                    | Pros / cons |
|---------|------------------------|------------------------------|-------------|
| **token** (default) | `file_link_style: token` | `/files/out?token=...&path=...` | Signed, time-limited; Core serves the file. |
| **static**          | `file_link_style: static` | `/files/AllenPeng/images/ID1.jpg?token=...` | Path in URL; same token security; link only accesses that user’s sandbox. |

Use **static** when you want readable URLs (scope/path in the path) while still restricting each link to one user’s file (token-bound).

---

## Config (core.yml)

```yaml
# Required for any shareable file links
core_public_url: "https://homeclaw.example.com"
homeclaw_root: "/path/to/your/sandbox/root"
auth_api_key: "your-secret"   # required to sign static links too

# Static links: path in URL, token in query (link only accesses that user's sandbox)
file_link_style: static
file_static_prefix: files   # URL path prefix → /files/scope/path?token=...
```

- **file_static_prefix** (default `files`): links look like `{core_public_url}/files/{scope}/{path}?token=...` (e.g. `/files/AllenPeng/images/ID1.jpg?token=...`).
- **file_view_link_expiry_sec**: how long file/view links (token) are valid. Set in **config/core.yml**: seconds (e.g. `604800`) or days (e.g. `"7d"`). Default **7 days**; max **365 days**. Applies to both token-style and static-style links.
- **Serving**: Core serves these URLs itself (GET `/files/{scope}/{path}?token=...`). The token is verified; only that scope+path is served. No need to point the web server’s www_root at homeclaw_root for this.

---

## Security

Each link is bound to one **(scope, path)** by the token. So a link generated for user AllenPeng only accesses files under that user’s sandbox; it cannot be changed to access another user’s folder. The token is signed and time-limited (same as token-style links).
