# HomeClaw — 채널 가이드

채널은 사용자(또는 봇)가 HomeClaw Core에 접근하는 방식입니다. 이 문서는 두 부분으로 구성됩니다. **1부 사용자용** (채널 사용 및 설정), **2부 개발자용** (설계, 다른 에이전트와 비교, 개선).

**다른 언어:** [English](Channel.md) | [简体中文](Channel_zh.md) | [日本語](Channel_jp.md)

---

# 1부 — 사용자용

## 1. 채널이란?

**채널**은 홈 Core와 대화하는 방법입니다.

- **휴대폰 등 외부에서**: Email, Matrix, WeChat, WhatsApp 또는 메시지를 Core로 전달하는 봇(예: Telegram) 사용.
- **같은 기기에서**: 터미널 CLI 또는 (향후) 브라우저 WebChat 사용.

모든 채널이 동일한 Core와 동일한 허용 목록을 사용합니다. `config/user.yml`에서 누가 어시스턴트와 대화할 수 있는지 설정합니다.

---

## 2. 공통 설정

### 2.1 누가 대화할 수 있는지 (IM·봇에 필요)

**`config/user.yml`** 편집. 각 사용자에 **name**, **email**/**im**/**phone** (Core가 수신과 매칭하는 식별자), **permissions** (EMAIL, IM, PHONE 또는 비워두면 전부 허용). **inbound 스타일 봇**(Telegram, Discord 등): **im**에 `telegram_<chat_id>` 또는 `discord_<user_id>` 사용, **permissions**에 IM 포함(또는 비워두면 전부 허용). **이메일** 채널: 허용 주소를 **email**에, EMAIL 추가.

### 2.2 Core 위치 (채널 프로세스용)

채널 프로세스는 Core 주소를 알아야 함. **`channels/.env`**에 설정:

```env
core_host=127.0.0.1
core_port=9000
mode=dev
```

채널이 다른 머신에서 실행되면 해당 머신의 IP 또는 호스트명 사용.

---

## 3. 사용 가능한 채널

**지원 채널 목록**

| 채널 | 유형 | 실행 |
|------|------|------|
| **CLI** | 프로세스 내 (local_chat) | `python main.py` |
| **Email** | 풀 (BaseChannel) | 별도 시작; §3.2 참조. 코드: `core/emailChannel/` 또는 `channels/emailChannel/`. |
| **Matrix, Tinode, WeChat, WhatsApp** | 풀 (BaseChannel) | `python -m channels.run matrix` (또는 tinode, wechat, whatsapp) |
| **Telegram, Discord, Slack** | Inbound (POST /inbound) | `python -m channels.run telegram` (또는 discord, slack) |
| **Google Chat, Signal, iMessage, Teams, Zalo, Feishu, DingTalk, BlueBubbles** | Inbound / HTTP / webhook | `python -m channels.run google_chat` (또는 signal, imessage, teams, zalo, feishu, dingtalk, bluebubbles) |
| **WebChat** | WebSocket /ws | `python -m channels.run webchat` |
| **Webhook** | 릴레이(Core /inbound로 전달) | `python -m channels.run webhook` |

**인증(Core를 인터넷에 노출할 때):** `config/core.yml`에서 **auth_enabled: true**와 **auth_api_key** 설정; **POST /inbound** 및 **WebSocket /ws**에는 **X-API-Key** 또는 **Authorization: Bearer** 필요. **docs/RemoteAccess.md** 참조.

---

### 3.1 CLI(터미널)

**용도**: Core가 실행 중인 같은 머신에서 어시스턴트와 대화. **실행**: `python main.py`, 메시지 입력 후 Enter; 응답은 같은 터미널에 출력. **설정**: 로컬 CLI용 user.yml에 자신을 추가할 필요 없음(로컬 발신자는 허용 처리). 접두사: `+` 기억 저장, `?` 기억 검색, `quit` 종료, `llm` 목록/설정.

