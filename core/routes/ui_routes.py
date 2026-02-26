"""
UI route: GET /ui launcher page (sessions + plugin UIs + testing buttons).
"""
from fastapi.responses import HTMLResponse

from base.util import Util


def get_ui_launcher_handler(core):
    """Return handler for GET /ui. No API key required; auth is only for Testing buttons (Companion or X-API-Key)."""
    async def ui_launcher():
        try:
            session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
            sessions_enabled = session_cfg.get("api_enabled", True)
            sessions_list = []
            if sessions_enabled:
                try:
                    raw = core.get_sessions(num_rounds=50, fetch_all=True)
                    sessions_list = list(raw) if isinstance(raw, (list, tuple)) else []
                except Exception:
                    pass
            plugins_with_ui = []
            pm = getattr(core, "plugin_manager", None)
            for pid, plug in (getattr(pm, "plugin_by_id", None) or {}).items():
                if not isinstance(plug, dict) or not plug.get("ui"):
                    continue
                plugins_with_ui.append({"plugin_id": pid, "name": plug.get("name") or pid, "ui": plug["ui"]})
            html_parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>HomeClaw UI</title>",
            "<style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;}",
            "h1,h2{color:#333;} ul{list-style:none;padding:0;} li{margin:0.5rem 0;}",
            "a{color:#e65100;} a:hover{text-decoration:underline;} .meta{color:#666;font-size:0.9rem;}",
            "table{border-collapse:collapse;width:100%;margin-top:0.5rem;} th,td{border:1px solid #ddd;padding:0.4rem 0.6rem;text-align:left;} th{background:#f5f5f5;}</style></head><body>",
            "<h1>HomeClaw</h1>",
            "<h2>Sessions</h2>",
            "<p class='meta'>Recent chat sessions (session_id, app_id, user_id, created). Data from Core; session.api_enabled in config.</p>",
            ]
            if sessions_list:
                html_parts.append("<table><thead><tr><th>session_id</th><th>app_id</th><th>user_id</th><th>created_at</th></tr></thead><tbody>")
                for s in sessions_list[:30]:
                    sid = (s.get("session_id") or "").replace("<", "&lt;").replace(">", "&gt;")
                    aid = (s.get("app_id") or "").replace("<", "&lt;").replace(">", "&gt;")
                    uid = (s.get("user_id") or "").replace("<", "&lt;").replace(">", "&gt;")
                    created = (s.get("created_at") or "").replace("<", "&lt;").replace(">", "&gt;") if s.get("created_at") else ""
                    html_parts.append(f"<tr><td><code>{sid}</code></td><td>{aid}</td><td>{uid}</td><td>{created}</td></tr>")
                html_parts.append("</tbody></table>")
            else:
                html_parts.append("<p class='meta'>No sessions yet, or session API disabled.</p>")
            html_parts.append("<h2>Plugin UIs</h2><p class='meta'>WebChat, Control UI, Dashboard, TUI. Open a link to use the UI.</p><ul>")
            for p in plugins_with_ui:
                name = p["name"]
                ui = p["ui"]
                for label, val in [("WebChat", ui.get("webchat")), ("Control UI", ui.get("control")), ("Dashboard", ui.get("dashboard")), ("TUI", ui.get("tui"))]:
                    url = val if isinstance(val, str) else (val.get("url") or val.get("base_path") if isinstance(val, dict) else None)
                    if url:
                        if label == "TUI" and not (url.startswith("http://") or url.startswith("https://")):
                            html_parts.append(f"<li><strong>{name}</strong> — <span class='meta'>{label}: run <code>{url}</code></span></li>")
                        else:
                            html_parts.append(f"<li><strong>{name}</strong> — <a href='{url}' target='_blank' rel='noopener'>{label}</a></li>")
                for c in (ui.get("custom") or []):
                    c_url = c.get("url") or c.get("base_path") if isinstance(c, dict) else None
                    c_name = (c.get("name") or c.get("id") or "Custom") if isinstance(c, dict) else "Custom"
                    if c_url:
                        html_parts.append(f"<li><strong>{name}</strong> — <a href='{c_url}' target='_blank' rel='noopener'>{c_name}</a></li>")
            html_parts.append("</ul><p class='meta'>Add plugins that declare <code>ui</code> in registration to see them here. See docs_design/PluginUIsAndHomeClawControlUI.md.</p>")
            auth_enabled_ui = bool(getattr(Util().get_core_metadata(), "auth_enabled", False))
            auth_key_ui = (getattr(Util().get_core_metadata(), "auth_api_key", None) or "").strip()
            if auth_enabled_ui and auth_key_ui:
                html_parts.append("<h2>Testing</h2><p class='meta'>Clear data for a clean test. When auth is enabled, use Companion (Manage Core → Testing) or send X-API-Key / Authorization: Bearer with requests.</p>")
            else:
                html_parts.append("<h2>Testing</h2><p class='meta'>Clear data for a clean test.</p>")
            html_parts.append("<div style='display:flex;flex-wrap:wrap;gap:0.5rem;margin-top:0.5rem;'>")
            html_parts.append("<button type='button' class='test-btn' data-url='/memory/reset' data-label='Clear memory'>Clear memory</button>")
            html_parts.append("<button type='button' class='test-btn' data-url='/knowledge_base/reset' data-label='Clear knowledge base'>Clear knowledge base</button>")
            html_parts.append("<button type='button' class='test-btn' data-url='/api/testing/clear-all' data-label='Clear all (skills &amp; plugins)'>Clear all (skills &amp; plugins)</button>")
            html_parts.append("</div><p id='test-msg' class='meta' style='margin-top:0.5rem;min-height:1.2rem;'></p>")
            html_parts.append("<style>.test-btn{padding:0.4rem 0.8rem;cursor:pointer;background:#e65100;color:#fff;border:none;border-radius:4px;font-size:0.9rem;}.test-btn:hover{background:#bf360c;}</style>")
            html_parts.append("<script>document.querySelectorAll('.test-btn').forEach(function(btn){btn.onclick=function(){var url=btn.getAttribute('data-url');var label=btn.getAttribute('data-label');var msg=document.getElementById('test-msg');msg.textContent=label+'...';var opts={method:'POST'};if(window._homeclaw_api_key){opts.headers={'X-API-Key':window._homeclaw_api_key,'Authorization':'Bearer '+window._homeclaw_api_key};}fetch(url,opts).then(function(r){return r.ok ? r.text().then(function(t){msg.textContent=label+' done.';}) : r.text().then(function(t){msg.textContent=label+' failed: '+t;});}).catch(function(e){msg.textContent=label+' error: '+e.message;});};});</script>")
            html_parts.append("</body></html>")
            return HTMLResponse(content="".join(html_parts))
        except Exception as e:
            err_msg = str(e).replace("<", "&lt;").replace(">", "&gt;")[:500]
            fallback = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>HomeClaw UI</title></head><body>"
                "<h1>HomeClaw</h1><p>Launcher could not load. This page does not require an API key.</p>"
                f"<p class='meta'>Error: {err_msg}</p>"
                "<p class='meta'>Check Core logs. If auth is enabled, only the Testing buttons need X-API-Key.</p></body></html>"
            )
            return HTMLResponse(content=fallback, status_code=200)
    return ui_launcher
