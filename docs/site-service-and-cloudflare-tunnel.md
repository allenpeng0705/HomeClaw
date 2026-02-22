# Site as a service and Cloudflare Tunnel

This guide explains how to:

1. Run the **site** folder (static promo site) as a **service** on your machine so it restarts automatically when the machine restarts.
2. Publish it with **Cloudflare Tunnel** so the site is reachable via a public HTTPS URL without opening ports on your router.

**Platforms:**

- **Linux:** systemd service (Part 1) + cloudflared (Part 2).
- **Windows:** Python script + NSSM or Task Scheduler (Part 3) + cloudflared (Part 2 and Part 3).

**Prerequisites:** Python 3 on the machine; for Cloudflare Tunnel, a Cloudflare account (free tier is enough).

---

## Part 1: Run the site as a systemd service

### 1.1 Choose a port and repo path

- **Port:** Default is **9999**. The site will listen on `http://127.0.0.1:9999` (localhost only; Cloudflare Tunnel will expose it).
- **Repo path:** Use the **absolute path** to your HomeClaw repo, e.g. `/opt/HomeClaw` or `/home/youruser/HomeClaw`.

### 1.2 Make the serve script executable

From the repo root:

```bash
chmod +x scripts/serve_site.sh
```

Test it manually:

```bash
./scripts/serve_site.sh
# Or: PORT=3000 ./scripts/serve_site.sh
```

Then open **http://localhost:9999** (or 3000). Stop with Ctrl+C.

### 1.3 Install the systemd unit

1. **Copy the unit file** and edit the two paths:

   ```bash
   sudo cp scripts/systemd/homeclaw-site.service /etc/systemd/system/
   sudo nano /etc/systemd/system/homeclaw-site.service
   ```

   Replace **both** occurrences of `/path/to/HomeClaw` with your repo path, e.g. `/opt/HomeClaw`:

   - `WorkingDirectory=/opt/HomeClaw`
   - `ExecStart=/opt/HomeClaw/scripts/serve_site.sh`

   Optionally change **port** with `Environment=PORT=3000` and **user** (e.g. `User=youruser` if you don’t want to use `www-data`). If you change the user, ensure that user can read the repo (especially the `site/` directory).

2. **Reload systemd**, enable the service (start on boot), and start it:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable homeclaw-site
   sudo systemctl start homeclaw-site
   ```

3. **Check status:**

   ```bash
   sudo systemctl status homeclaw-site
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9999
   # Should print 200
   ```

4. **After a reboot:** The service should start automatically. Verify with `systemctl status homeclaw-site` and `curl http://127.0.0.1:9999`.

**Useful commands:**

| Command | Description |
|--------|-------------|
| `sudo systemctl status homeclaw-site` | Show status and recent logs |
| `sudo systemctl restart homeclaw-site` | Restart the site server |
| `sudo systemctl stop homeclaw-site` | Stop the service |
| `sudo journalctl -u homeclaw-site -f` | Follow logs |

---

## Part 2: Publish with Cloudflare Tunnel

Cloudflare Tunnel (`cloudflared`) creates an outbound connection from your machine to Cloudflare and forwards public HTTPS traffic to your local site server. You do **not** open any port on your router.

### 2.1 Install cloudflared

**Linux (generic):**

- Download from [Developers: Cloudflare Tunnel — Install](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).
- Or with a package manager, e.g.:
  - **Debian/Ubuntu:** `sudo apt install cloudflared` (if in your repos), or use the official `.deb` from Cloudflare.
  - **Fedora/RHEL:** See Cloudflare docs for `yum`/`dnf`.

**macOS:** `brew install cloudflared`

