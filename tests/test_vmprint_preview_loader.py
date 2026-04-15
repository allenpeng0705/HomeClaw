"""VMPrint hybrid preview client-side asset URL helpers."""

from tools.vmprint_preview_loader import vmprint_hybrid_preview_loaders


def test_vmprint_hybrid_preview_loaders_includes_resolver_and_no_static_script_src():
    head, body = vmprint_hybrid_preview_loaders("v1")
    assert "window.__hcVmprintAsset" in head
    assert "document.write" in head and "styles.css" in head
    assert "src='./_vmprint_assets/" not in body
    assert "vmprint-context-canvas.js" in body
    assert "assets/pipeline.js" in body
    assert "assets/ui.js" in body


def test_vmprint_hybrid_preview_loaders_extra_scripts():
    head, body = vmprint_hybrid_preview_loaders(
        "v1", extra_body_script_rels=("assets/vmprint-client-engine-loader.js",)
    )
    assert "vmprint-client-engine-loader.js" in body
    assert head  # unchanged shape
