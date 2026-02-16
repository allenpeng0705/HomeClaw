# llama.cpp server binaries for HomeClaw

HomeClaw runs the **llama.cpp** HTTP server as the local LLM engine. Put the matching release build in the correct subfolder for your platform. The core will auto-detect and start the right binary.

## Folder layout

| Folder       | Platform        | Use case              | Binary          |
|-------------|-----------------|------------------------|-----------------|
| `mac/`      | macOS (Arm/Intel) | Apple Silicon or Intel | `llama-server`  |
| `win_cpu/`  | Windows         | CPU only               | `llama-server.exe` |
| `win_cuda/` | Windows         | NVIDIA GPU (CUDA)      | `llama-server.exe` |
| `linux_cpu/`| Linux           | CPU only               | `llama-server`  |
| `linux_cuda/`| Linux          | NVIDIA GPU (CUDA)     | `llama-server`  |

## How to get the binaries

1. Go to [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases).
2. Download the **server** build for your OS (e.g. `llama-b...-bin-win-cuda-cu12.x.x.zip` for Windows CUDA).
3. Unzip and copy the **llama-server** (or **llama-server.exe** on Windows) into the matching folder above.  
   - Example (Windows CUDA): put `llama-server.exe` inside `llama.cpp-master/win_cuda/`.
   - Example (macOS): put `llama-server` inside `llama.cpp-master/mac/`.

## Auto-detection

- **macOS**: always uses `mac/`.
- **Windows**: uses `win_cuda/` if CUDA is available, otherwise `win_cpu/`.
- **Linux**: uses `linux_cuda/` if CUDA is available, otherwise `linux_cpu/`.

If the expected folder or binary is missing, the core will log an error and will not start the local LLM server.