### 3.2 Email

**용도**: 이메일로 어시스턴트에게 보내면 회신이 이메일로 옴. **설정**: `config/email_account.yml`(IMAP/SMTP 및 자격 증명), `config/user.yml`(이메일 및 EMAIL 권한), `channels/emailChannel/config.yml`(선택). **실행**: Core를 먼저 시작한 뒤 이메일 채널 시작(배포 또는 메인 문서 참조).

### 3.3 Matrix, Tinode, WeChat, WhatsApp(풀 채널)

**용도**: 일반 IM으로 어시스턴트와 대화; 각각 **별도 프로세스**로 IM에 로그인/연결하고 메시지를 Core로 전달. **설정**: 각 채널 폴더에 `config.yml` 및 `.env`(자격 증명); `config/user.yml`에 허용 im 식별자 및 permissions; `channels/.env`에 **core_host**, **core_port**. **실행**: Core를 먼저, 그다음 해당 채널(각 채널 README 참조). 채널은 Core에 등록하고 HTTP 콜백으로 응답 수신.

### 3.4 Inbound API(임의 봇, 새 채널 코드 불필요)

**용도**: 임의 봇(Telegram, Discord, Slack, n8n, 자체 스크립트)이 “메시지당 HTTP 요청 1회”로 Core에 연결. **설정**: `config/user.yml`에 봇이 보낼 **user_id**(예: `telegram_123456789`)를 **im**에 추가하고 IM 권한 부여; 봇이 `http://<core_host>:<core_port>/inbound`로 POST 가능해야 함; 노출 시 auth 설정은 선택, docs/RemoteAccess.md 참조. **요청**: `POST /inbound`, JSON 본문 `{ "user_id", "text", "channel_name?", "user_name?" }`. **응답**: `{ "text": "..." }`. 예: `channels/telegram/`(BotFather에서 토큰 발급, .env 및 user.yml 설정, `python -m channels.run telegram`).

### 3.5 Webhook 채널(Core에 도달 불가 시 릴레이)

**용도**: Core가 홈 LAN에만 있고 봇이 다른 곳/인터넷에 있을 때, 봇과 Core 모두에 도달 가능한 호스트에서 **Webhook** 실행; 봇이 Webhook에 POST하면 Webhook이 Core로 전달해 응답 반환. **설정**: `channels/.env`에 **core_host**, **core_port**; user.yml은 Inbound와 동일. **실행**: `python -m channels.run webhook`, 기본 포트 8005. 요청: `POST http://<webhook_host>:8005/message`, 본문은 /inbound와 동일, 응답 `{ "text": "..." }`.

### 3.6 WebSocket(자체 클라이언트용)

**용도**: 전용 클라이언트(예: 브라우저 WebChat)가 Core와 하나의 연결 유지. **엔드포인트**: `ws://<core_host>:<core_port>/ws`. **프로토콜**: JSON 전송 `{ "user_id", "text" }`, 수신 `{ "text", "error" }`. **설정**: user_id 허용 목록 동일; auth_enabled 시 WebSocket 핸드셰이크 헤더에 X-API-Key 또는 Authorization: Bearer 전송.

### 3.7 문제 해결: "Connection error when sending to http://127.0.0.1:8005/get_response"

**Core**가 **Matrix(또는 다른 풀) 채널**의 `/get_response`로 응답을 POST하려 하는데 해당 주소에서 아무것도 리스닝하지 않음. **원인**: 풀 채널은 **별도 프로세스**로 실행; 채널이 **실행 중**이어야 하고 Core에 등록한 포트에서 리스닝해야 함. **조치**: 별도 터미널에서 `python -m channels.run matrix` 등; Core를 먼저, 그다음 채널; Core와 채널이 다른 머신이면 채널 `config.yml`의 **host**를 Core에서 도달 가능한 IP로(0.0.0.0은 Core가 127.0.0.1로 변환하므로 사용 안 함).

