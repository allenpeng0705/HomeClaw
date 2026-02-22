# Deploy HomeClaw to the cloud

You can run HomeClaw on a **cloud VM** (VPS) so it is always on and reachable from anywhere—Companion app, Telegram, WebChat, etc.—without keeping your home machine running. This page gives a short guide for **Aliyun (阿里云)**, **AWS**, and other providers. The steps are the same; only the way you create the VM and open the firewall differs.

---

## Overview

| Step | What to do |
|------|-------------|
| 1. Create a VM | Use Aliyun ECS, AWS EC2, GCP, Azure, DigitalOcean, or any VPS. Choose **Linux** (Ubuntu 22.04 or similar). |
| 2. Install and run | Same as [Getting started](getting-started.md): clone repo, `pip install -r requirements.txt`, configure, `python -m main start`. |
| 3. Secure Core | Set `auth_enabled: true` and `auth_api_key` in `config/core.yml`; open only port **9000** (or use a tunnel and keep 9000 internal). |
| 4. Keep it running | Use **systemd** (or supervisor) so Core restarts on reboot. |

**Cloud vs home:** On a cloud VM you typically use **cloud LLMs** (OpenAI, Gemini, etc.) and set API keys in the environment. To run **local models** (llama.cpp), copy llama.cpp's binary distribution into `llama.cpp-master/<platform>/` for the VM (e.g. `linux_cpu/` or a GPU build; see `llama.cpp-master/README.md`).

---

## 1. Create a VM

### Aliyun (阿里云) ECS

1. Log in to [Aliyun Console](https://ecs.console.aliyun.com/) (or [International](https://www.alibabacloud.com/)).
2. Create an **ECS instance**: choose a region, **Ubuntu 22.04** (or 20.04), instance type (e.g. 2 vCPU, 4 GiB for cloud-only; larger if you run local models).
3. Set **security group**: allow **inbound TCP 22** (SSH) and **TCP 9000** (Core). Restrict source IPs if you can (e.g. your office IP) or use a tunnel (see [Remote access](remote-access.md)) and do **not** open 9000 to 0.0.0.0/0.
4. Assign an **elastic IP** (optional) so the public IP does not change after reboot.
5. SSH in: `ssh root@<your-ecs-public-ip>` (or use a non-root user and sudo).

### AWS EC2

1. In [AWS EC2 Console](https://console.aws.amazon.com/ec2/), launch an instance: **Ubuntu Server 22.04**, instance type (e.g. t3.small for cloud-only).
2. **Security group**: allow inbound **SSH (22)** and **Custom TCP 9000** (or only 22 if you use a tunnel). Restrict 9000 to your IP or VPN if you open it.
3. Allocate an **Elastic IP** and associate it with the instance (optional).
4. SSH: `ssh -i your-key.pem ubuntu@<ec2-public-ip>`.

### Other providers

- **Tencent Cloud (腾讯云)** — CVM: same idea (Ubuntu, security group for 22 and 9000).
- **GCP** — Compute Engine: create VM with Ubuntu, firewall rules for tcp:22 and tcp:9000.
- **Azure** — Linux VM: Ubuntu, NSG rules for SSH and port 9000.
- **DigitalOcean, Vultr, Linode** — Create Droplet/VPS with Ubuntu; open port 9000 in firewall or use tunnel.

---

## 2. Install and run HomeClaw

On the VM (same as [Getting started](getting-started.md)):

```bash
# Install Python 3 and git if not present (Ubuntu)
sudo apt update && sudo apt install -y python3 python3-pip git

# Clone and install
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
pip install -r requirements.txt   # or: pip3 install -r requirements.txt

# Configure (optional but recommended)
# Edit config/core.yml: main_llm, embedding_llm (e.g. cloud_models/Gemini-2.5-Flash)
# Set API key: export GEMINI_API_KEY="your-key"
# Edit config/user.yml: add users (name, email, im, etc.)
# If using LOCAL models: copy llama.cpp binary distribution into llama.cpp-master/<platform>/ for the VM (e.g. linux_cpu/ or GPU build; see llama.cpp-master/README.md)

# Enable auth (important when Core is reachable from the internet)
# In config/core.yml set:
#   auth_enabled: true
#   auth_api_key: "<long-random-secret>"

# Run Core
python3 -m main start
```

You can chat in the same terminal (CLI) or run a channel in another terminal (e.g. `python3 -m channels.run webchat`). From your phone or laptop, use the **Companion app** with **Core URL** = `http://<vm-public-ip>:9000` (or your tunnel URL) and the same **API key**.

---

## 3. Security

- **Always set** `auth_enabled: true` and a long random `auth_api_key` in `config/core.yml` when the VM is reachable from the internet. Clients (Companion, WebChat, bots) must send `X-API-Key` or `Authorization: Bearer <key>`.
- **Firewall:** Prefer opening only **22** (SSH) and using **Cloudflare Tunnel** or **Tailscale** to reach Core, so you do not expose port 9000 to the public. If you do open 9000, restrict the source IP range if possible.
- **HTTPS:** Use a tunnel (e.g. [Cloudflare Tunnel](remote-access.md#2-cloudflare-tunnel-public-url)) or a reverse proxy (Nginx/Caddy) with TLS in front of Core so clients connect over HTTPS.

---

## 4. Keep Core running (systemd)

To restart Core after reboot and capture logs:

```bash
# Create a systemd service (adjust paths and user)
sudo nano /etc/systemd/system/homeclaw.service
```

Paste (adjust `WorkingDirectory` and `User`):

```ini
[Unit]
Description=HomeClaw Core
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/HomeClaw
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 -m main start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable homeclaw
sudo systemctl start homeclaw
sudo systemctl status homeclaw
```

Logs: `journalctl -u homeclaw -f`.

---

## 5. Summary

| Provider | Create VM | Open firewall | Then |
|----------|-----------|----------------|------|
| **Aliyun ECS** | ECS console, Ubuntu, security group | 22, 9000 (or 22 + tunnel) | SSH → clone, pip install, config, run |
| **AWS EC2** | Launch instance, Ubuntu, security group | 22, 9000 (or 22 + tunnel) | SSH → same |
| **Others** | Same pattern | 22, 9000 or tunnel | Same |

For **remote access without opening 9000**, use [Tailscale](remote-access.md#1-tailscale-recommended-for-home--mobile) or [Cloudflare Tunnel](remote-access.md#2-cloudflare-tunnel-public-url) on the VM; then set the tunnel URL as **Core URL** in the Companion app. For more on auth and tunnels, see [Remote access](remote-access.md).
