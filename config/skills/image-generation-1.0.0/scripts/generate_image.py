#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
#     "pillow>=10.0.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
Generate images via Gemini, Baidu Qianfan (通用图像生成), or local Stable Diffusion.

Provider selection: set provider in config.yml or use "auto" (Gemini if GEMINI_API_KEY →
Baidu if BAIDU_API_KEY → Stable Diffusion if base_url configured).
When HOMECLAW_OUTPUT_DIR is set, images are saved there with a unique filename per run.
"""

import argparse
import base64
import io
import os
import random
import string
import sys
import time
from pathlib import Path

try:
    import requests
    from PIL import Image as PILImage
except ModuleNotFoundError:
    print("Error: Missing dependency. Install: pip install requests pillow", file=sys.stderr)
    sys.exit(1)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Baidu Qianfan 通用图像生成 (single API Key): https://cloud.baidu.com/doc/qianfan-api/s/8m7u6un8a
BAIDU_QIANFAN_IMAGE = "https://qianfan.baidubce.com/v2/images/generations"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-exp"
DEFAULT_BAIDU_MODEL = "qwen-image"


def _skill_root() -> Path:
    """Skill folder containing config.yml and scripts/."""
    return Path(__file__).resolve().parent.parent


def _load_config() -> dict:
    """Load skill config from config.yml; env overrides not applied here."""
    path = _skill_root() / "config.yml"
    if not path.is_file():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _get_provider_config(cfg: dict) -> tuple[str, dict]:
    """Return (provider, merged_config). provider is one of gemini, baidu, stable_diffusion."""
    provider = (cfg.get("provider") or "auto").strip().lower()
    if provider not in ("auto", "gemini", "baidu", "stable_diffusion"):
        provider = "auto"

    # Resolve "auto": first available
    if provider == "auto":
        if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or
                (cfg.get("gemini") or {}).get("api_key")):
            provider = "gemini"
        elif os.environ.get("BAIDU_API_KEY") or (cfg.get("baidu") or {}).get("api_key"):
            provider = "baidu"
        elif os.environ.get("STABLE_DIFFUSION_URL") or ((cfg.get("stable_diffusion") or {}).get("base_url")):
            provider = "stable_diffusion"
        else:
            provider = ""

    gemini_cfg = cfg.get("gemini") or {}
    baidu_cfg = cfg.get("baidu") or {}
    sd_cfg = cfg.get("stable_diffusion") or {}

    merged = {
        "gemini": {
            "api_key": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or gemini_cfg.get("api_key") or "",
            "model": gemini_cfg.get("model") or DEFAULT_GEMINI_MODEL,
        },
        "baidu": {
            "api_key": os.environ.get("BAIDU_API_KEY") or baidu_cfg.get("api_key") or "",
            "model": baidu_cfg.get("model") or DEFAULT_BAIDU_MODEL,
            "size": baidu_cfg.get("size") or "1024x1024",
        },
        "stable_diffusion": {
            "base_url": (os.environ.get("STABLE_DIFFUSION_URL") or sd_cfg.get("base_url") or "").rstrip("/"),
            "steps": sd_cfg.get("steps", 28),
            "width": sd_cfg.get("width", 512),
            "height": sd_cfg.get("height", 512),
        },
    }
    return provider, merged


def _unique_basename() -> str:
    t = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    short = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"image-{t}-{short}"


def _is_generic_filename(name: str) -> bool:
    if not name or not name.strip():
        return True
    base = Path(name).stem.lower()
    return base in ("generated", "output", "image", "img", "out")


def _save_png(raw_bytes: bytes, output_path: Path) -> None:
    image = PILImage.open(io.BytesIO(raw_bytes))
    if image.mode == "RGBA":
        rgb = PILImage.new("RGB", image.size, (255, 255, 255))
        rgb.paste(image, mask=image.split()[3])
        rgb.save(str(output_path), "PNG")
    elif image.mode == "RGB":
        image.save(str(output_path), "PNG")
    else:
        image.convert("RGB").save(str(output_path), "PNG")


# ---------- Gemini ----------
def generate_gemini(prompt: str, resolution: str, input_image_path: str | None, api_key: str, model: str) -> bytes:
    parts = []
    if input_image_path:
        with open(input_image_path, "rb") as f:
            raw = f.read()
        mime = "image/png" if Path(input_image_path).suffix.lower() == ".png" else "image/jpeg"
        parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(raw).decode("ascii")}})
    parts.append({"text": prompt})

    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"imageSize": resolution},
        },
    }
    resp = requests.post(url, params={"key": api_key}, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(data.get("error", {}).get("message") or "No candidates in response")
    for part in (candidates[0].get("content") or {}).get("parts") or []:
        if "inlineData" in part:
            b64 = part["inlineData"].get("data")
            if b64:
                return base64.b64decode(b64)
    raise RuntimeError("No image in Gemini response")


# ---------- Baidu Qianfan 通用图像生成 ----------
def generate_baidu(prompt: str, model: str, size: str, api_key: str) -> bytes:
    """Qianfan API: POST /v2/images/generations, Bearer API Key. Returns image bytes from data[0].url."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {"model": model, "prompt": prompt, "size": size, "n": 1}
    resp = requests.post(BAIDU_QIANFAN_IMAGE, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    # API can return 200 with error in body
    if "code" in data and data.get("code") != 0:
        raise RuntimeError(data.get("message") or data.get("type") or "Baidu API error")
    items = data.get("data") or []
    if not items:
        raise RuntimeError("Baidu API: no data in response")
    url = items[0].get("url") if isinstance(items[0], dict) else None
    if not url:
        raise RuntimeError("Baidu API: no url in data[0]")
    img_resp = requests.get(url, timeout=60)
    img_resp.raise_for_status()
    return img_resp.content


# ---------- Stable Diffusion (e.g. Automatic1111) ----------
def generate_stable_diffusion(
    prompt: str,
    input_image_path: str | None,
    base_url: str,
    steps: int,
    width: int,
    height: int,
) -> bytes:
    if input_image_path:
        with open(input_image_path, "rb") as f:
            init_b64 = base64.b64encode(f.read()).decode("ascii")
        url = f"{base_url}/sdapi/v1/img2img"
        payload = {
            "prompt": prompt,
            "init_images": [init_b64],
            "steps": steps,
            "width": width,
            "height": height,
        }
    else:
        url = f"{base_url}/sdapi/v1/txt2img"
        payload = {"prompt": prompt, "steps": steps, "width": width, "height": height}
    resp = requests.post(url, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    images = data.get("images")
    if not images:
        raise RuntimeError("Stable Diffusion: no images in response")
    return base64.b64decode(images[0])


def main():
    parser = argparse.ArgumentParser(description="Generate images (Gemini / Baidu / Stable Diffusion)")
    parser.add_argument("--prompt", "-p", required=True, help="Image description/prompt")
    parser.add_argument("--filename", "-f", default="", help="Output filename (optional; unique name if generic)")
    parser.add_argument("--input-image", "-i", help="Optional input image for editing (Gemini/SD)")
    parser.add_argument("--resolution", "-r", choices=["1K", "2K", "4K"], default="1K", help="Resolution (Gemini only)")
    parser.add_argument("--api-key", "-k", help="Override API key (Gemini or Baidu)")
    parser.add_argument("--provider", choices=["gemini", "baidu", "stable_diffusion"], help="Force backend (default: from config or auto)")
    args = parser.parse_args()

    cfg = _load_config()
    provider, merged = _get_provider_config(cfg)

    if args.provider:
        provider = args.provider
    if not provider:
        print("Error: No image backend available.", file=sys.stderr)
        print("  Set GEMINI_API_KEY, or BAIDU_API_KEY, or configure stable_diffusion.base_url in config.yml (or STABLE_DIFFUSION_URL).", file=sys.stderr)
        sys.exit(1)

    # Output path
    output_dir = os.environ.get("HOMECLAW_OUTPUT_DIR")
    if output_dir:
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = None
    name_arg = (args.filename or "").strip()
    if not name_arg or _is_generic_filename(name_arg):
        base = _unique_basename()
        ext = Path(name_arg).suffix if name_arg and Path(name_arg).suffix else ".png"
        if ext.lower() not in (".png", ".jpg", ".jpeg"):
            ext = ".png"
        filename = base + ext
    else:
        filename = Path(name_arg).name
    if output_dir is not None:
        output_path = (output_dir / filename).resolve()
    else:
        output_path = Path(filename).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Using provider: {provider}")
    try:
        if provider == "gemini":
            g = merged["gemini"]
            api_key = args.api_key or g["api_key"]
            if not api_key:
                print("Error: Gemini requires api_key (config or GEMINI_API_KEY or --api-key).", file=sys.stderr)
                sys.exit(1)
            raw = generate_gemini(args.prompt, args.resolution, args.input_image, api_key, g["model"])
        elif provider == "baidu":
            b = merged["baidu"]
            api_key = args.api_key or b["api_key"]
            if not api_key:
                print("Error: Baidu requires api_key (config or BAIDU_API_KEY).", file=sys.stderr)
                sys.exit(1)
            if args.input_image:
                print("Warning: Baidu backend does not support --input-image; using text-to-image only.", file=sys.stderr)
            raw = generate_baidu(args.prompt, b["model"], b["size"], api_key)
        else:
            sd = merged["stable_diffusion"]
            if not sd["base_url"]:
                print("Error: Stable Diffusion requires base_url in config or STABLE_DIFFUSION_URL.", file=sys.stderr)
                sys.exit(1)
            raw = generate_stable_diffusion(
                args.prompt, args.input_image,
                sd["base_url"], sd["steps"], sd["width"], sd["height"],
            )
    except requests.RequestException as e:
        print(f"Error calling API: {e}", file=sys.stderr)
        if hasattr(e, "response") and e.response is not None and e.response.text:
            print(e.response.text[:500], file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        _save_png(raw, output_path)
    except Exception as e:
        print(f"Error: failed to save image: {e}", file=sys.stderr)
        sys.exit(1)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        print("Error: Image was not written or file is empty.", file=sys.stderr)
        sys.exit(1)
    source_label = {"gemini": "Gemini", "baidu": "Baidu", "stable_diffusion": "Stable Diffusion"}.get(provider, provider)
    print(f"\nImage saved: {output_path}")
    print(f"Image source: {source_label}")
    print(f"HOMECLAW_IMAGE_PATH={output_path}")
    print(f"HOMECLAW_IMAGE_SOURCE={provider}")


if __name__ == "__main__":
    main()
