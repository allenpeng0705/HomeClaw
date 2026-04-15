"""
VMPrint hybrid preview: resolve ./styles.css and ./assets/*.js when the HTML document URL is
``GET /files/out?path=output/foo.preview.html``. Browsers resolve ``./assets/x.js`` against the
pathname ``/files/out``, producing ``/files/assets/x.js`` (wrong). Core can rewrite href/src on
serve (``rewrite_vmprint_preview_html_assets``); this client-side loader fixes previews opened
through proxies or copied links without that rewrite.
"""

from __future__ import annotations

import re
from typing import Sequence, Tuple


def _safe_asset_version(v: str) -> str:
    s = (v or "").strip()
    if re.fullmatch(r"[A-Za-z0-9._-]+", s):
        return s
    return "v1"


def vmprint_hybrid_preview_loaders(
    asset_version: str = "v1", *, extra_body_script_rels: Sequence[str] = ()
) -> Tuple[str, str]:
    """
    Return (head_html, body_tail_html) for a VMPrint browser preview page.

    head_html: defines ``window.__hcVmprintAsset`` and injects the stylesheet via document.write.
    body_tail_html: loads VMPrint engine scripts + pipeline + ui in order (dynamic script tags).
    """
    av = _safe_asset_version(asset_version)
    extras = [str(x).lstrip("/").replace("\\", "/") for x in (extra_body_script_rels or ()) if str(x).strip()]
    extras_js = "".join(f",a({x!r})" for x in extras)

    head_html = (
        "<script>"
        "(function(){"
        "function a(r){r=String(r||'').replace(/^\\.\\//,'');"
        "try{var L=window.location,sp=new URLSearchParams(L.search),"
        "p=String(sp.get('path')||'');"
        "if(!p)return './'+r;var pn=L.pathname||'';"
        "if(pn.indexOf('files/out')<0)return './'+r;"
        "var pts=p.split('/');pts.pop();var px=pts.join('/');"
        "var f=(px?px+'/':'')+r.replace(/^\\/+/,'');sp.set('path',f);"
        "var q=sp.toString();return L.origin+pn+(q?'?'+q:'');}"
        "catch(e){return './'+r;}}"
        "window.__hcVmprintAsset=a;"
        "document.write(\"<link rel='stylesheet' href='\"+a('styles.css').replace(/'/g,'%27')+\"'>\");"
        "})();"
        "</script>"
    )

    body_tail = (
        "<script>"
        "(function(){"
        "function a(r){return window.__hcVmprintAsset?window.__hcVmprintAsset(r):('./'+String(r).replace(/^\\.\\//,''));}"
        f"var V={av!r};"
        "var urls=["
        "a('_vmprint_assets/'+V+'/vmprint-fontkit.js'),"
        "a('_vmprint_assets/'+V+'/vmprint-engine.js'),"
        "a('_vmprint_assets/'+V+'/vmprint-web-fonts.js'),"
        "a('_vmprint_assets/'+V+'/vmprint-context-canvas.js'),"
        "a('assets/pipeline.js'),a('assets/ui.js')"
        f"{extras_js}"
        "];"
        "function n(i){if(i>=urls.length)return;var s=document.createElement('script');"
        "s.src=urls[i];s.onload=function(){n(i+1);};"
        "s.onerror=function(){console.error('[vmprint] load failed',urls[i]);n(i+1);};"
        "(document.head||document.documentElement).appendChild(s);}"
        "n(0);"
        "})();"
        "</script>"
    )
    return (head_html, body_tail)
