# HomeClaw — 設計ドキュメント

このドキュメントは **HomeClaw** のアーキテクチャ、コンポーネント、データフローを説明します。プロジェクトの理解と今後の開発のためのベースとなる参照です。

**他言語：** [English](Design.md) | [简体中文](Design_zh.md) | [한국어](Design_kr.md)

---

## 1. プロジェクト概要

### 1.1 目的

**HomeClaw** は**ローカルファーストの AI アシスタント**であり、以下を満たします。

- ユーザーのマシン（例：自宅 PC）で動作する。
- **ローカル LLM**（llama.cpp サーバ経由）と**クラウド AI**（OpenAI 互換 API、**LiteLLM** 使用）をサポートする。
- **複数チャネル**（メール、IM、CLI）でアシスタントを公開し、どこからでも（例：スマートフォンから）自宅インスタンスとやり取りできる。
- **RAG 型メモリ**を使用：**Cognee**（デフォルト）または自前 SQLite + Chroma；オプションでユーザーごとの**プロフィール**と**ナレッジベース**。docs_design/MemoryAndDatabase.md 参照。
- **プラグイン**（plugin.yaml + config.yml + plugin.py；route_to_plugin または orchestrator）、**スキル**（config/skills/ 下の SKILL.md；オプションでベクトル検索；run_skill ツール）、**ツール層**（use_tools: true — exec、browser、cron、sessions_*、memory_*、file_* など）で振る舞いを拡張。docs_design/ToolsSkillsPlugins.md 参照。

### 1.2 設計目標

- **ローカルファースト**：主にローカルハードウェアで動作；クラウドはオプション。
- **シンプルなデプロイ**：最小限の依存（デフォルトで SQLite、Chroma、重い DB なし）。
- **チャネル非依存**：メール、Matrix、Tinode、WeChat、WhatsApp、CLI のいずれで接続しても同じ Core。
- **拡張可能**：プラグインで機能追加；将来的に専用 HomeClaw チャネルの可能性。
- **マルチモデル**：チャット用と埋め込み用で異なるモデル；設定で複数モデルを読み込み可能。

---

## 2. 高レベルアーキテクチャ

（図は Design.md §2 と同じ：Channels → Core Engine → LLM Layer → Memory。Cognee デフォルトまたは SQLite + Chroma；オプションで profile、KB。）

- **チャネル**はユーザー入力を `PromptRequest` として HTTP で **Core** に送る。
- **Core** は自ら処理（チャット + メモリ/RAG）するか、**プラグイン**にルーティングする。
- **LLM** 呼び出しは単一エンドポイント：ローカル llama.cpp サーバまたは LiteLLM プロキシ（同一の OpenAI 互換 API）。
- **Memory** はチャットと RAG 用のベクトル化知識を保存する。

---

## 3. コアコンポーネント

### 3.1 Core エンジン（`core/`）

- **役割**：中央ルーター、権限チェック、チャット + メモリのハンドラ。
- **エントリ**：`core/core.py` — `Core`（シングルトン）が FastAPI アプリを実行し LLM マネージャを起動。
- **主なエンドポイント**：`POST /process`、`POST /local_chat`、`POST /inbound`、`WebSocket /ws`、`POST /register_channel`、`POST /deregister_channel`。
- **設定**：`config/core.yml`（host、port、main_llm、embedding_llm、memory_backend、use_tools、use_skills、tools.*、result_viewer、auth_enabled、auth_api_key など）。**認証**：auth_enabled: true のとき /inbound と /ws に X-API-Key または Authorization: Bearer が必要。docs_design/RemoteAccess.md 参照。**結果ビューア**：オプションの save_result_page ツールとレポートサーバ（port、base_url）。docs_design/ComplexResultViewerDesign.md 参照。

**Orchestrator**（`core/orchestrator.py`）：チャット履歴とユーザー入力から意図（TIME/OTHER）を分類；OTHER のとき Core がプラグインを選択。**TAM**（`core/tam.py`）：時間意識モジュール；TIME 意図（スケジューリングなど）を処理。ルーティングスタイルは core.yml の **orchestrator_unified_with_tools** で制御（デフォルト true = メイン LLM がツール付きでルーティング；false = 別途 orchestrator が先に 1 回 LLM 呼び出し）。

