# HomeClaw — チャネルガイド

チャネルはユーザー（またはボット）が HomeClaw Core に届く手段です。本文は二部構成：**第一部はユーザー向け**（チャネルの利用・設定）、**第二部は開発者向け**（設計、他エージェントとの比較、改善）。

**他の言語：** [English](Channel.md) | [简体中文](Channel_zh.md) | [한국어](Channel_kr.md)

---

# 第一部 — ユーザー向け

## 1. チャネルとは

**チャネル**は自宅 Core と話す手段です。

- **スマホや他端末から**：Email、Matrix、WeChat、WhatsApp、またはメッセージを Core に転送するボット（例：Telegram）。
- **同一マシンから**：ターミナルの CLI、または（将来）ブラウザの WebChat。

全チャネルが同一 Core と同一許可リストを使用：`config/user.yml` で誰がアシスタントと話せるかを設定。

---

## 2. 共通設定

### 2.1 誰が話せるか（IM・ボットに必須）

**`config/user.yml`** を編集。各ユーザーに **name**、**email**/**im**/**phone**（Core が入信にマッチする識別子）、**permissions**（EMAIL、IM、PHONE、または空で全許可）。**inbound 系ボット**（Telegram、Discord 等）：**im** に `telegram_<chat_id>` や `discord_<user_id>` を入れ、**permissions** に IM（または空で全許可）。**メール**チャネル：許可アドレスを **email** に、EMAIL を追加。

### 2.2 Core の場所（チャネルプロセス用）

チャネルプロセスは Core のアドレスが必要。**`channels/.env`** に設定：

```env
core_host=127.0.0.1
core_port=9000
mode=dev
```

チャネルが別マシンで動く場合はそのマシンの IP またはホスト名を使用。

---

## 3. 利用可能なチャネル

**対応チャネル一覧**

| チャネル | タイプ | 起動 |
|----------|--------|------|
| **CLI** | プロセス内 (local_chat) | `python main.py` |
| **Email** | フル (BaseChannel) | 別途起動；§3.2 参照。コード：`core/emailChannel/` または `channels/emailChannel/`。 |
| **Matrix, Tinode, WeChat, WhatsApp** | フル (BaseChannel) | `python -m channels.run matrix`（または tinode, wechat, whatsapp） |
| **Telegram, Discord, Slack** | Inbound (POST /inbound) | `python -m channels.run telegram`（または discord, slack） |
| **Google Chat, Signal, iMessage, Teams, Zalo, Feishu, DingTalk, BlueBubbles** | Inbound / HTTP / webhook | `python -m channels.run google_chat`（または signal, imessage, teams, zalo, feishu, dingtalk, bluebubbles） |
| **WebChat** | WebSocket /ws | `python -m channels.run webchat` |
| **Webhook** | リレー（Core /inbound に転送） | `python -m channels.run webhook` |

**認証（Core をインターネットに公開する場合）：** `config/core.yml` で **auth_enabled: true** と **auth_api_key** を設定；**POST /inbound** と **WebSocket /ws** には **X-API-Key** または **Authorization: Bearer** が必要。**docs/RemoteAccess.md** 参照。

---

### 3.1 CLI（ターミナル）

**用途**：Core が動いている同一マシンからアシスタントと会話。**起動**：`python main.py`、メッセージ入力して Enter；応答は同じターミナルに表示。**設定**：user.yml に自分を追加する必要なし（ローカル送信者は許可扱い）。プレフィックス：`+` 記憶保存、`?` 記憶検索、`quit` 終了、`llm` 一覧/設定。

### 3.2 Email

**用途**：メールでアシスタントに送信；返信はメールで届く。**設定**：`config/email_account.yml`（IMAP/SMTP と認証情報）、`config/user.yml`（メールアドレスと EMAIL 権限）、`channels/emailChannel/config.yml`（任意）。**起動**：Core を先に起動し、次にメールチャネル（デプロイまたはメインドキュメント参照）。

### 3.3 Matrix、Tinode、WeChat、WhatsApp（フルチャネル）

**用途**：通常の IM でアシスタントと会話；各チャネルは**別プロセス**で IM にログイン/接続し、メッセージを Core に転送。**設定**：各チャネルフォルダに `config.yml` と `.env`（認証情報）；`config/user.yml` に許可する im 識別子と permissions；`channels/.env` に **core_host**、**core_port**。**起動**：先に Core、次に該当チャネル（各チャネルの README 参照）。チャネルは Core に登録し、HTTP コールバックで応答を受信。

### 3.4 Inbound API（任意ボット、新チャネルコード不要）

**用途**：任意ボット（Telegram、Discord、Slack、n8n、自前スクリプト）が「1 メッセージ 1 HTTP リクエスト」で Core に接続。**設定**：`config/user.yml` にボットが送る **user_id**（例：`telegram_123456789`）を **im** に追加し IM 権限；ボットが `http://<core_host>:<core_port>/inbound` に POST 可能に；公開時は auth 設定任意、docs/RemoteAccess.md 参照。**リクエスト**：`POST /inbound`、JSON 体 `{ "user_id", "text", "channel_name?", "user_name?" }`。**レスポンス**：`{ "text": "..." }`。例：`channels/telegram/`（BotFather でトークン取得、.env と user.yml 設定、`python -m channels.run telegram`）。