---

## 4. 어디서나 접근(요약)

| 목표 | 방법 |
|------|------|
| 휴대폰에서 이메일로 | **Email** 채널: Core 계정으로 이메일 발송, 회신은 이메일로. |
| 휴대폰에서 IM으로 | **Matrix/Tinode/WeChat/WhatsApp**: 해당 채널 실행; 또는 **Telegram 등 봇**이 **Core /inbound** 또는 **Webhook /message**에 POST(Core가 홈에만 있으면 Webhook을 릴레이에 둠). |
| 같은 LAN 브라우저에서 | **WebSocket /ws** 또는 WebChat 사용. |
| 어디서나 브라우저에서 | **Tailscale** 또는 **SSH 터널**로 Core(또는 Webhook) 노출 후 WebSocket 또는 Web UI 사용. |

**연결성**: 요청을 보내는 앱이 Webhook 또는 Core에 도달할 수 있어야 함; Webhook이 Core와 다른 머신에 있으면 Webhook 머신에서 Core에 도달 가능해야 함(리버스 SSH, Tailscale 등). §4.1 참조.

---

# 2부 — 개발자용

## 1. 현재 채널 설계

**두 패턴**: (1) **풀 채널** — BaseChannel을 구현하는 프로세스; Core에 등록하고 **PromptRequest** 전송; **POST /get_response**로 비동기 응답 수신 또는 **POST /local_chat**로 동기 응답 수신(Email, Matrix, Tinode, WeChat, WhatsApp, CLI). (2) **최소(inbound/WebSocket)** — BaseChannel 없음; 클라이언트가 Core에 최소 페이로드를 보내 동기 응답 수신(**POST /inbound**, **WebSocket /ws**, 선택적 **Webhook** 릴레이). 둘 다 **config/user.yml**로 권한 관리. **계약**: 풀 → POST /process(PromptRequest), POST /local_chat; 최소 → POST /inbound(InboundRequest), WebSocket /ws. **Webhook**: 포트(기본 8005)에서 리스닝, POST /message를 Core /inbound로 전달, `{ "text": "..." }` 반환. 코드: `channels/webhook/channel.py`.

## 2. 다른 에이전트와 비교

HomeClaw: Core + 독립 채널 프로세스(또는 외부 봇); IM 채널, POST /inbound, Webhook, WebSocket /ws로 연결. 채널 코드는 **channels/**에 있고 Core와 분리. 다른 에이전트: 단일 Gateway 프로세스 내에서 모든 채널; Tailscale/SSH로 Gateway에 원격 접속. 우리는 최소 API, 선택적 Webhook, 로컬 LLM + RAG를 유지하고, 모든 IM을 리포지터리 내에서 구현할 필요는 없음.

## 3. 현재 기능

풀 채널: Email, Matrix, Tinode, WeChat, WhatsApp, CLI; 최소 API: POST /inbound, WebSocket /ws; Webhook 릴레이; 예: channels/telegram/, discord/, slack/, `python -m channels.run <name>`. 문서: Design.md, Improvement.md, Comparison.md, Channel.md.

## 4. 있는 것과 개선 가능 항목

**이미 있음**: **Onboarding** `python main.py onboard`; **Doctor** `python main.py doctor`; **원격 접근 및 인증** docs/RemoteAccess.md. **개선 가능**: Core+채널을 한 번에 시작하는 단일 진입점, 선택적 페어링, WebChat(channels/webchat/ 이미 있음).

## 5. 참고

- **Design**: `Design.md`
- **새 채널 작성 방법**: **docs/HowToWriteAChannel.md** (풀 채널 vs webhook/inbound, 두 가지 방법)
- **Improvement**: `Improvement.md`; **Comparison**: `Comparison.md`; **RemoteAccess**: **docs/RemoteAccess.md**
- **채널 사용**: `channels/README.md`, `channels/webhook/README.md`, `channels/telegram/README.md`
