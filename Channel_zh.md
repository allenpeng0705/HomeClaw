# HomeClaw — 渠道指南

渠道是用户（或机器人）访问 HomeClaw Core 的方式。本文分两部分：**第一部分面向用户**（如何使用与配置渠道），**第二部分面向开发者**（设计、与其他方案对比及改进）。

**其他语言：** [English](Channel.md) | [日本語](Channel_jp.md) | [한국어](Channel_kr.md)

---

# 第一部分 — 面向用户

## 1. 什么是渠道？

**渠道**是与家中 Core 对话的方式：

- **从手机或别处**：使用 Email、Matrix、WeChat、WhatsApp，或通过将消息转发到 Core 的机器人（如 Telegram）。
- **从本机**：使用终端 CLI，或（未来）浏览器中的 WebChat。

所有渠道共用同一 Core 和同一权限列表：在 `config/user.yml` 中配置允许与助手对话的用户。

---

## 2. 通用配置

### 2.1 允许谁可对话（IM 与机器人必配）

编辑 **`config/user.yml`**。每个用户有：

- **name**：显示名。
- **email**、**im**、**phone**：Core 用于匹配入站消息的标识（如邮箱、`telegram_123456789`）。
- **permissions**：该用户可用的渠道类型：`EMAIL`、`IM`、`PHONE`，或留空表示全部允许。

**inbound 类机器人**（Telegram、Discord 等）：在 **im** 中使用 `telegram_<chat_id>` 或 `discord_<user_id>`，并在 **permissions** 中加入 `IM`（或留空允许全部）。**邮件**渠道：将允许的地址写在 **email** 中并添加 `EMAIL`。

### 2.2 Core 地址（供渠道进程使用）

渠道进程需知道 Core 的地址。在 **`channels/.env`** 中设置：

```env
core_host=127.0.0.1
core_port=9000
mode=dev
```

若渠道在另一台机器运行，请使用该机的 IP 或主机名。

---

## 3. 可用渠道

**所有支持的渠道**

| 渠道 | 类型 | 运行方式 |
|------|------|----------|
| **CLI** | 进程内 (local_chat) | `python main.py` |
| **Email** | 完整 (BaseChannel) | 单独启动；见 §3.2。代码：`core/emailChannel/` 或 `channels/emailChannel/`。 |
| **Matrix, Tinode, WeChat, WhatsApp** | 完整 (BaseChannel) | `python -m channels.run matrix`（或 tinode, wechat, whatsapp） |
| **Telegram, Discord, Slack** | Inbound (POST /inbound) | `python -m channels.run telegram`（或 discord, slack） |
| **Google Chat, Signal, iMessage, Teams, Zalo, Feishu, DingTalk, BlueBubbles** | Inbound / HTTP / webhook | `python -m channels.run google_chat`（或 signal, imessage, teams, zalo, feishu, dingtalk, bluebubbles） |
| **WebChat** | WebSocket /ws | `python -m channels.run webchat` |
| **Webhook** | 中继（转发到 Core /inbound） | `python -m channels.run webhook` |

**鉴权（对外暴露 Core 时）：** 在 `config/core.yml` 中设置 **auth_enabled: true** 和 **auth_api_key**；则 **POST /inbound** 与 **WebSocket /ws** 需携带 **X-API-Key** 或 **Authorization: Bearer**。见 **docs/RemoteAccess.md**。

---

### 3.1 CLI（终端）

**用途**：在运行 Core 的本机与助手对话。**运行**：`python main.py`，输入消息回车；回复在同一终端打印。**配置**：无需在 user.yml 中为本地 CLI 添加自己（本地发送者视为已允许）。前缀：`+` 存记忆、`?` 查记忆、`quit` 退出、`llm` 列出/切换 LLM。

### 3.2 Email

**用途**：发邮件到助手邮箱，回复通过邮件返回。**配置**：`config/email_account.yml`（IMAP/SMTP 与凭证）、`config/user.yml`（邮箱与 EMAIL 权限）、`channels/emailChannel/config.yml`（可选）。**运行**：先启动 Core，再启动邮件渠道（见部署或主文档）。

### 3.3 Matrix、Tinode、WeChat、WhatsApp（完整渠道）

**用途**：用常用 IM 与助手对话；各为**独立进程**，登录/连接 IM 并将消息转发到 Core。**配置**：各渠道目录下有 `config.yml` 及 `.env`（凭证）；`config/user.yml` 中添加允许的 im 身份与 permissions；`channels/.env` 中设置 **core_host**、**core_port**。**运行**：先启动 Core，再启动对应渠道（见各渠道 README）。渠道向 Core 注册，通过 HTTP 回调接收回复。

### 3.4 Inbound API（任意机器人，无需新渠道代码）

**用途**：任意机器人（Telegram、Discord、Slack、n8n、自写脚本）通过“每条消息一次 HTTP 请求”连接 Core。**配置**：`config/user.yml` 中添加机器人使用的 **user_id**（如 `telegram_123456789`）到 **im** 并设 **IM** 权限；机器人需能 POST 到 `http://<core_host>:<core_port>/inbound`；对外暴露时可选配置 auth，见 docs/RemoteAccess.md。**请求**：`POST /inbound`，JSON 体 `{ "user_id", "text", "channel_name?", "user_name?" }`。**响应**：`{ "text": "..." }`。示例：`channels/telegram/`（BotFather 取 token，配置 .env 与 user.yml，`python -m channels.run telegram`）。

