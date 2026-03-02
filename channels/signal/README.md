# Signal channel

HTTP webhook that a **Signal bridge** calls (e.g. signal-cli with a small script). The bridge runs on your machine, receives Signal messages, POSTs to this channel, and sends our response back via Signal. Core connection from **channels/.env** only.

## How it works

1. You run this channel: `python -m channels.run signal` (listens on port 8011 by default).
2. You run a Signal bridge (e.g. signal-cli) that:
   - On each incoming Signal message: POST to `http://127.0.0.1:8011/message` with `{ "user_id": "signal_<number_or_id>", "text": "<message>", "user_name": "..." }`.
   - Takes the response `{ "text": "..." }` and sends it back via Signal.
3. Add `signal_<id>` to `config/user.yml` under `im` for allowed users.

**Do you still need a script to interact with signal-cli and this channel?**  
Yes. signal-cli and the Signal channel do not talk to each other by themselves. You need either:
- **Our bridge script** (recommended): run `python channels/signal/scripts/bridge-signal-cli-to-channel.py` after starting the channel and signal-cli daemon with `--http`. See [Bridge script](#bridge-script) below.
- **signal-cli-rest-api** (Docker) and your own webhook logic, or another script that POSTs to `/message` and sends replies via signal-cli.

## Images and files

The bridge can send the same payload as Companion: in addition to `user_id`, `text`, `user_name`, include optional `images`, `videos`, `audios`, or `files` (data URLs or paths). The channel forwards them to Core `/inbound`. Core stores **images** in the user's **images** folder when the model doesn't support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.

## Run

```bash
python -m channels.run signal
```

Set `SIGNAL_CHANNEL_HOST`, `SIGNAL_CHANNEL_PORT` in `channels/.env` if needed. The bridge must be able to reach this server (localhost is fine if the bridge runs on the same machine).

## How to use signal-cli

**signal-cli** lets you send and receive Signal messages from the command line and (with a small bridge) connect Signal to this HomeClaw channel.

| Step | What to do |
|------|------------|
| **1. Get signal-cli** | Use a [pre-built release](https://github.com/AsamK/signal-cli/releases) (Linux/macOS/Windows if available), or build from source: **Windows** → `.\channels\signal\scripts\build-signal-cli-windows.ps1` (needs JDK 17+); **Mac** → `./channels/signal/scripts/build-signal-cli-mac.sh` (needs JDK 17+). |
| **2. One-time setup** | **Register** a new number: `signal-cli -u +1234567890 register`, then `signal-cli -u +1234567890 verify <code>`. Or **link** an existing device: see [Linking (Provisioning)](https://github.com/AsamK/signal-cli/wiki/Linking-other-devices-%28Provisioning%29). |
| **3. Send and receive** | **Send:** `signal-cli -u +1234567890 send -m "Hello" +0987654321` — **Receive (once):** `signal-cli -u +1234567890 receive`. On Windows use `signal-cli.bat` instead of `signal-cli`. |
| **4. Connect to HomeClaw** | Run the channel (`python -m channels.run signal`), then signal-cli daemon (`signal-cli -u +NUMBER daemon --http=127.0.0.1:8080`), then **run the bridge**: `python channels/signal/scripts/bridge-signal-cli-to-channel.py`. Alternatively use [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) or your own script. Add `signal_<id>` to `config/user.yml` under `im` for allowed users. |

More detail: **Register / Send & receive / Daemon & bridge** are in the sections below.

## Using signal-cli (detail)

**signal-cli** is a command-line and daemon client for Signal. Use it as the bridge that receives Signal messages and sends replies. Official docs: [signal-cli GitHub](https://github.com/AsamK/signal-cli) and [Quickstart](https://github.com/AsamK/signal-cli/wiki/Quickstart).

### Platform support

signal-cli is **primarily supported on Linux**. The project’s main binary distribution and docs target Linux; Windows and macOS support may be limited or require extra steps (e.g. building from source or using community builds). If you’re on **Windows or macOS**, consider:

- **Linux / WSL (Windows):** Run signal-cli inside WSL2 so it runs in a Linux environment.
- **Docker:** Use a signal-cli Docker image (see [Binary distributions](https://github.com/AsamK/signal-cli/wiki/Binary-distributions)) so the bridge runs in a Linux container on any host.
- **signal-cli-rest-api:** Run [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) in Docker; it exposes signal-cli as a REST API and can run on Windows/macOS via Docker Desktop.

### Build and run on Windows (no Docker)

You can run signal-cli natively on Windows in two ways:

**Option 1: Pre-built release (if a Windows build is published)**  
Check the [signal-cli releases](https://github.com/AsamK/signal-cli/releases) page for a Windows artifact (e.g. a zip or an asset that includes Windows binaries). The project documents that native libs are bundled for x86_64 Linux, Windows, and macOS; the exact asset name may vary by release. You need a **JRE 25** (or the version stated in that release) installed and `java` on your PATH. Unpack the archive and run from the `bin` folder, e.g. `signal-cli.bat` or `signal-cli` in PowerShell.

**Option 2: Build from source on Windows**  
Requires: **JDK 17+** (Gradle); **JDK 25** recommended for signal-cli runtime (see [signal-cli README](https://github.com/AsamK/signal-cli)). **Git for Windows**.

**One-script Windows build (from this repo):**  
Install [Eclipse Temurin JDK 17+](https://adoptium.net/) (or another JDK 17+), set `JAVA_HOME` to its installation path, then run:
```powershell
cd D:\path\to\HomeClaw
.\channels\signal\scripts\build-signal-cli-windows.ps1
```
If PowerShell says the script "cannot be loaded" or "is not digitally signed", run once with: `powershell -ExecutionPolicy Bypass -File .\channels\signal\scripts\build-signal-cli-windows.ps1`, or allow local scripts: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.  
The script clones signal-cli (or uses an existing clone at `..\signal-cli`), runs `gradlew.bat installDist`, and optionally zips the result. If you only have Java 8, the script exits with instructions to install JDK 17+ and set `JAVA_HOME`.

**Manual clone and build:**
1. Clone and build:
   ```powershell
   git clone https://github.com/AsamK/signal-cli.git
   cd signal-cli
   .\gradlew.bat installDist
   ```
2. The built binary is under `build\install\signal-cli\bin\`. Run:
   ```powershell
   .\build\install\signal-cli\bin\signal-cli.bat -u +1234567890 receive
   ```
   (Use `signal-cli.bat` for all commands; replace `+1234567890` with your number.)

**Native library (libsignal) on Windows:**  
signal-cli depends on a native library (libsignal-client). Official releases bundle it for Windows. When **building from source**, the Gradle build may not include the Windows native lib; if you get errors about a missing DLL or native library, see [Provide native lib for libsignal](https://github.com/AsamK/signal-cli/wiki/Provide-native-lib-for-libsignal). Community-built Windows artefacts (e.g. `libsignal_jni_dll*_windows_amd64-ucrt.gz`) are listed there; you can use one that matches your signal-cli version and place the `.dll` on the Java library path or bundle it as described in the wiki.

### Building from source to produce Windows and macOS binaries

To **produce** a signal-cli build for Windows or macOS (not just run it), you need a native library (libsignal-client) for that OS. The practical approach is to build **on each target OS** (or use community pre-built native libs and build the Java part).

**Common requirements (all platforms)**  
- **JDK 25** (or the version required by [signal-cli](https://github.com/AsamK/signal-cli))  
- **Git**  
- For building **libsignal-client** yourself: **Rust**, and (on Linux/macOS) the tools used by `build_jni.sh` (see [libsignal](https://github.com/signalapp/libsignal))

**Producing a Windows binary**  
1. On a **Windows** machine: install JDK 25 and Git, then clone and build:
   ```powershell
   git clone https://github.com/AsamK/signal-cli.git
   cd signal-cli
   .\gradlew.bat installDist
   ```
2. If the build fails due to a missing native library, use a pre-built Windows lib from [Provide native lib for libsignal](https://github.com/AsamK/signal-cli/wiki/Provide-native-lib-for-libsignal) (e.g. `libsignal_jni_dll*_windows_amd64-ucrt.gz`). Extract the `.dll`, match the libsignal version to your signal-cli, and either put the DLL on the Java library path or bundle it as described in the wiki. Then run `.\gradlew.bat installDist` again (or pass `-Plibsignal_client_path=...` if you built a custom libsignal jar).  
3. The Windows build output is under `build\install\signal-cli\`. Distribute that folder (or zip it); users need a JRE and to run `bin\signal-cli.bat`.

**Producing a macOS binary**  
**One-script Mac build (from this repo):** On a Mac, install JDK 17+ (e.g. `brew install openjdk@21` or [Adoptium](https://adoptium.net/)), set `JAVA_HOME` if needed, then run:
```bash
cd /path/to/HomeClaw
chmod +x channels/signal/scripts/build-signal-cli-mac.sh
./channels/signal/scripts/build-signal-cli-mac.sh
```
The script clones signal-cli (or uses an existing clone at `../signal-cli`), runs `./gradlew installDist`, and creates `signal-cli-mac.tar.gz` in the build directory.

**Manual:** On a **macOS** machine: install JDK 17+ and Git, then clone and build:
   ```bash
   git clone https://github.com/AsamK/signal-cli.git
   cd signal-cli
   ./gradlew installDist
   ```
If the build fails due to a missing native library, build **libsignal-client** on the Mac: clone [libsignal](https://github.com/signalapp/libsignal), determine the version required by your signal-cli (see the wiki), then in the libsignal repo run `cd java && ./build_jni.sh desktop`. Use the produced `.dylib` (and optionally the Java jar) with signal-cli’s Gradle build via `-Plibsignal_client_path=...` or by placing the library on the Java library path.  
The macOS build output is under `build/install/signal-cli/`. Users need a JRE and run `bin/signal-cli`.

**Summary**  
- **Windows**: Build on Windows; use Gradle’s output or a community Windows native lib if the default build doesn’t include it.  
- **macOS**: Build on macOS; use Gradle’s output or build libsignal-client on the Mac and point signal-cli at it.  
- **Cross-compiling** from one OS to another (e.g. Linux → Windows) is not documented in the official signal-cli/wiki flow; building on each target OS is the supported approach.

### Prerequisites (Linux)

- **Java 21+** (JRE). Example: `sudo apt install openjdk-21-jre` (Ubuntu/Debian), or install from [Adoptium](https://adoptium.net/).

### Install (Linux)

1. Download a release from [signal-cli releases](https://github.com/AsamK/signal-cli/releases) and unpack to a folder (e.g. `~/signal-cli`).
2. Use the `bin` subfolder: `cd ~/signal-cli/bin`.

### Register (one-time)

Replace `+1234567890` with your phone number (with country code).

```bash
# Register (you get an SMS with a code)
./signal-cli -u +1234567890 register

# Verify with the code from SMS
./signal-cli -u +1234567890 verify 123456
```

Alternatively, **link** an existing Signal device: see [Linking other devices (Provisioning)](https://github.com/AsamK/signal-cli/wiki/Linking-other-devices-%28Provisioning%29).

### Send and receive (CLI)

```bash
# Send a message
./signal-cli -u +1234567890 send -m "Hello" +0987654321

# Receive once (one-shot; exits after processing)
./signal-cli -u +1234567890 receive
```

### Bridge to this channel (daemon + script)

To connect Signal to HomeClaw automatically:

1. Run the **Signal channel**: `python -m channels.run signal` (listens on 8011).
2. Run **signal-cli** in **daemon** mode so it can receive messages and you can send replies via JSON-RPC or CLI:
   - **Daemon (HTTP)** — **use this for our bridge script:**  
     `./signal-cli -u +1234567890 daemon --http=127.0.0.1:8080` (Windows: `.\signal-cli.bat ...`). The bridge connects to the HTTP API (`/api/v1/events`, `/api/v1/rpc`).
   - **Daemon (TCP socket):**  
     `./signal-cli -u +1234567890 daemon --socket` — for other clients that speak JSON-RPC over a socket; the bridge script does not use this.  
     Then use the HTTP API (see [JSON-RPC service](https://github.com/AsamK/signal-cli/wiki/JSON-RPC-service)).
3. Use a **small script** that:
   - Subscribes to incoming messages (e.g. via daemon’s JSON-RPC/SSE or by polling `receive`), and
   - For each message: POST to `http://127.0.0.1:8011/message` with `{"user_id": "signal_<sender_number>", "text": "<message>", "user_name": "..."}`, then
   - Sends the response `text` (and optional `images`) back with `signal-cli send` (or the daemon’s send API).

Example (conceptual) for a single received message:

```bash
# After receiving a message from +0987654321 with body "Hello"
curl -s -X POST http://127.0.0.1:8011/message \
  -H "Content-Type: application/json" \
  -d '{"user_id":"signal_0987654321","text":"Hello","user_name":"Alice"}'
# Returns e.g. {"text":"Hi! How can I help?"}

# Send that reply back via Signal
./signal-cli -u +1234567890 send -m "Hi! How can I help?" +0987654321
```

For a full bridge, wire the daemon’s receive events (e.g. SSE from `GET /api/v1/events` when using `--http`) to the above POST, then send the returned `text` with `signal-cli send`. You can use **signal-cli-rest-api** (Docker REST wrapper) or your own script against the JSON-RPC/HTTP API.

### Bridge script

This repo includes a small bridge that connects signal-cli's daemon (HTTP) to this channel so you don't have to write your own.

1. **Start the Signal channel** (from the repo root): `python -m channels.run signal`
2. **Start signal-cli in daemon mode with HTTP** (use your number and a port, e.g. 8080): `signal-cli -u +1234567890 daemon --http=127.0.0.1:8080`
3. **Run the bridge** (from the repo root; needs `httpx`): `python channels/signal/scripts/bridge-signal-cli-to-channel.py`

The bridge subscribes to the daemon's SSE stream, POSTs each incoming message to the channel, and sends the reply back via signal-cli's JSON-RPC `send`. Optional env: `SIGNAL_CLI_DAEMON_HTTP` (default `http://127.0.0.1:8080`), `CHANNEL_SIGNAL_URL` (default `http://127.0.0.1:8011/message`). Add allowed users to `config/user.yml` under `im` as `signal_<number>`.

**"Cannot reach signal-cli daemon":** The bridge only works when the **signal-cli daemon is already running with HTTP**. In a **separate terminal** (and keep it open):

- **If you use a release build:** go to the folder where you unpacked signal-cli (e.g. `signal-cli-0.14.0\bin` on Windows), then run:
  - Windows: `.\signal-cli.bat -u +YOUR_NUMBER daemon --http=127.0.0.1:8080`
  - Linux/macOS: `./signal-cli -u +YOUR_NUMBER daemon --http=127.0.0.1:8080`
- **If you built from source (Windows):** e.g. `.\build\install\signal-cli\bin\signal-cli.bat -u +YOUR_NUMBER daemon --http=127.0.0.1:8080` (run from the signal-cli repo directory).

Replace `+YOUR_NUMBER` with your Signal number (with country code). Leave this terminal running. Then in another terminal run the bridge again. To confirm the daemon is up, open in a browser or run: `curl http://127.0.0.1:8080/api/v1/check` (should return 200).

**"SSE failed: HTTP 404":** Your signal-cli build may not include the HTTP daemon. Use a [recent release](https://github.com/AsamK/signal-cli/releases) or a full build from source; some minimal or older builds only expose socket mode, not HTTP.

**Bridge runs but doesn't get messages:** (1) Ensure the daemon is started with `--receive-mode=on-start` (default) so it receives messages; if you use `--receive-mode=manual`, you must call `subscribeReceive` via JSON-RPC first. (2) Send a **new** Signal message to the number the daemon is using (from another phone or Signal app); the bridge only sees messages that arrive **after** it connected to the SSE stream. (3) The bridge supports the HTTP SSE format: signal-cli sends `event: receive` and `data: {"account":"+...", "envelope":{...}}` (not the JSON-RPC notification shape). If you still see no messages, run with debug: `set BRIDGE_DEBUG=1` (Windows) or `BRIDGE_DEBUG=1` (Linux/macOS), then run the bridge again and check which events are received or skipped.