**1 Core、複数 LLM（ローカル + クラウド）**：設定で `local_models`、`cloud_models`；`main_llm`、`embedding_llm` は参照（例：local_models/xxx または cloud_models/xxx）。実行時 Util.main_llm()、Util.get_llm(name) で解決；オプションの llm_name で呼び出しごとにモデルを切り替え可能。**sessions_spawn** ツールで llm_name を指定し別モデルでワンショット子タスクを実行可能。

**1 エージェントと複数エージェント**：現在は**1 エージェント**（1 つの identity、ツールセット、スキルセット）；複数エージェント（各エージェントが identity、ツール/スキルのサブセット、オプションでデフォルト LLM）へ拡張可能。推奨デフォルトは「1 エージェント、複数 LLM」。

### 3.2 チャネル（`channels/`、`main.py`、Core `/inbound` と `/ws`）

ユーザーまたはボットが Core に届く経路。**フルチャネル**（別プロセス、BaseChannel、非同期/同期返答）と**最小**（BaseChannel プロセスなし、POST /inbound または WebSocket /ws で同期返答）の 2 パターン。権限は `config/user.yml` で統一。

**既存チャネル**：Email、Matrix、Tinode、WeChat、WhatsApp、Telegram、Discord、Slack、WebChat、Google Chat、Signal、iMessage、Teams、Zalo、Feishu、DingTalk、BlueBubbles、CLI（main.py）。任意のチャネル実行：`python -m channels.run <name>`。詳細は Design.md §3.2 参照。

**Webhook と WebSocket**：Core `POST /inbound`（最小 HTTP API）；Webhook チャネル `POST /message` で中継；Core `WebSocket /ws` で自前クライアント（WebChat など）。新規ボットは Core `/inbound` または Webhook `/message` に `{ user_id, text }` を POST し、返却された text をユーザーに送る；user.yml に user_id を登録。

### 3.3 LLM 層（`llm/`）

