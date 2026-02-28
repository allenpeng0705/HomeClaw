"""
Platform detection and path resolution for llama.cpp server binaries.
HomeClaw looks for llama-server in this order:
  1. llama.cpp-master/<platform>/ under project root (see llama.cpp-master/README.md)
  2. PATH (e.g. from winget install llama.cpp, brew install llama.cpp, nix, MacPorts)
     See https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md
"""
import platform
import shutil
from pathlib import Path
from typing import Optional, Tuple

# Optional: use torch to detect CUDA; fallback to env or nvidia-smi if needed
def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# Supported subfolder names (user puts the corresponding llama.cpp release in each)
FOLDER_MAC = "mac"
FOLDER_WIN_CPU = "win_cpu"
FOLDER_WIN_CUDA = "win_cuda"
FOLDER_LINUX_CPU = "linux_cpu"
FOLDER_LINUX_CUDA = "linux_cuda"

ALL_FOLDERS = (FOLDER_MAC, FOLDER_WIN_CPU, FOLDER_WIN_CUDA, FOLDER_LINUX_CPU, FOLDER_LINUX_CUDA)

# Executable name per platform (Windows uses .exe)
EXE_WINDOWS = "llama-server.exe"
EXE_UNIX = "llama-server"


def get_platform_folder() -> Optional[str]:
    """
    Return the subfolder name for the current platform and device (CPU vs CUDA).
    Returns one of: mac, win_cpu, win_cuda, linux_cpu, linux_cuda, or None if unknown.
    """
    system = platform.system()
    if system == "Darwin":
        return FOLDER_MAC
    if system == "Windows":
        return FOLDER_WIN_CUDA if _cuda_available() else FOLDER_WIN_CPU
    if system == "Linux":
        return FOLDER_LINUX_CUDA if _cuda_available() else FOLDER_LINUX_CPU
    return None


def get_llama_server_executable(root_path: str, subfolder: Optional[str] = None) -> Optional[Path]:
    """
    Resolve the full path to the llama-server executable.

    :param root_path: Path to the parent folder containing platform subfolders (e.g. llama.cpp-master).
    :param subfolder: Override subfolder (mac, win_cpu, etc.). If None, uses get_platform_folder().
    :return: Path to llama-server (or llama-server.exe), or None if not found.
    """
    root = Path(root_path)
    if not root.is_dir():
        return None
    folder = subfolder or get_platform_folder()
    if not folder:
        return None
    is_windows = platform.system() == "Windows"
    exe_name = EXE_WINDOWS if is_windows else EXE_UNIX
    exe_path = root / folder / exe_name
    if exe_path.is_file():
        return exe_path
    return None


def get_llama_cpp_root(project_root: str) -> Path:
    """Return the default llama.cpp root directory under the project (e.g. project_root/llama.cpp-master)."""
    return Path(project_root) / "llama.cpp-master"


def resolve_llama_server(project_root: str, subfolder_override: Optional[str] = None) -> Tuple[Optional[Path], Optional[str]]:
    """
    Resolve the llama-server executable for the current platform.
    First checks llama.cpp-master/<platform>/; then falls back to PATH (winget, brew, nix, etc.).

    :param project_root: HomeClaw project root directory.
    :param subfolder_override: Optional subfolder name to use instead of auto-detection.
    :return: (path_to_executable, subfolder_name) or (None, None) if not found.
    """
    root = get_llama_cpp_root(project_root)
    folder = subfolder_override or get_platform_folder()
    if folder:
        exe = get_llama_server_executable(str(root), folder)
        if exe is not None:
            return exe, folder
    # Fallback: use llama-server from PATH (e.g. winget install llama.cpp, brew install llama.cpp)
    exe_name = EXE_WINDOWS if platform.system() == "Windows" else EXE_UNIX
    path_exe = shutil.which(exe_name)
    if path_exe:
        return Path(path_exe), "path"
    return None, None
