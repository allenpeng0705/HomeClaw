# Core.py refactor — Phase 7: Extract plugins startup and media

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move system plugins startup logic and media (image/audio/video) helpers from `core/core.py` into `core/plugins_startup.py` and `core/media_utils.py`. Core keeps thin wrappers that delegate; all callers see unchanged behavior.

## Changes

### 1. New file: core/plugins_startup.py

- **_discover_system_plugins(core)**  
  Discovers plugins in system_plugins/ that have register.js and a server (server.js or package.json start). Returns list of `{id, cwd, start_argv, register_argv}`. Uses `Util().root_path()` and `Util().system_plugins_path`; does not use core attributes.

- **_wait_for_core_ready(core, base_url, timeout_sec=60.0, interval_sec=0.5)**  
  Polls GET `{base_url}/ready` until 200 or timeout. Uses httpx.AsyncClient. Returns bool.

- **_run_system_plugins_startup(core)**  
  Starts each discovered system plugin (subprocess), then runs register.js. Waits for Core ready first. Appends processes to `core._system_plugin_processes`. Uses `_discover_system_plugins(core)` and `_wait_for_core_ready(core, ...)`. Imports `_component_log` from core.log_helpers.

All take `core` as first argument. No import of core.core.

### 2. New file: core/media_utils.py

- **resize_image_data_url_if_needed(core, data_url, max_dimension)**  
  If max_dimension > 0 and Pillow is available, resizes image so max(w,h) <= max_dimension and returns data URL; else returns original. No core attributes used in body.

- **image_item_to_data_url(core, item)**  
  Converts image item (data URL, file path, or raw base64) to a data URL for vision API. Uses `Util().get_core_metadata().completion.image_max_dimension` and calls `resize_image_data_url_if_needed(core, data_url, max_dim)`.

- **audio_item_to_base64_and_format(core, item)**  
  Converts audio item (data URL or file path) to `(base64_string, format)` for input_audio. Format: wav, mp3, ogg, webm.

- **video_item_to_base64_and_format(core, item)**  
  Converts video item (data URL or file path) to `(base64_string, format)` for input_video. Format: mp4, webm.

All take `core` as first argument. No import of core.core.

### 3. core/core.py

- **Imports:**  
  - `from core.plugins_startup import _discover_system_plugins as _discover_system_plugins_fn, _wait_for_core_ready as _wait_for_core_ready_fn, _run_system_plugins_startup as _run_system_plugins_startup_fn`  
  - `from core.media_utils import resize_image_data_url_if_needed as _resize_image_data_url_if_needed_fn, image_item_to_data_url as _image_item_to_data_url_fn, audio_item_to_base64_and_format as _audio_item_to_base64_and_format_fn, video_item_to_base64_and_format as _video_item_to_base64_and_format_fn`

- **Methods:**  
  - `_discover_system_plugins(self)` → `return _discover_system_plugins_fn(self)`  
  - `_wait_for_core_ready(self, base_url, ...)` → `return await _wait_for_core_ready_fn(self, base_url, ...)`  
  - `_run_system_plugins_startup(self)` → `await _run_system_plugins_startup_fn(self)`  
  - `_resize_image_data_url_if_needed(self, data_url, max_dimension)` → `return _resize_image_data_url_if_needed_fn(self, data_url, max_dimension)`  
  - `_image_item_to_data_url(self, item)` → `return _image_item_to_data_url_fn(self, item)`  
  - `_audio_item_to_base64_and_format(self, item)` → `return _audio_item_to_base64_and_format_fn(self, item)`  
  - `_video_item_to_base64_and_format(self, item)` → `return _video_item_to_base64_and_format_fn(self, item)`

## Logic and stability

- **Logic:** Bodies moved verbatim; only `self` → `core` where needed. `_run_system_plugins_startup` uses `core._system_plugin_processes`; no other core attributes in plugins_startup. Media helpers use Util() and core only for config (image_max_dimension) or delegation (resize).
- **Stability:** Same error handling and fallbacks. No new dependencies on core.core.
- **Platforms:** macOS, Windows, Linux (plugins_startup uses asyncio.create_subprocess_exec and 127.0.0.1 for readiness on 0.0.0.0; media_utils uses os.path and PIL when available).

## Testing

- **Unit:**  
  - `test_plugins_startup_module`: core.plugins_startup exposes the three functions; _wait_for_core_ready and _run_system_plugins_startup are async.  
  - `test_media_utils_module`: core.media_utils exposes the four functions.  
  - `test_media_utils_resize_image_no_change`: resize returns original when max_dimension <= 0 or empty input.
- **Manual:** Start Core (system plugins start in background if configured); upload image/audio/video and confirm conversion and response as before.

## Summary

Phase 7 extracts plugins startup (~150 lines) and media helpers (~150 lines) into dedicated modules. Core.run() and callers of the media helpers still use the same Core API; implementation is delegated to plugins_startup and media_utils.
