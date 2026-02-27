# Test Companion app on iPhone via Cloudflare Tunnel

This guide gives **detailed steps** to run the HomeClaw Companion app on your **iPhone** and connect it to HomeClaw Core over the internet using **Cloudflare Tunnel**. No port forwarding on your router; you get a public HTTPS URL that forwards to Core.

---

## Prerequisites

- **Machine A (e.g. Mac or PC at home):** HomeClaw Core runs here. You will install **cloudflared** and run a tunnel from this machine.
- **iPhone:** You will run the Companion app and set the **Core URL** to the tunnel URL.
- **Cloudflare account:** Free. Sign up at [dash.cloudflare.com](https://dash.cloudflare.com/) if you don’t have one (optional for quick tunnels; required for named tunnels with a stable hostname).

---

## Step 1: Run HomeClaw Core on the “server” machine

On the machine that will run Core (e.g. your Mac at home):

1. **Clone and install** (if not already done):
   ```bash
   git clone https://github.com/allenpeng0705/HomeClaw.git
   cd HomeClaw
   pip install -r requirements.txt
   ```
2. **Configure** `config/core.yml` and `config/user.yml` as needed (LLM, users).
3. **Start Core:**
   ```bash
   python -m main start
   ```
   Leave this running (or run Core in the background / as a service). Core listens on **port 9000** by default.

4. **Verify locally:** In a browser or with curl:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9000/ready
   ```
   You should see **200**.

---

## Step 2: Enable auth on Core (required for public tunnel)

Because the tunnel URL will be **public**, you must enable authentication so only you can use Core.

1. Open **config/core.yml**.
2. Set:
   ```yaml
   auth_enabled: true
   auth_api_key: "YOUR_LONG_RANDOM_KEY_HERE"
   ```
   Use a long, random string (e.g. 32+ characters). Example (generate your own):
   ```bash
   openssl rand -hex 24
   ```
3. **Restart Core** so the new config is loaded (stop with Ctrl+C, then run `python -m main start` again).

**Save the API key** — you will enter it in the Companion app on your iPhone.

---

## Step 3: Install cloudflared on the same machine as Core

Install the Cloudflare Tunnel client (**cloudflared**) on the machine where Core is running.

### macOS (Homebrew)

```bash
brew install cloudflared
```

### macOS (manual) or Linux

1. Download the right binary from [Cloudflare: Install cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).
2. Or with curl (example for macOS ARM64):
   ```bash
   curl -L -o cloudflared.tgz "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz"
   tar -xzf cloudflared.tgz
   sudo mv cloudflared /usr/local/bin/
   ```
3. Check:
   ```bash
   cloudflared --version
   ```

### Windows

Download from [Cloudflare Tunnel releases](https://github.com/cloudflare/cloudflared/releases) (e.g. `cloudflared-windows-amd64.exe`) and put it in your PATH, or use the installer from the Cloudflare docs.

---

## Step 4: Start a quick tunnel to Core

On the **same machine** where Core is running:

1. Run:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:9000
   ```
2. **Copy the URL** printed in the terminal. It looks like:
   ```text
   https://random-words-here.trycloudflare.com
   ```
   This URL is **public**: anyone with it could try to reach your Core, which is why you enabled `auth_enabled` and `auth_api_key`.

3. **Leave this terminal open** — the tunnel stays active while the command runs. If you close it, the URL stops working (quick tunnels get a new URL each time you start).

**Optional (stable URL):** For a URL that doesn’t change every time, use a **named tunnel** and a custom hostname in the Cloudflare dashboard. See [Cloudflare Tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/). The steps below work the same; you just use your stable URL instead of `https://....trycloudflare.com`.

---

## Step 5: Get the Companion app on your iPhone

Choose one:

### Option A: Build from source (recommended for testing)

1. On a Mac with **Xcode** and **Flutter** installed:
   ```bash
   cd HomeClaw/clients/HomeClawApp
   flutter pub get
   flutter run -d ios
   ```
   Or open the Xcode project under `ios/` and run on a connected iPhone or simulator.

2. See **clients/HomeClawApp/README.md** for full build and signing steps (e.g. development team, provisioning profile for a real device).

### Option B: Install from TestFlight or App Store

If you have a TestFlight or store build, install the HomeClaw Companion app on your iPhone as usual.

---

## Step 6: Configure the Companion app on iPhone

1. **Open the Companion app** on your iPhone.
2. Go to **Settings** (or the screen where you set the Core connection).
3. Set **Core URL** to the tunnel URL you copied in Step 4, e.g.:
   ```text
   https://random-words-here.trycloudflare.com
   ```
   - Use **https** and the **full URL** (no path like `/inbound` — the app adds that).
   - Do **not** add a trailing slash unless the app expects it.
4. Set **API key** to the same value as `auth_api_key` in **config/core.yml** (from Step 2).
5. Save / confirm. The app will use this URL and key for **POST /inbound** and **WebSocket /ws**.

---

## Step 7: Test the connection

1. **On the iPhone:** In the Companion app, open the chat screen and send a short message (e.g. “Hello”).
2. **Expected:** The assistant replies. If it does, Core is reachable via the tunnel and auth is correct.
3. **On the Core machine:** You can watch the tunnel terminal for log lines and Core’s terminal for request logs.

### If it doesn’t work

| Symptom | What to check |
|--------|----------------|
| “Connection failed” / no reply | Core URL in the app must be **exactly** the tunnel URL (https, no typo). Tunnel must still be running on the Core machine. |
| 401 Unauthorized | API key in the app must **exactly** match `auth_api_key` in **config/core.yml** (no extra spaces). |
| Timeout | Core must be running and reachable at `http://127.0.0.1:9000` on the machine where `cloudflared` runs. Check with `curl http://127.0.0.1:9000/ready` on that machine. |
| Tunnel URL gone | Quick tunnels get a **new URL** each time you run `cloudflared tunnel --url ...`. Update the Core URL in the app if you restarted the tunnel. |

---

## Step 8: Use the app over cellular or another Wi‑Fi

Once the tunnel is running and the app is configured:

- **Turn off Wi‑Fi** on the iPhone and use **cellular** (or connect to a different Wi‑Fi than the Core machine).
- Open the Companion app and send another message.

If you get a reply, you’ve confirmed **remote access** to HomeClaw via Cloudflare Tunnel.

---

## Summary checklist

- [ ] Core is running on the “server” machine (e.g. `python -m main start`).
- [ ] **auth_enabled: true** and **auth_api_key** set in **config/core.yml**; Core restarted.
- [ ] **cloudflared** installed on the same machine as Core.
- [ ] **cloudflared tunnel --url http://127.0.0.1:9000** is running and you have the `https://....trycloudflare.com` URL.
- [ ] Companion app on iPhone: **Core URL** = tunnel URL, **API key** = same as in core.yml.
- [ ] Test message from the app succeeds; then test on cellular or another network.

For a **stable URL** that doesn’t change on restart, set up a **named tunnel** and a hostname in the Cloudflare dashboard; then use that URL in the Companion app. For more options (Tailscale, SSH tunnel), see [Remote access](remote-access.md).
