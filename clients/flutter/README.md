# HomeClaw Flutter companion app (placeholder)

Cross-platform companion app for **HomeClaw Core**: iOS, Android, macOS, Windows (Linux later).

## Connection

- Connects to Core’s HTTP/WebSocket URL (e.g. `http://127.0.0.1:9000` or a remote URL via Tailscale/Cloudflare).
- Uses **POST /inbound** or **WebSocket /ws** for chat; optional API key when Core has `auth_enabled: true`.

## Status

Placeholder. When implementing:

1. Create Flutter project here (e.g. `flutter create .`).
2. Add Core URL (and optional API key) in settings; persist in secure storage.
3. Implement HTTP client for `/inbound` or WebSocket client for `/ws`.
4. Add UI: message input, reply display, status. Then extend with sessions, device actions, etc.

See **../README.md** and **docs_design/HomeClawCompanionConnectivity.md** for connectivity options.