### 3.5 Webhook 渠道（Core 不可达时的中继）

**用途**：Core 仅在内网时，在能同时被机器人与 Core 访问的主机上运行 **Webhook**；机器人 POST 到 Webhook，Webhook 转发到 Core 并返回回复。**配置**：`channels/.env` 中设置 **core_host**、**core_port**；user.yml 同 Inbound。**运行**：`python -m channels.run webhook`，默认端口 8005。请求：`POST http://<webhook_host>:8005/message`，体同 /inbound，响应 `{ "text": "..." }`。

### 3.6 WebSocket（自有客户端）

**用途**：专用客户端（如浏览器 WebChat）保持与 Core 的一条连接。**端点**：`ws://<core_host>:<core_port>/ws`。**协议**：发送 JSON `{ "user_id", "text" }`，接收 `{ "text", "error" }`。**配置**：同 user_id 允许列表；auth_enabled 时在握手头中发 X-API-Key 或 Authorization: Bearer。

### 3.7 故障排查："Connection error when sending to http://127.0.0.1:8005/get_response"

表示 **Core** 正在向 **Matrix（或其他完整）渠道** 的 `/get_response` 推送回复，但该地址无监听。**原因**：完整渠道以**独立进程**运行，渠道必须**已启动**并在注册给 Core 的端口上监听。**处理**：在单独终端运行 `python -m channels.run matrix`（等）；先启动 Core，再启动渠道；若 Core 与渠道在不同机器，在渠道 `config.yml` 中将 **host** 设为 Core 可访问的 IP（不要用 0.0.0.0，否则 Core 会解析为 127.0.0.1）。

---

## 4. 从任意位置访问（小结）

| 目标 | 方式 |
|------|------|
| 用邮件从手机使用 | **Email** 渠道：发邮件到 Core 所用邮箱，回复通过邮件返回。 |
| 用 IM 从手机使用 | **Matrix/Tinode/WeChat/WhatsApp**：运行对应渠道；或运行 **Telegram 等机器人** POST 到 **Core /inbound** 或 **Webhook /message**（Core 仅在内网时把 Webhook 放在中继上）。 |
| 同 LAN 浏览器 | 使用 **WebSocket /ws** 或 WebChat。 |
| 任意位置浏览器 | 通过 **Tailscale** 或 **SSH 隧道** 暴露 Core（或 Webhook），再使用 WebSocket 或 Web UI。 |

**连通性**：请求方必须能访问 Webhook 或 Core；若 Webhook 与 Core 不在同一机器，Webhook 所在机必须能访问 Core（如反向 SSH、Tailscale）。详见 §4.1。

---

# 第二部分 — 面向开发者

## 1. 当前渠道设计

**两种模式**：（1）**完整渠道** — 实现 BaseChannel 的进程，向 Core 注册，发送 **PromptRequest**，通过 **POST /get_response** 异步收回复或 **POST /local_chat** 同步收回复（Email、Matrix、Tinode、WeChat、WhatsApp、CLI）。（2）**最小（inbound/WebSocket）** — 无 BaseChannel；客户端向 Core 发最小载荷，获同步回复（**POST /inbound**、**WebSocket /ws**、可选 **Webhook** 中继）。两者共用 **config/user.yml** 权限。**契约**：完整渠道 → POST /process（PromptRequest）、POST /local_chat；最小 → POST /inbound（InboundRequest）、WebSocket /ws。**Webhook**：监听端口（默认 8005），POST /message 转发到 Core /inbound，返回 `{ "text": "..." }`。代码：`channels/webhook/channel.py`。

## 2. 与其它方案对比

HomeClaw：Core + 独立渠道进程（或外部机器人）；可经 IM 渠道、POST /inbound、Webhook、WebSocket /ws 连接。渠道代码在 **channels/** 独立于 Core。其它方案：单 Gateway 进程内跑所有渠道；远程通过 Tailscale/SSH 访问 Gateway。我们保留：最小 API、可选 Webhook、本地 LLM + RAG，不强制在仓库内实现每种 IM。

## 3. 当前能力

完整渠道：Email、Matrix、Tinode、WeChat、WhatsApp、CLI；最小 API：POST /inbound、WebSocket /ws；Webhook 中继；示例：channels/telegram/、discord/、slack/，`python -m channels.run <name>`。文档：Design.md、Improvement.md、Comparison.md、Channel.md。

## 4. 已有与可改进项

**已有**：**Onboarding** `python main.py onboard`；**Doctor** `python main.py doctor`；**远程与鉴权** docs/RemoteAccess.md。**可改进**：单一入口启动 Core+渠道、可选配对、WebChat（已有 channels/webchat/）。

## 5. 参考

- **Design**：`Design.md`
- **如何编写新渠道**：**docs/HowToWriteAChannel.md**（完整渠道 vs webhook/inbound，两种方法）
- **Improvement**：`Improvement.md`；**Comparison**：`Comparison.md`；**RemoteAccess**：**docs/RemoteAccess.md**
- **渠道使用**：`channels/README.md`、`channels/webhook/README.md`、`channels/telegram/README.md`
