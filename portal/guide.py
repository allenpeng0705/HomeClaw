"""
Guide to install: lightweight checks for onboarding (Python, venv, Node, config, llama.cpp, doctor).
No dependency on base.util or core; doctor runs via subprocess.
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from portal.config import ROOT_DIR

# llama.cpp platform subfolders (must match llm/llama_cpp_platform.py)
_LLAMA_FOLDERS = ("mac", "win_cpu", "win_cuda", "linux_cpu", "linux_cuda")
_LLAMA_EXE_WIN = "llama-server.exe"
_LLAMA_EXE_UNIX = "llama-server"

# Optional: load core to resolve model_path
def _get_models_dir() -> Path:
    """Resolve models directory from core.yml model_path (relative to project root)."""
    try:
        from portal import config_api
        core_data = config_api.load_config("core")
        raw = (core_data or {}).get("model_path") or ""
        raw = (raw or "models").strip().rstrip("/\\")
        if not raw or raw == ".":
            return Path(ROOT_DIR) / "models"
        if os.path.isabs(raw):
            return Path(raw)
        parts = Path(raw).parts
        if parts[0] == "..":
            base = Path(ROOT_DIR).parent
            for p in parts[1:]:
                base = base / p
            return base
        return Path(ROOT_DIR) / raw
    except Exception:
        return Path(ROOT_DIR) / "models"

# Pip mirror for users in China (faster than default PyPI)
_PIP_CHINA_HINT = " In China, use a mirror: pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"


def run_guide_checks() -> List[Dict[str, Any]]:
    """
    Run step-by-step checks. Returns list of { "id", "ok", "message", "hint" }.
    Steps: python, venv, config_dir, config_files, (doctor is separate).
    """
    steps = []

    # 1. Python (system or virtual environment; venv is optional)
    ver = sys.version_info
    version_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    in_venv = getattr(sys, "prefix", None) != getattr(sys, "base_prefix", None) or os.environ.get("VIRTUAL_ENV")
    env_label = "virtual environment" if in_venv else "system"
    if ver.major >= 3 and ver.minor >= 9:
        steps.append({
            "id": "python",
            "ok": True,
            "message": f"{version_str} ({env_label})",
            "hint": "Python 3.9+ is required. You can use system Python or a virtual environment (venv/conda); venv is optional. Run: pip install -r requirements.txt." + _PIP_CHINA_HINT + " To use a venv: python -m venv .venv then activate it; or conda: conda create -n homeclaw python=3.11, conda activate homeclaw. Then pip install -r requirements.txt",
        })
    else:
        steps.append({
            "id": "python",
            "ok": False,
            "message": version_str,
            "hint": "Install Python 3.9 or newer (system or in a virtual environment). From python.org or your package manager; or use conda/venv. Then run pip install -r requirements.txt." + _PIP_CHINA_HINT,
        })

    # 2. Dependencies (pip install -r requirements.txt is required)
    deps_ok = False
    deps_msg = "not checked"
    try:
        import fastapi  # noqa: F401
        import ruamel.yaml  # noqa: F401
        deps_ok = True
        deps_msg = "Core dependencies installed"
    except ImportError as e:
        deps_msg = "Missing: " + (str(e).split()[-1] if " " in str(e) else str(e))
    steps.append({
        "id": "dependencies",
        "ok": deps_ok,
        "message": deps_msg,
        "hint": "Run: pip install -r requirements.txt (required). Use the same Python you use to run the Portal/Core." + _PIP_CHINA_HINT,
    })

    # 3. Node.js (required for browser plugin)
    node_ok = False
    node_msg = "not found"
    try:
        which_node = shutil.which("node") if shutil else None
        if which_node:
            proc = subprocess.run(
                [which_node, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout:
                node_msg = proc.stdout.strip().lstrip("v")
                node_ok = True
            else:
                node_msg = "node found but --version failed"
        else:
            node_msg = "not in PATH"
    except Exception as e:
        node_msg = str(e)
    steps.append({
        "id": "node",
        "ok": node_ok,
        "message": node_msg,
        "hint": "Node.js is required for the browser plugin. Install from nodejs.org or your package manager (e.g. brew install node, apt install nodejs).",
    })

    # 3b. VMPrint (optional but recommended for high-quality markdown_to_pdf)
    vmprint = run_vmprint_status()
    steps.append({
        "id": "vmprint",
        "ok": bool(vmprint.get("ok")),
        "message": str(vmprint.get("message") or "unknown"),
        "hint": (
            "VMPrint improves Markdown->PDF quality and supports profiles (academic/manuscript/screenplay/literature). "
            "Install/repair by running install.sh / install.ps1 / install.bat. "
            "Then click 'Run VMPrint smoke test' in this step."
        ),
    })

    # 4. llama.cpp binary: llama.cpp-master/<platform>/ or on PATH (winget, brew, nix, MacPorts)
    llama_root = Path(ROOT_DIR) / "llama.cpp-master"
    system = platform.system()
    is_windows = system == "Windows"
    exe_name = _LLAMA_EXE_WIN if is_windows else _LLAMA_EXE_UNIX
    if system == "Darwin":
        platform_folder = "mac"
    elif system == "Windows":
        platform_folder = "win_cpu"
    elif system == "Linux":
        platform_folder = "linux_cpu"
    else:
        platform_folder = None
    llama_ok = False
    llama_msg = "llama.cpp-master not found"
    if llama_root.is_dir():
        if platform_folder and (llama_root / platform_folder / exe_name).is_file():
            llama_ok = True
            llama_msg = f"llama-server found in llama.cpp-master/{platform_folder}/"
        else:
            for folder in _LLAMA_FOLDERS:
                if (llama_root / folder / (_LLAMA_EXE_WIN if folder.startswith("win_") else _LLAMA_EXE_UNIX)).is_file():
                    llama_ok = True
                    llama_msg = f"llama-server found in llama.cpp-master/{folder}/"
                    break
            if not llama_ok:
                folder_hint = platform_folder or "mac, win_cpu, win_cuda, linux_cpu, linux_cuda"
                llama_msg = f"Binary not found in llama.cpp-master/{folder_hint}/"
    if not llama_ok and shutil.which(exe_name):
        llama_ok = True
        llama_msg = "llama-server found on PATH (e.g. winget/brew/nix)"
    steps.append({
        "id": "llama_cpp",
        "ok": llama_ok,
        "message": llama_msg,
        "hint": (
            "Two ways to install llama.cpp (we use the llama-server binary for local GGUF models):\n\n"
            "Method A — Copy binary into project: Download the executable for your platform from "
            "https://github.com/ggml-org/llama.cpp/releases (e.g. llama-b...-bin-macos-arm64.tar.gz for Mac Apple Silicon, "
            "llama-b...-bin-win-cuda-12.4-x64.zip for Windows CUDA). Unzip and copy llama-server "
            "(or llama-server.exe on Windows) into llama.cpp-master/<platform>/ in this repo "
            "(mac, win_cpu, win_cuda, linux_cpu, or linux_cuda). See llama.cpp-master/README.md for folder layout.\n\n"
            "Method B — Install via package manager (llama-server on PATH):\n"
            "• Windows: winget install llama.cpp\n"
            "• Mac / Linux: brew install llama.cpp\n"
            "• Mac (MacPorts): sudo port install llama.cpp\n"
            "• Mac / Linux (Nix): nix profile install nixpkgs#llama-cpp\n\n"
            "Official install guide: https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md"
        ),
    })

    # 5. GGUF models folder (model_path from core.yml)
    models_dir = _get_models_dir()
    models_exists = models_dir.is_dir() if models_dir else False
    gguf_count = 0
    if models_exists and models_dir:
        try:
            gguf_count = sum(1 for _ in models_dir.rglob("*.gguf"))
        except Exception:
            pass
    _gguf_download_hint = (
        "Download GGUF models from Hugging Face (huggingface.co). "
        "In China you can use ModelScope (modelscope.cn) or HF Mirror (https://hf-mirror.com/). "
        "Put .gguf files in the models folder and add entries in config/llm.yml under local_models with path set to the filename (e.g. model.gguf)."
    )
    if models_exists and gguf_count > 0:
        steps.append({
            "id": "gguf_models",
            "ok": True,
            "message": f"{models_dir} ({gguf_count} .gguf file(s))",
            "hint": "Local GGUF models are used by llama.cpp. To add more: " + _gguf_download_hint,
        })
    elif models_exists:
        steps.append({
            "id": "gguf_models",
            "ok": False,
            "message": f"{models_dir} (no .gguf files yet)",
            "hint": _gguf_download_hint,
        })
    else:
        steps.append({
            "id": "gguf_models",
            "ok": False,
            "message": f"Models folder not found: {models_dir}",
            "hint": "Create the models folder (see model_path in config/core.yml; default is project_root/models or ../models). " + _gguf_download_hint,
        })

    return steps


def run_doctor_report() -> Dict[str, Any]:
    """
    Run `python -m main doctor` in project root; parse stdout for OK/Issue lines.
    Returns { "ok": [...], "issues": [...], "output": "raw stdout", "error": "..." if subprocess failed }.
    """
    result = {"ok": [], "issues": [], "output": ""}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "main", "doctor"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        result["output"] = (proc.stdout or "") + (proc.stderr or "")
        for line in result["output"].splitlines():
            s = line.strip()
            if s.startswith("OK:"):
                result["ok"].append(s[3:].strip())
            elif s.startswith("Issue:"):
                result["issues"].append(s[6:].strip())
        if proc.returncode != 0 and not result["issues"]:
            result["issues"].append("Doctor command exited with code " + str(proc.returncode))
    except subprocess.TimeoutExpired:
        result["error"] = "Doctor timed out."
    except FileNotFoundError:
        result["error"] = "Could not run python -m main doctor (main not found)."
    except Exception as e:
        result["error"] = str(e)
    return result


def run_vmprint_status() -> Dict[str, Any]:
    """Check VMPrint install/build status. Returns {'ok': bool, 'message': str, ...}."""
    vmprint_dir = Path(ROOT_DIR) / "tools" / "vmprint"
    alt_dir = Path(ROOT_DIR) / "tools" / "vm_print"
    if not vmprint_dir.exists() and alt_dir.exists():
        vmprint_dir = alt_dir
    if not vmprint_dir.exists():
        return {"ok": False, "message": "Not installed (tools/vmprint not found)."}
    if not (vmprint_dir / "draft2final").is_dir():
        return {"ok": False, "message": "Invalid VMPrint folder (draft2final missing).", "path": str(vmprint_dir)}
    if not (vmprint_dir / "node_modules").is_dir():
        return {"ok": False, "message": "Dependencies missing (node_modules not found).", "path": str(vmprint_dir)}
    cli_js = vmprint_dir / "draft2final" / "dist" / "cli.js"
    if not cli_js.is_file():
        return {
            "ok": False,
            "message": "draft2final CLI not built (draft2final/dist/cli.js missing).",
            "path": str(vmprint_dir),
        }
    node_path = shutil.which("node")
    if not node_path:
        return {"ok": False, "message": "Node.js not found in PATH for Portal/Core process.", "path": str(vmprint_dir)}
    return {"ok": True, "message": f"Ready ({vmprint_dir})", "path": str(vmprint_dir), "node": node_path}


def run_vmprint_smoke_test() -> Dict[str, Any]:
    """Run a tiny VMPrint render smoke test. Returns parsed status and output path."""
    status = run_vmprint_status()
    if not status.get("ok"):
        return {"ok": False, "error": status.get("message", "VMPrint not ready"), "status": status}
    vmprint_dir = Path(status.get("path"))
    cli_js = vmprint_dir / "draft2final" / "dist" / "cli.js"
    try:
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "smoke.md"
            outp = Path(td) / "smoke.pdf"
            inp.write_text("# VMPrint smoke test\n\nThis is a quick render check.\n", encoding="utf-8")
            # Prefer --out (current upstream docs), keep --output fallback.
            cmd1 = ["node", str(cli_js), str(inp), "--as", "academic", "--out", str(outp)]
            r = subprocess.run(cmd1, cwd=str(vmprint_dir), capture_output=True, text=True, timeout=45)
            if r.returncode != 0 or not outp.exists():
                cmd2 = ["node", str(cli_js), str(inp), "--as", "academic", "--output", str(outp)]
                r = subprocess.run(cmd2, cwd=str(vmprint_dir), capture_output=True, text=True, timeout=45)
            if r.returncode == 0 and outp.exists() and outp.stat().st_size > 0:
                return {
                    "ok": True,
                    "message": f"Smoke test passed ({outp.stat().st_size} bytes PDF).",
                    "stdout": (r.stdout or "").strip()[:1000],
                }
            err = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()[:2000]
            return {"ok": False, "error": err or f"Render failed (exit {r.returncode})."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