**Windows:** Download the Windows build from [Cloudflare Tunnel — Install](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) (e.g. `cloudflared-windows-amd64.exe`). Rename to `cloudflared.exe`, place it in a folder (e.g. `C:\Program Files\cloudflared\`), and add that folder to your PATH. Or use **winget**: `winget install Cloudflare.cloudflared`.

Verify:

```bash
cloudflared --version
```

### 2.2 Option A: Quick Tunnel (random URL, good for testing)

Creates a temporary URL like `https://random-words.trycloudflare.com` that forwards to your local server.

1. Ensure the **site service** is running and listening on `http://127.0.0.1:9999` (or whatever port you used).

2. Run:

   ```bash
   cloudflared tunnel --url http://127.0.0.1:9999
   ```

3. In the output you’ll see a line like: **Your quick Tunnel has been created! Visit it at:** `https://xxxx.trycloudflare.com`. Open that URL in a browser to see your site.

4. Stop the tunnel with Ctrl+C. The URL stops working when the tunnel process stops. For a **permanent** setup, use Option B (named tunnel).

### 2.3 Option B: Named Tunnel (stable URL, recommended for production)

Gives you a **stable hostname** (e.g. `site.yourdomain.com`) and allows running the tunnel as a service so it survives reboots.

#### Step 1: Log in and create a tunnel

1. Log in (opens browser):

   ```bash
   cloudflared tunnel login
   ```

   A browser tab opens; choose your Cloudflare account and domain. This saves a credential file (e.g. `~/.cloudflared/cert.pem`).

2. Create a **named tunnel** (e.g. `homeclaw-site`):

   ```bash
   cloudflared tunnel create homeclaw-site
   ```

   This creates a tunnel and an ID. You’ll use the tunnel name in the config file.

3. Create a config file, e.g. `~/.cloudflared/config.yml`:

   ```yaml
   tunnel: homeclaw-site
   credentials-file: /home/youruser/.cloudflared/<TUNNEL_ID>.json

   ingress:
     - hostname: site.yourdomain.com
       service: http://127.0.0.1:9999
     - service: http_status:404
   ```

   Replace:

   - `youruser` with your Linux username.
   - `<TUNNEL_ID>` with the tunnel ID from step 2 (find it with `cloudflared tunnel list`; the JSON file is in `~/.cloudflared/`).
   - `site.yourdomain.com` with the subdomain (or domain) you want for the site.

4. **Route the hostname** to this tunnel in Cloudflare:

   ```bash
   cloudflared tunnel route dns homeclaw-site site.yourdomain.com
   ```

   This creates a CNAME in your Cloudflare DNS pointing to the tunnel. If your domain is not on Cloudflare, use the alternative “Route via Dashboard” in Cloudflare docs.

5. **Run the tunnel** (foreground, for a quick test):

   ```bash
   cloudflared tunnel run homeclaw-site
   ```

   Open **https://site.yourdomain.com** in a browser. Stop with Ctrl+C when done testing.

#### Step 2: Run the tunnel as a service (auto-restart and start on boot)

1. **Install cloudflared as a system service** (Linux):

   ```bash
   sudo cloudflared service install
   ```

   This may create a unit that runs the **default** config. To make it use your named tunnel and config, you typically need to point the service at your config file.

2. **Use your config file:** On many setups, the installed service reads `~/.cloudflared/config.yml` for the **user** that ran `service install`. If you ran it with `sudo`, the config might be expected in `/etc/cloudflared/config.yml`. Copy your config there and set the paths:

   ```bash
   sudo mkdir -p /etc/cloudflared
   sudo cp ~/.cloudflared/config.yml /etc/cloudflared/
   # Edit credentials-file path to the JSON file (e.g. /home/youruser/.cloudflared/xxx.json or copy the json to /etc/cloudflared/ and point there)
   sudo nano /etc/cloudflared/config.yml
   ```

   Cloudflare’s official docs describe the exact path and format for your OS: [Run as a service](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/local/#run-the-tunnel-as-a-service).

3. **Enable and start the cloudflared service:**

   ```bash
   sudo systemctl enable cloudflared
   sudo systemctl start cloudflared
   sudo systemctl status cloudflared
   ```

4. After a **reboot**, both the site server and the tunnel should start automatically: the site serves files on localhost:9999, and cloudflared exposes them at https://site.yourdomain.com.

**Useful commands:**

| Command | Description |
|--------|-------------|
| `cloudflared tunnel list` | List tunnels and IDs |
| `cloudflared tunnel run homeclaw-site` | Run tunnel in foreground (for testing) |
| `sudo systemctl status cloudflared` | Status of tunnel service |
| `sudo journalctl -u cloudflared -f` | Follow tunnel logs |

---

## Summary

| Component | Role | Restart on reboot |
|-----------|------|-------------------|
| **homeclaw-site.service** | Serves `site/` on http://127.0.0.1:9999 | Yes (systemd `enable`) |
| **cloudflared** (tunnel) | Forwards https://site.yourdomain.com → http://127.0.0.1:9999 | Yes (when run as system service) |

- You do **not** open port 9999 (or 80/443) on your router; Cloudflare Tunnel uses an outbound connection.
- The site is static (HTML/CSS/images); no API keys or secrets are required for the site itself. If you add auth or sensitive content later, configure it in the site or behind Cloudflare Access.

For **Cloudflare Pages** (hosting the same static files on Cloudflare’s edge instead of your machine), see [site/README.md](../site/README.md#deploy-to-cloudflare-pages).

---

## Part 3: Windows — site and tunnel as services

On **Windows**, use the **Python** site server (no bash) and run it as a Windows service with **NSSM** or **Task Scheduler**. Then run **cloudflared** as a Windows service so the tunnel restarts on reboot.

### 3.1 Run the site (test manually)

From the repo root in **PowerShell** or **Command Prompt**:

```powershell
python scripts\serve_site.py
# Or with a different port: set PORT=3000 && python scripts\serve_site.py
# Or: python scripts\serve_site.py 3000
```

Open **http://127.0.0.1:9999** in a browser. Stop with Ctrl+C.

The script `scripts/serve_site.py` finds the repo root from the script's directory (or from `HOMECLAW_REPO_ROOT` if set) and serves the `site/` folder. It works on both Windows and Linux.

### 3.2 Run the site as a Windows service (auto-restart on reboot)

You have two options: **NSSM** (recommended) or **Task Scheduler**. Replace `D:\mygithub\HomeClaw` and `C:\Users\YourName\...` with your actual paths.

---

#### Option A: NSSM (Non-Sucking Service Manager)

**Step 1: Download and extract NSSM**

1. Go to [nssm.cc/download](https://nssm.cc/download).
2. Download the latest release (e.g. **nssm-2.24.zip**).
3. Extract the ZIP. Use the **win64** folder (e.g. `nssm-2.24\win64\nssm.exe`). Remember this path (e.g. `C:\Tools\nssm-2.24\win64`).

**Step 2: Find your Python path**

1. Open **Command Prompt** or **PowerShell**.
2. Run: `where python`
3. Note the first path (e.g. `C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe`). If you use a venv, use that `python.exe` path instead.

**Step 3: Install the service with NSSM**

1. **Right-click** the **Start** button → **Terminal (Admin)** or **Command Prompt (Admin)** (or **PowerShell (Admin)**).
2. Go to the NSSM folder:
   ```cmd
   cd C:\Tools\nssm-2.24\win64
   ```
   (Use your actual NSSM path.)

3. Run:
   ```cmd
   nssm install HomeClawSite
   ```
   A window titled **NSSM - Install HomeClawSite service** opens.

4. **Application** tab (should be open by default):
   - **Path:** Click **Browse**, go to your Python folder, select **python.exe** (e.g. `C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe`). Or type/paste the full path.
   - **Startup directory:** Click **Browse**, go to your HomeClaw repo root (e.g. `D:\mygithub\HomeClaw`), select that folder and confirm. Or type: `D:\mygithub\HomeClaw`.
   - **Arguments:** Type: `scripts\serve_site.py`
     - The site will use port **9999** by default. To use another port, type: `scripts\serve_site.py 3000`

5. **Details** tab (optional):
   - **Display name:** `HomeClaw Site`
   - **Description:** e.g. `Serves the HomeClaw static site on port 9999`

6. **I/O** tab (optional, for logs):
   - **Output (stdout):** e.g. `D:\mygithub\HomeClaw\logs\site-stdout.log`
   - **Error (stderr):** e.g. `D:\mygithub\HomeClaw\logs\site-stderr.log`
   - Create the `logs` folder first if it doesn’t exist.

7. Click **Install service**. A message says the service was installed. Click **OK** and close the NSSM window.

**Step 4: Start the service**

In the same admin Command Prompt (in the NSSM folder):

```cmd
nssm start HomeClawSite
```

You should see: `HomeClawSite: START: The operation completed successfully.`

**Step 5: Check**

1. Open a browser and go to **http://127.0.0.1:9999**. You should see the HomeClaw site.
2. Optional: In **Services** (Win+R → `services.msc` → find **HomeClaw Site**), confirm status is **Running** and **Startup type** is **Automatic** so it starts after reboot.

**Useful NSSM commands** (run from the NSSM folder in an admin prompt):

| Command | Description |
|--------|-------------|
| `nssm start HomeClawSite` | Start the service |
| `nssm stop HomeClawSite` | Stop the service |
| `nssm restart HomeClawSite` | Restart the service |
| `nssm status HomeClawSite` | Show status |
| `nssm remove HomeClawSite confirm` | Remove the service (stops and uninstalls) |

---

#### Option B: Task Scheduler (run at logon or at startup)

**Step 1: Find your Python path and repo path**

1. In Command Prompt or PowerShell, run: `where python` — note the full path to `python.exe` (e.g. `C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe`).
2. Note your HomeClaw repo root (e.g. `D:\mygithub\HomeClaw`).

**Step 2: Open Task Scheduler**

1. Press **Win+R**, type **taskschd.msc**, press **Enter**.
2. Or search **Task Scheduler** in the Start menu and open it.

**Step 3: Create a basic task**

1. In the right panel, click **Create Basic Task...**.
2. **Name:** e.g. `HomeClaw Site`
3. **Description (optional):** e.g. `Serves the HomeClaw static site on port 9999`
4. Click **Next**.

**Step 4: Set the trigger**

1. Choose **When I log on** (task runs when you sign in) or **When the computer starts** (runs at boot; useful if the machine runs without a user logging in).
2. Click **Next**.

**Step 5: Set the action**

1. Select **Start a program** → **Next**.
2. **Program/script:** Enter the **full path** to `python.exe` (e.g. `C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe`). Or click **Browse** and select it.
3. **Add arguments (optional):** `scripts\serve_site.py`  
   (If the task runs before the working directory is set, use the full path: `D:\mygithub\HomeClaw\scripts\serve_site.py`)
4. **Start in (optional):** Enter the **full path** to your HomeClaw repo root (e.g. `D:\mygithub\HomeClaw`). This is important so the script finds the `site` folder.
5. Click **Next**.

**Step 6: Finish**

1. Check **Open the Properties dialog...** if you want to change “Run whether user is logged on or not” or “Run with highest privileges”.
2. Click **Finish**.

**Step 7: Optional — run at startup without logging in**

1. In Task Scheduler, find **HomeClaw Site** in the list, **right-click** → **Properties**.
2. **General** tab: Check **Run whether user is logged on or not** if the task should run at startup even when no one is logged in. You may be prompted for your password.
3. **Conditions** tab: Uncheck **Start the task only if the computer is on AC power** if you want it to run on battery (e.g. laptop).
4. Click **OK**.

**Step 8: Run the task once to test**

1. Right-click **HomeClaw Site** → **Run**.
2. Open **http://127.0.0.1:9999** in a browser to confirm the site loads.

After reboot (or next logon, depending on the trigger), the task will run again and the site will be available at http://127.0.0.1:9999.

### 3.3 Cloudflare Tunnel on Windows

1. **Install cloudflared** (see [2.1 Install cloudflared](#21-install-cloudflared)) and ensure `cloudflared` is on your PATH.

2. **Quick Tunnel (test):** With the site running (manually or as a service), open PowerShell or Command Prompt:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:9999
   ```

   Use the printed URL (e.g. `https://xxxx.trycloudflare.com`) to open your site. Stop with Ctrl+C.

3. **Named Tunnel (stable URL):** Same as Linux: run `cloudflared tunnel login`, then `cloudflared tunnel create homeclaw-site`, create a config file (use Windows paths for `credentials-file`), and run `cloudflared tunnel route dns homeclaw-site site.yourdomain.com`. Config path on Windows is often `%USERPROFILE%\.cloudflared\config.yml`; in the config use `credentials-file: C:\Users\YourName\.cloudflared\<TUNNEL_ID>.json` and `service: http://127.0.0.1:9999`.

4. **Run cloudflared as a Windows service** so the tunnel restarts on reboot:

   - **Option A:** Run `cloudflared service install` (if your build supports it), then configure it to use your named tunnel (see [Cloudflare: Run as a service](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/local/#run-the-tunnel-as-a-service)).
   - **Option B:** Use NSSM to run cloudflared as a service: **Path** = full path to `cloudflared.exe`, **Arguments** = `tunnel run homeclaw-site`, **Startup directory** = folder containing your config (e.g. `C:\Users\YourName\.cloudflared`).

After reboot, start the **site** service (NSSM or Task Scheduler) and the **cloudflared** service; your site will be available at your tunnel URL.