### 3.5 Webhook チャネル（Core に届かない場合のリレー）

**用途**：Core が自宅 LAN のみでボットが別場所/インターネットにある場合、ボットと Core の両方に届くホストで **Webhook** を起動；ボットは Webhook に POST、Webhook が Core に転送して返答を返す。**設定**：`channels/.env` に **core_host**、**core_port**；user.yml は Inbound と同様。**起動**：`python -m channels.run webhook`、デフォルトポート 8005。リクエスト：`POST http://<webhook_host>:8005/message`、体は /inbound と同じ、レスポンス `{ "text": "..." }`。

### 3.6 WebSocket（自前クライアント用）

**用途**：専用クライアント（例：ブラウザ WebChat）が Core と 1 本の接続を維持。**エンドポイント**：`ws://<core_host>:<core_port>/ws`。**プロトコル**：JSON 送信 `{ "user_id", "text" }`、受信 `{ "text", "error" }`。**設定**：user_id 許可リストは同じ；auth_enabled 時は WebSocket ハンドシェイクヘッダで X-API-Key または Authorization: Bearer を送信。

### 3.7 トラブルシュート："Connection error when sending to http://127.0.0.1:8005/get_response"

**Core** が **Matrix（または他フル）チャネル**の `/get_response` に応答を POST しようとしているが、そのアドレスで何もリスンしていない。**原因**：フルチャネルは**別プロセス**で動作；チャネルが**起動中**で Core に登録したポートでリスンしている必要あり。**対処**：別ターミナルで `python -m channels.run matrix` 等；Core を先に、次にチャネル；Core とチャネルが別マシンの場合はチャネル `config.yml` の **host** を Core から到達可能な IP に（0.0.0.0 は Core が 127.0.0.1 に変換するため不可）。

---

## 4. どこからでもアクセス（まとめ）

| 目的 | 方法 |
|------|------|
| メールでスマホから | **Email** チャネル：Core のアカウントにメール送信、返信はメールで。 |
| IM でスマホから | **Matrix/Tinode/WeChat/WhatsApp**：該当チャネルを起動；または **Telegram 等ボット**が **Core /inbound** または **Webhook /message** に POST（Core が自宅のみの場合は Webhook をリレーに配置）。 |
| 同一 LAN のブラウザから | **WebSocket /ws** または WebChat を使用。 |
| どこからでもブラウザで | **Tailscale** または **SSH トンネル**で Core（または Webhook）を公開し、WebSocket または Web UI を使用。 |

**接続性**：リクエスト送信元が Webhook または Core に到達可能である必要あり；Webhook が Core と別マシンの場合は Webhook マシンから Core に到達可能に（リバース SSH、Tailscale 等）。§4.1 参照。

---

# 第二部 — 開発者向け

## 1. 現在のチャネル設計

**二パターン**：（1）**フルチャネル** — BaseChannel を実装するプロセス；Core に登録し **PromptRequest** を送信；**POST /get_response** で非同期に応答を受けるか **POST /local_chat** で同期で応答を受ける（Email、Matrix、Tinode、WeChat、WhatsApp、CLI）。（2）**最小（inbound/WebSocket）** — BaseChannel なし；クライアントが Core に最小ペイロードを送り同期で応答を受ける（**POST /inbound**、**WebSocket /ws**、任意で **Webhook** リレー）。両方とも **config/user.yml** で許可。**契約**：フル → POST /process（PromptRequest）、POST /local_chat；最小 → POST /inbound（InboundRequest）、WebSocket /ws。**Webhook**：ポート（デフォルト 8005）でリスン、POST /message を Core /inbound に転送、`{ "text": "..." }` を返す。コード：`channels/webhook/channel.py`。

## 2. 他エージェントとの比較

HomeClaw：Core + 独立チャネルプロセス（または外部ボット）；IM チャネル、POST /inbound、Webhook、WebSocket /ws で接続。チャネルコードは **channels/** にあり Core と分離。他：単一 Gateway プロセス内で全チャネル；Tailscale/SSH で Gateway にリモート接続。当方の方針：最小 API、任意 Webhook、ローカル LLM + RAG を維持し、全 IM をリポジトリ内で実装する必要はない。

## 3. 現在の機能

フルチャネル：Email、Matrix、Tinode、WeChat、WhatsApp、CLI；最小 API：POST /inbound、WebSocket /ws；Webhook リレー；例：channels/telegram/、discord/、slack/、`python -m channels.run <name>`。ドキュメント：Design.md、Improvement.md、Comparison.md、Channel.md。

## 4. 既にあるものと改善案

**既存**：**Onboarding** `python main.py onboard`；**Doctor** `python main.py doctor`；**リモートアクセスと認証** docs/RemoteAccess.md。**改善案**：Core+チャネルを一括起動する単一エントリポイント、任意のペアリング、WebChat（channels/webchat/ は既存）。

## 5. 参照

- **Design**：`Design.md`
- **新チャネルの書き方**：**docs/HowToWriteAChannel.md**（フルチャネル vs webhook/inbound、二つの方法）
- **Improvement**：`Improvement.md`；**Comparison**：`Comparison.md`；**RemoteAccess**：**docs/RemoteAccess.md**
- **チャネル利用**：`channels/README.md`、`channels/webhook/README.md`、`channels/telegram/README.md`
