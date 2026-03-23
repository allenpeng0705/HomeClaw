# Remote Access

HomeClaw Core runs on your home computer. To use the Companion App from your phone on cellular, or a laptop away from home, you need a way for the app to reach Core over the internet. This guide covers four options: **Pinggy** (built-in), **Cloudflare Tunnel**, **ngrok**, and **Tailscale**.

No changes to Core or the app are required — you only need to expose Core and enter the resulting URL in the Companion App.

---

## Which method should I use?

| Method | Setup time | Cost | URL stability | Best for |
|--------|-----------|------|--------------|----------|
| **[Pinggy](#pinggy-built-in)** | 1 min | Free tier available | Changes on restart (free) | Quickest start; built into HomeClaw with QR scan |
| **[Cloudflare Tunnel](#cloudflare-tunnel)** | 5 min | Free | Stable with named tunnel | Reliable, long-term use |
| **[ngrok](#ngrok)** | 3 min | Free tier available | Stable with paid plan | Quick testing, developer-friendly |
| **[Tailscale](#tailscale)** | 5 min | Free for personal | Stable IP | Private network, no public exposure |

**Quick answer:** If you want the fastest setup, use **Pinggy** (already built into HomeClaw). If you want a stable public URL, use **Cloudflare Tunnel**. If you want zero public exposure, use **Tailscale**.

---

## Before you start: enable auth

When Core is reachable from the internet, **always** enable authentication so only you can use it.

Edit `config/core.yml`:

```yaml
auth_enabled: true
auth_api_key: "your-long-random-key"
```

Generate a strong key:

```bash
openssl rand -hex 24
```

Restart Core after changing auth settings. Enter the same API key in the Companion App's Settings.

---

## Pinggy (built-in)

Pinggy is the easiest option because HomeClaw has **built-in support**. Core starts the tunnel automatically and shows a QR code you scan with the Companion App.

### Setup

1. **Get a Pinggy token** — Sign up at [pinggy.io](https://pinggy.io) and create a token.

2. **Configure Core** — In `config/core.yml`:

```yaml
pinggy:
  token: "your-pinggy-token"
  open_browser: true
```

3. **Start Core:**

```bash
python -m main start
```

4. **Scan to connect** — Core opens a page at `http://127.0.0.1:9000/pinggy` showing:
    - The public tunnel URL
    - A QR code for the Companion App

5. **In the Companion App** — Go to **Settings → Scan QR to connect** and scan the QR code. The app saves the URL and API key automatically.

### Install the Pinggy package

If the `/pinggy` page shows "pinggy package not installed":

```bash
pip install pinggy
# Or if your mirror doesn't have it:
pip install pinggy -i https://pypi.org/simple
```

---

## Cloudflare Tunnel

Cloudflare Tunnel gives you a free public HTTPS URL that forwards to Core. No port forwarding on your router needed.

### Quick tunnel (testing)

1. **Install cloudflared:**

```bash
# macOS
brew install cloudflared

# Linux (Debian/Ubuntu)
sudo apt install cloudflared

# Windows
winget install Cloudflare.cloudflared
```

2. **Start a tunnel to Core:**

```bash
cloudflared tunnel --url http://127.0.0.1:9000
```

3. **Copy the URL** — looks like `https://random-words.trycloudflare.com`

4. **In the Companion App** — Set **Core URL** to the tunnel URL and **API key** to your `auth_api_key`.

5. **Test** — Send a message from the app. If you get a reply, you're connected.

The URL changes each time you restart the tunnel. For a stable URL, use a **named tunnel**.

### Named tunnel (stable URL)

For a permanent URL like `https://homeclaw.yourdomain.com`:

1. Log in: `cloudflared tunnel login`
2. Create a tunnel: `cloudflared tunnel create homeclaw`
3. Create `~/.cloudflared/config.yml`:

```yaml
tunnel: homeclaw
credentials-file: /home/you/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: homeclaw.yourdomain.com
    service: http://127.0.0.1:9000
  - service: http_status:404
```

4. Route DNS: `cloudflared tunnel route dns homeclaw homeclaw.yourdomain.com`
5. Start: `cloudflared tunnel run homeclaw`

See [Companion on iPhone via Cloudflare Tunnel](companion-iphone-cloudflare-tunnel.md) for a detailed step-by-step walkthrough.

### Use `core_public_url` for QR scan

If you use Cloudflare Tunnel (or any public URL) and want the Companion App's QR scan feature:

In `config/core.yml`:

```yaml
core_public_url: "https://homeclaw.yourdomain.com"
```

Now `http://127.0.0.1:9000/pinggy` shows your Cloudflare URL and a QR code — scan it from the Companion App to connect automatically.

---

## ngrok

ngrok is a popular tunneling tool that's quick to set up and developer-friendly.

### Setup

1. **Sign up** at [ngrok.com](https://ngrok.com) and get your authtoken.

2. **Install ngrok:**

```bash
# macOS
brew install ngrok

# Linux
snap install ngrok

# Windows
choco install ngrok
# Or download from https://ngrok.com/download
```

3. **Authenticate:**

```bash
ngrok config add-authtoken your-auth-token
```

4. **Start a tunnel to Core:**

```bash
ngrok http 9000
```

5. **Copy the URL** — ngrok shows a forwarding URL like `https://abc123.ngrok-free.app`

6. **In the Companion App** — Set **Core URL** to the ngrok URL and **API key** to your `auth_api_key`.

### Stable URL (paid plan)

On ngrok's free tier, the URL changes each restart. With a paid plan, you can set a fixed domain:

```bash
ngrok http 9000 --domain=homeclaw.ngrok-free.app
```

### Use `core_public_url` for QR scan

```yaml
core_public_url: "https://abc123.ngrok-free.app"
```

This lets the Companion App's QR scan feature use your ngrok URL.

---

## Tailscale

Tailscale creates a private network between your devices. Only devices on your Tailscale network can reach Core — nothing is exposed to the public internet.

### Setup

1. **Install Tailscale** on the Core machine and on your phone/laptop: [tailscale.com/download](https://tailscale.com/download)

2. **Log in** with the same account on both devices.

3. **Find Core's Tailscale IP:**

```bash
tailscale ip
# e.g. 100.101.102.103
```

4. **In the Companion App** — Set **Core URL** to `http://100.101.102.103:9000`.

### Optional: HTTPS with Tailscale Serve

```bash
tailscale serve https / http://127.0.0.1:9000
```

This gives you a URL like `https://your-machine.your-tailnet.ts.net`. Use this as the Core URL for HTTPS.

### Tailscale Funnel (public access)

If you want public access via Tailscale:

```bash
tailscale funnel 9000
```

This exposes Core publicly — enable `auth_enabled` in core.yml.

---

## Summary: connecting the Companion App

No matter which method you use, the Companion App only needs two things:

1. **Core URL** — The public/tunnel URL (e.g. `https://random-words.trycloudflare.com`)
2. **API key** — The same value as `auth_api_key` in `config/core.yml`

Enter both in **Settings** in the Companion App, or use **Scan QR to connect** if you configured Pinggy or `core_public_url`.

---

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| "Connection failed" | Is Core running? (`curl http://127.0.0.1:9000/ready` should return 200 on the Core machine) |
| 401 Unauthorized | API key in the app must exactly match `auth_api_key` in core.yml |
| Timeout | Is the tunnel running? Quick tunnels stop when you close the terminal |
| URL changed | Free-tier quick tunnels get new URLs on restart; update the app |
| 502 Bad Gateway | Core is not running, or the tunnel points to the wrong port |
| Works on Wi-Fi, not on cellular | The tunnel may not be running, or DNS hasn't propagated (for named tunnels) |

### Test from your phone

1. Turn off Wi-Fi on your phone
2. Open the Companion App on cellular
3. Send a message

If you get a reply, remote access is working.

---

## Running tunnels as a service

For always-on access, run your tunnel as a system service so it restarts automatically:

- **Cloudflare Tunnel:** `sudo cloudflared service install` → `sudo systemctl enable cloudflared`
- **ngrok:** Use a process manager like systemd or pm2, or ngrok's built-in service mode
- **Pinggy:** Runs automatically when Core starts (if `pinggy.token` is set in core.yml)
- **Tailscale:** Runs as a system service by default after installation

See [Site service and Cloudflare Tunnel](site-service-and-cloudflare-tunnel.md) for detailed service setup on Linux and Windows.