- **役割**：ローカルとクラウドの LLM を、Core が使う 1 つの OpenAI 互換 API に統一。
- **設定**：`config/core.yml` の `llama_cpp`、`local_models`（配列）、`cloud_models`（配列）と選択された `main_llm`、`embedding_llm`（id 指定）。ローカル：llama-server を各エントリの host/port で起動；バイナリは **llama.cpp-master/** のプラットフォーム別サブフォルダから自動選択。llama.cpp-master/README.md 参照。クラウド：LiteLLM；各 cloud_models エントリに **api_key_name** があり、Core の実行環境で**同名の環境変数**を設定；core.yml にキーを書かないこと。

### 3.4 メモリ（`memory/`）

- **役割**：チャット履歴 + RAG（現在クエリに関連する過去コンテンツの保存と検索）。
- **設計**：**Cognee（デフォルト）**：デフォルトで SQLite + ChromaDB + Kuzu；Cognee `.env` で Postgres、Qdrant などに対応。**自前（chroma）**：core.yml で SQLite + Chroma + オプションで Kuzu/Neo4j。docs_design/MemoryAndDatabase.md 参照。
- **memory_backend**：`cognee`（デフォルト）または `chroma`。cognee 時は **cognee:** および/または Cognee `.env` で設定；chroma 時は core.yml の vectorDB、graphDB を使用。**database** は常に Core のチャットセッション、runs、ターンに使用。**profile**（オプション）：ユーザーごと JSON；profile.enabled、profile.dir。**knowledge_base**（オプション）：RAG メモリとは別；knowledge_base.enabled、knowledge_base.backend。
- **ワークスペースブートストラップ（オプション）**：`config/workspace/` の IDENTITY.md、AGENTS.md、TOOLS.md；base/workspace.py で読み込みシステムプロンプトに付加。core.yml：use_workspace_bootstrap、workspace_dir。
- **セッション記録**：ChatHistory.get_transcript、get_transcript_jsonl、prune_session、Core.summarize_session_transcript など。Comparison.md §7.6 参照。
- **最終チャネル保存**：base/last_channel.py — save_last_channel、get_last_channel；channel_send とプラグインの返信を正しいチャネルに届けるため。

### 3.5 プラグイン（`plugins/`）

- **役割**：Core が汎用チャット + RAG で直接答えない場合、**route_to_plugin** または orchestrator で**プラグインにルーティング**して処理。

**組み込みプラグイン vs 外部プラグイン**

| タイプ | 言語 | 実行場所 | マニフェスト | 用途 |
|--------|------|----------|--------------|------|
| **組み込み** | Python のみ | Core と同プロセス | `plugin.yaml` で **type: inline**、`config.yml`、`plugin.py`（BasePlugin 継承）を `plugins/<Name>/` に配置 | 高速統合、追加プロセスなし、Python ライブラリ利用（Weather、News、Mail など）。 |
| **外部** | 任意（Node.js、Go、Java など） | 別プロセスまたはリモート HTTP サービス | `plugins/` 下のフォルダに `plugin.yaml` で **type: http**、または **POST /api/plugins/register** で登録 | 既存サービス、他言語、独立デプロイ；サーバが POST PluginRequest を受け取り PluginResult を返す。 |

Core は `plugins/` をスキャンして plugin.yaml + plugin.py を読み込み**組み込み**プラグインを発見；**外部**プラグインはフォルダ内の宣言（plugin.yaml type: http + エンドポイント URL）または実行時 API で登録。どちらも同じルーティング（orchestrator または route_to_plugin）。**docs_design/PluginsGuide.md**（§2 組み込み、§3 外部）、**docs_design/PluginStandard.md**、**docs_design/RunAndTestPlugins.md** 参照。

- **マニフェスト**：**plugin.yaml**（id、name、description、**type: inline** または **type: http**、capabilities とパラメータ）。**config.yml** で実行時設定。**plugin.py**（組み込みのみ）— BasePlugin 継承、run() および/または能力メソッドを実装。**読み込み**：PluginManager が plugins/ をスキャンし plugin.yaml（および type: inline のとき plugin.py）を読み込み説明を登録；Core は LLM でユーザーテキストにマッチするプラグインまたは **route_to_plugin** を実行し、組み込みは plugin.run()、外部は HTTP POST。

### 3.6 プラグインとツール：違いと設計

**プラグイン** = メッセージを 1 つのハンドラにルーティングし、実行して応答を返す。**ツール** = モデルが名前と構造化引数で関数を呼び出し；実行結果を会話に追加し、モデルが続けて呼び出しまたは返答。HomeClaw は**ツール層**を実装済み（exec、browser、cron、sessions_*、memory_*、file_*、document_read、web_search、run_skill、route_to_plugin、route_to_tam、save_result_page、models_list、agents_list、channel_send、image；remind_me、record_date、recorded_events_list；profile_*、knowledge_base_*；tavily_extract/crawl/research、web_extract、web_crawl、web_search_browser、http_request など）；nodes/canvas は対象外。一覧は **Design.md §3.6** 参照。**docs_design/ToolsSkillsPlugins.md**、**Comparison.md** §7.10.2 参照。

- **実装**：`base/tools.py`（ToolDefinition、ToolContext、ToolRegistry）、`tools/builtin.py`（register_builtin_tools）；Core は initialize() で登録し、answer_from_memory で use_tools が true のときツール付きで呼び出し tool_calls ループを実行。**設定**：core.yml で **use_tools: true** と **tools:**（exec_allowlist、file_read_base、tools.web、browser_*、run_skill_* など）。**docs_design/ToolsDesign.md**、**docs_design/ToolsAndSkillsTesting.md** 参照。新規ツール：execute_async を定義、ToolDefinition を組み立て、register_builtin_tools 内または get_tool_registry().register(tool) で登録。

---

## 4. エンドツーエンドフロー

### 4.1 ユーザーがメッセージを送る（例：メールまたは IM）

チャネルがメッセージを受信 → PromptRequest を構築 → Core に POST /process（CLI は POST /local_chat）→ Core が権限チェック → orchestrator 有効時は意図分類とプラグイン選択・実行、または Core が処理 → Core が処理する場合：チャット履歴を読み込み、オプションでメモリにエンキュー、answer_from_memory（メモリ取得 Cognee/Chroma、LLM 呼び出し；use_tools 時は tool_calls ループ実行）、チャット DB に書き込み、AsyncResponse を response_queue にプッシュ → チャネルが /get_response で受け取りユーザーに配信。

### 4.2 ローカル CLI（`main.py`）

ユーザーが main.py を実行してコンソールに入力；Core はバックグラウンドスレッドで動作；CLI は local_chat（同期）を使い、応答は HTTP ボディで返りコンソールに表示。プレフィックス `+`/`?` でメモリの保存/検索にマッピング可能。

---

## 5. 設定サマリ

| ファイル | 目的 |
|----------|------|
| `config/core.yml` | **単一設定**：host/port、model_path、local_models、cloud_models、main_llm、embedding_llm、memory_backend、cognee:、database、vectorDB/graphDB（chroma 時）、use_memory、use_workspace_bootstrap、workspace_dir、use_tools、tools:、use_skills、skills_dir、skills_use_vector_search、profile、knowledge_base、result_viewer、auth_enabled、auth_api_key など。HOW_TO_USE.md 参照。 |
| `config/user.yml` | 許可リスト：ユーザー（id、name、email、im、phone、permissions）；チャット/メモリ/プロフィールはすべてシステムユーザー id で区別。 |
| `config/email_account.yml` | メールチャネル用 IMAP/SMTP と認証情報。 |
| `channels/.env` | CORE_URL、各チャネルのボットトークン。 |

Core は core.yml から main_llm、embedding_llm（id）を読み、**local_models** または **cloud_models** から host/port とタイプを解決。ローカルモデルの path は **model_path** に対する相対パス。llama.cpp サーババイナリは **llama.cpp-master/** のプラットフォーム別サブフォルダ（mac/、win_cuda/、linux_cpu/ など）に配置。llama.cpp-master/README.md 参照。クラウド API キー：各 cloud モデルの **api_key_name** と同じ名前の**環境変数**を設定（例：OPENAI_API_KEY）。

---

## 6. 拡張ポイントと今後の作業

- **チャネル**：最小 — 任意ボットが POST /inbound または Webhook /message；フル — channels/ に BaseChannel サブクラスを追加し /get_response を実装。専用アプリは WebSocket /ws を使用可能。
- **LLM**：core.yml の local_models または cloud_models にエントリを追加；ローカルはエントリごとに llama-server を起動。
- **メモリ/RAG**：デフォルトは Cognee；代替は memory_backend: chroma。docs_design/MemoryAndDatabase.md 参照。
- **プラグイン**：plugins/ 下にフォルダを追加し plugin.yaml、config.yml、plugin.py（組み込み）または type: http + エンドポイント（外部）；外部は POST /api/plugins/register も可。docs_design/PluginsGuide.md、docs_design/PluginStandard.md、docs_design/RunAndTestPlugins.md 参照。
- **ツール層**：§3.6 参照；組み込みツールは実装済み；オプションでプラグインが get_tools()/run_tool() でツールを公開可能。
- **スキル（SKILL.md）**：実装済み；base/skills.py が config/skills/ から読み込み；use_skills、skills_dir、skills_use_vector_search；run_skill ツール。docs_design/SkillsGuide.md、docs_design/ToolsSkillsPlugins.md 参照。
- **TAM**：時間意図は分類済み；スケジューリング/リマインダーの拡張が可能。

---

## 7. キーファイルクイックリファレンス

| 領域 | キーファイル |
|------|--------------|
| Core | core/core.py、core/coreInterface.py、core/orchestrator.py、core/tam.py |
| Channels | base/BaseChannel.py、base/base.py（InboundRequest）、channels/、main.py。実行：`python -m channels.run <name>`。 |
| LLM | llm/llmService.py、llm/litellmService.py |
| Memory | memory/base.py、memory/mem.py、memory/chroma.py、memory/storage.py、memory/embedding.py、memory/chat/chat.py；memory/graph/（chroma 時）；memory/cognee_adapter.py（cognee 時）；base/profile_store.py、database/profiles/；ナレッジベースは core.yml 参照。ワークスペース：base/workspace.py、config/workspace/。スキル：base/skills.py、config/skills/；run_skill は tools/builtin.py。docs_design/MemoryAndDatabase.md、docs_design/SkillsGuide.md 参照。 |
| Tools | base/tools.py、tools/builtin.py；設定は core.yml tools:。docs_design/ToolsDesign.md、docs_design/ToolsAndSkillsTesting.md 参照。 |
| Plugins | base/BasePlugin.py、base/PluginManager.py、plugins/Weather/（plugin.yaml、config.yml、plugin.py）；外部：POST /api/plugins/register。docs_design/PluginsGuide.md、docs_design/PluginStandard.md 参照。 |
| Shared | base/base.py（PromptRequest、AsyncResponse、列挙、設定データクラス）、base/util.py |

---

この Design.md は現在のコードベースを反映し、HomeClaw のさらなる開発とリファクタリングのためのベースドキュメントとして用意されています。
