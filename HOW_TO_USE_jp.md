# HomeClaw の使い方

このガイドでは、HomeClaw の**インストール**、**設定**、**利用方法**を説明します。環境構築、コア・ユーザー設定、ローカル／クラウドモデル、メモリ、ツール、ワークスペース、テスト、プラグイン、スキルを扱います。

**他言語：** [English](HOW_TO_USE.md) | [简体中文](HOW_TO_USE_zh.md) | [한국어](HOW_TO_USE_kr.md)

---

## 目次

1. [概要](#1-概要)
2. [インストール](#2-インストール)
3. [設定](#3-設定)
4. [ローカル GGUF モデル](#4-ローカル-gguf-モデル)
5. [クラウドモードと API キー](#5-クラウドモードと-api-キー)
6. [メモリシステム](#6-メモリシステム)
7. [個別ツール（Web検索・ローカルファイル）](#7-個別ツールweb検索ローカルファイル)
8. [ワークスペースファイル（config/workspace）](#8-ワークスペースファイル-configworkspace)
9. [システムのテスト](#9-システムのテスト)
10. [プラグイン](#10-プラグイン)
11. [スキル](#11-スキル)

---

## 1. 概要

HomeClaw は自機で動く**ローカルファーストの AI アシスタント**です。**チャネル**（WebChat、Telegram、Discord、メール等）で会話します。単一の **Core** プロセスが全チャネルを扱い、**メモリ**（RAG + チャット履歴）を保持し、**ローカル**（llama.cpp、GGUF）または**クラウド**（OpenAI、Gemini、DeepSeek 等）モデルを使えます。**プラグイン**で天気・ニュース・メール等の機能を追加し、**スキル**で LLM がツールを使って実行するワークフロー（例：ソーシャルメディアエージェント）を追加します。

- **Core の起動：** `python main.py`（または `python main.py core`）— Core はポート 9000 で待ち受けます。
- **チャネルの起動：** 例：`python main.py webchat`、または Core の `/inbound` や WebSocket に送るチャネルプロセスを起動します。
- **CLI：** `python main.py` は `llm set`、`llm cloud` などのサブコマンドと、ワークスペース・LLM・チャネル・スキルを対話で設定する**オンボーディング**（`python main.py onboard`）をサポートします。

アーキテクチャと機能は主 [README.md](README.md) を参照してください。

---

## 2. インストール

### 2.1 Python と依存関係

- **Python：** 3.10+ を推奨。
- **requirements からインストール：**

  ```bash
  pip install -r requirements.txt
  ```

  コア依存には `loguru`、`PyYAML`、`fastapi`、`openai`、`litellm`、`chromadb`、`sqlalchemy`、`aiohttp`、`httpx`、`cognee` などが含まれます。詳細は [requirements.txt](requirements.txt) を参照。

### 2.2 オプション

- **ブラウザツール（Playwright）：** `browser_navigate`、`browser_snapshot` 等用。`pip install playwright` の後：
  ```bash
  python -m playwright install chromium
  ```
- **Web検索（キー不要）：** `duckduckgo-search` は requirements に含まれます。`tools.web.search.provider: duckduckgo` と `fallback_no_key: true` でキーなし検索が可能です。
- **ドキュメント処理（file_read / document_read）：** requirements の `unstructured[all-docs]` で PDF、Word、HTML 等を扱います。
- **グラフDB（自前 RAG）：** `memory_backend: chroma` 時に `kuzu` を使用。Neo4j を使う場合は requirements の `neo4j` のコメントを外します。
- **チャネル：** 一部チャネルは追加パッケージが必要（例：WeChat `wcferry`、WhatsApp `neonize`）。requirements のコメントを参照。

### 2.3 環境

- **仮想環境**（例：`python -m venv venv` の後 `source venv/bin/activate` または `venv\Scripts\activate`）の利用を推奨します。
- **クラウドモデル**利用時は **API キー用の環境変数**を設定します（[§5](#5-クラウドモードと-api-キー) 参照）。

---

## 3. 設定

主な設定ファイルは **`config/core.yml`**（Core の動作、LLM、メモリ、ツール）と **`config/user.yml`**（利用可能なユーザーとその識別子）です。

### 3.1 core.yml（概要）

- **Core サーバ：** `host`、`port`（デフォルト 9000）、`mode`。
- **パス：** `model_path`（GGUF のベースディレクトリ）、`workspace_dir`（デフォルト `config/workspace`）、`skills_dir`（デフォルト `skills`）。
- **機能：** `use_memory`、`use_tools`、`use_skills`、`use_workspace_bootstrap`、`memory_backend`（例：`cognee` または `chroma`）。
- **LLM：** `local_models`、`cloud_models`、`main_llm`、`embedding_llm`（[§4](#4-ローカル-gguf-モデル) と [§5](#5-クラウドモードと-api-キー) 参照）。
- **メモリ：** `memory_backend`、`cognee:`（Cognee 利用時）、または `database`、`vectorDB`、`graphDB`（`memory_backend: chroma` 時）。[§6](#6-メモリシステム) 参照。
- **ツール：** `tools` セクション：`file_read_base`、`file_read_max_chars`、`web`（検索プロバイダ・API キー）、`browser_enabled`、`browser_headless` 等。[§7](#7-個別ツールweb検索ローカルファイル) 参照。
- **結果ビューア：** `result_viewer`（有効化、ポート、レポートリンク用 base_url）。
- **ナレッジベース：** `knowledge_base`（有効化、バックエンド、チャンク設定）。

環境に合わせて `config/core.yml` を編集します（パス、ポート、プロバイダ）。

### 3.2 user.yml（許可リストと識別子）

- **目的：** チャネル経由で Core と会話できる**ユーザー**を定義します。チャット・メモリ・プロファイルはすべて**システムユーザー id** で紐付きます。
- **構造：** `users` のリスト。各ユーザーに：
  - **id**（任意、デフォルトは `name`）、**name**（必須）。
  - **email：** メールアドレスリスト（メールチャネル用）。
  - **im：** `"<チャネル>:<id>"` のリスト（例：`matrix:@user:matrix.org`、`telegram:123456`、`discord:user_id`）。
  - **phone：** 番号リスト（SMS/電話用）。
  - **permissions：** 例：`[IM, EMAIL, PHONE]` または `[]` で全て許可。
- **例：**

  ```yaml
  users:
    - id: me
      name: Me
      email: [me@example.com]
      im: [telegram:123456, matrix:@me:matrix.org]
      phone: []
      permissions: []
  ```

`user.yml` のいずれかのエントリとチャネル識別子が一致するユーザーのみ許可されます。詳細は **docs/MultiUserSupport.md** を参照。

---

## 4. ローカル GGUF モデル

### 4.1 モデルの配置

- **ベースディレクトリ：** `config/core.yml` の **`model_path`**（デフォルト `../models/`）が GGUF のルートです。**`local_models`** の **path** は **`model_path` からの相対パス**（絶対パスも可）です。
- GGUF ファイルはそのルート以下に置きます（例：プロジェクトルートの `models/` や `../models/`）。

### 4.2 ローカルモデルの定義（埋め込み + メイン）

**`config/core.yml`** の **`local_models`** に、モデルごとに 1 エントリ追加します：

- **id**、**alias**、**path**（`model_path` からの相対パス）、**host**、**port**、**capabilities**（例：`[Chat]` または `[embedding]`）。
- **埋め込み：** `capabilities: [embedding]` を 1 つ；**`embedding_llm`** を `local_models/<id>` に設定。
- **チャット：** `capabilities: [Chat]` を 1 つ以上；**`main_llm`** を `local_models/<id>` に設定。

例：

```yaml
local_models:
  - id: embedding_text_model
    alias: embedding
    path: bge-m3-Q5_K_M.gguf
    host: 127.0.0.1
    port: 5066
    capabilities: [embedding]
  - id: Qwen3-14B-Q5_K_M
    alias: Qwen3-14B-Q5_K_M
    path: Qwen3-14B-Q5_K_M.gguf
    host: 127.0.0.1
    port: 5023
    capabilities: [Chat]

main_llm: local_models/Qwen3-14B-Q5_K_M
embedding_llm: local_models/embedding_text_model
```

### 4.3 llama.cpp サーバの起動

- 各モデルごとに、設定した `host` と `port` で **llama.cpp サーバを 1 つ**起動します。config の `path`（`model_path` からの相対）と同じパスを使います。
- 例（プロジェクトルートで `model_path: ../models/`）：`llama-server`（またはビルド）を `-m <path>` とポートで起動。プラットフォーム別は **llama.cpp-master/README.md** を参照。
- **動作確認済み：** 埋め込み **bge-m3-Q5_K_M.gguf**、チャット **Qwen3-14B-Q5_K_M.gguf**。ローカル RAG と会話に適しています。

### 4.4 モデルサイズと量子化の選び方

- **CPU のみ：** 小さいモデル（1.5B–7B）と高い量子化（Q4_K_M、Q5_K_M）を推奨。14B+ は遅くなる場合があります。
- **GPU（例：8GB VRAM）：** 7B–14B の Q4/Q5 が一般的。32B は Q4 や offload が必要な場合があります。
- **GPU（16GB+ VRAM）：** 14B–32B を Q5 や Q8 で運用可能。
- モデルファイルと llama.cpp プロセス用に十分なシステム RAM を確保してください（おおよそファイルサイズの 1–1.5 倍）。

---

## 5. クラウドモードと API キー

### 5.1 クラウドモデルの利用

- **`config/core.yml`** の **`cloud_models`** にクラウドプロバイダ（OpenAI、Gemini、Anthropic、DeepSeek 等）を列挙します。各エントリに **id**、**path**（例：`openai/gpt-4o`）、**host**、**port**、**api_key_name**、**capabilities** を指定します。
- **`main_llm`** または **`embedding_llm`** を `cloud_models/<id>`（例：`cloud_models/OpenAI-GPT4o`）にするとそのモデルを使います。
- クラウド API との通信には **LiteLLM** を使用します。プロバイダごとに LiteLLM プロキシを起動するか、1 つのプロキシで複数対応するかは `host`/`port` の設定で調整します。

### 5.2 API キー（環境変数）

- 各クラウドモデルエントリには **`api_key_name`**（例：`OPENAI_API_KEY`、`GEMINI_API_KEY`）があります。Core 起動前に**同じ名前の環境変数**に API キーを設定してください。
- 例：
  - OpenAI：`export OPENAI_API_KEY=sk-...`
  - Google：`export GEMINI_API_KEY=...`
  - Anthropic：`export ANTHROPIC_API_KEY=...`
  - DeepSeek：`export DEEPSEEK_API_KEY=...`
- **Ollama** エントリには `api_key_name` がありません（ローカル、キー不要）。
- バージョン管理する `core.yml` に API キーを書かないでください。環境変数またはローカル用の上書きファイルを使います。

### 5.3 ローカルとクラウドの切り替え

- 実行中は CLI の **`llm set`**（ローカル選択）や **`llm cloud`**（クラウド選択）でメインモデルを切り替えられます。または config の `main_llm` を変更して再起動しても構いません。

---

## 6. メモリシステム

### 6.1 バックエンド

- **`memory_backend: cognee`**（デフォルト）：Cognee がリレーショナル・ベクトル・グラフを担当します。**`cognee:`**（`config/core.yml` 内）および／または Cognee の **`.env`** で設定します。Cognee 利用時、core.yml の `vectorDB` と `graphDB` はメモリには**使われません**。
- **`memory_backend: chroma`：** 自前 RAG：Core は core.yml の **`database`**、**`vectorDB`**、オプションで **`graphDB`**（SQLite + Chroma + Kuzu/Neo4j）を使います。

### 6.2 Cognee（デフォルト）

- **`config/core.yml`** の **`cognee:`** で、リレーショナル（sqlite/postgres）、ベクトル（chroma）、グラフ（kuzu/neo4j）、およびオプションで LLM/embedding を設定できます。LLM/embedding を空にすると Core の **main_llm** と **embedding_llm**（同じ host/port）を使います。
- Cognee と chroma の対応や Cognee `.env` の詳細は **docs/MemoryAndDatabase.md** を参照してください。

### 6.3 メモリのリセット

- テスト用に RAG メモリを空にする：**`http://<core_host>:<core_port>/memory/reset`** に `GET` または `POST`（例：`curl http://127.0.0.1:9000/memory/reset`）。
- ナレッジベースを空にする：**`http://<core_host>:<core_port>/knowledge_base/reset`**。

---

## 7. 個別ツール（Web検索・ローカルファイル）

### 7.1 Web検索

- **`config/core.yml`** の **`tools.web.search`** で：
  - **provider：** `duckduckgo`（キー不要）、`google_cse`、`bing`、`tavily`、`brave`、`serpapi`。使用するものを指定。
  - **API キー：** `google_cse` は `api_key` と `cx`。`tavily` は `api_key`（または環境変数 `TAVILY_API_KEY`）。`bing`、`brave`、`serpapi` はそれぞれのブロックで設定。
  - **fallback_no_key：** `true` にすると、メインプロバイダが失敗またはキーがない場合に DuckDuckGo（キー不要）にフォールバックします。`duckduckgo-search`（requirements に含まれる）が必要です。

### 7.2 ローカルファイル処理

- **file_read / folder_list：** **`tools`** 内で：
  - **file_read_base：** ファイルアクセスのベースパス（`.` = カレントディレクトリ、または絶対パス）。モデルはこのベース以下のファイルのみ読みます。
  - **file_read_max_chars：** ツールが上限を渡さない場合の `file_read` の最大文字数（デフォルト 32000。長文は増やしてください）。
- **document_read（PDF、Word 等）：** `unstructured[all-docs]` インストール時に Unstructured を使用。同じベースパス。長い PDF は `file_read_max_chars` を増やしてください。

### 7.3 ブラウザツール

- **browser_enabled：** `false` でブラウザツールを無効にします（Web は `fetch_url` と `web_search` のみ）。
- **browser_headless：** `false` にするとブラウザウィンドウを表示します（ローカルテスト用）。Playwright と `playwright install chromium` が必要です。

---

## 8. ワークスペースファイル（config/workspace）

**ワークスペース**はプロンプト専用です。Markdown が**システムプロンプトに注入**され、LLM の役割と能力を伝えます。これらのファイルからはコードは実行されません。

### 8.1 ファイルと順序

- **`config/workspace/IDENTITY.md`** — アシスタントの役割（トーン、スタイル）。`## Identity` として注入。
- **`config/workspace/AGENTS.md`** — 高レベルな振る舞いとルーティングのヒント。`## Agents / behavior` として注入。
- **`config/workspace/TOOLS.md`** — 能力の人間向けリスト。`## Tools / capabilities` として注入。

この順で連結し、その後に RAG 応答テンプレート（メモリ）を追加します。詳細な流れとコツは **config/workspace/README.md** を参照。

### 8.2 設定

- **`config/core.yml`** で：**`use_workspace_bootstrap: true`** で注入を有効化；**`workspace_dir`**（デフォルト `config/workspace`）が読み込みディレクトリです。
- 上記 `.md` を編集して identity・振る舞い・能力の説明を調整します。変更を反映するには Core を再起動するか、キャッシュしない場合は新規メッセージを送ります。

### 8.3 コツ

- 各ファイルは短く保ち、プロンプトが肥大化しないようにします。
- ファイルを空にするか削除すると、そのブロックはスキップされます。

---

## 9. システムのテスト

### 9.1 簡単な確認

- Core 起動：`python main.py`（または `python main.py core`）。Core はポート 9000 で待ち受けます。
- WebChat 起動（有効な場合）：WebChat URL に接続してメッセージを送ります。`user.yml` で自分の識別子が許可されていることを確認してください。
- **メモリリセット：** `curl http://127.0.0.1:9000/memory/reset` で RAG を空にしてクリーンなテストができます。

### 9.2 ツールのトリガー

- **`use_tools: true`** のとき、LLM がツールを呼べます。よく使うトリガー例：
  - **time：** 「今何時？」
  - **memory_search：** 「私のことを何か覚えている？」
  - **web_search：** 「Web で … を検索して」
  - **file_read：** 「ファイル X を読んで」／「… の内容を要約して」
  - **cron_schedule：** 「毎日 9 時にリマインドして」
- ツール別の例文一覧は **docs/ToolsAndSkillsTesting.md** を参照。

### 9.3 テスト（pytest）

- テスト実行：プロジェクトルートで `pytest`。requirements に `pytest`、`pytest-asyncio`、`httpx` が含まれます。

---

## 10. プラグイン

プラグインは**単一機能**（天気、ニュース、メール等）を追加します。**組み込み**（Python、プロセス内）と**外部**（HTTP サービス）の両方があります。

- **利用・開発：** **docs/PluginsGuide.md** でプラグインの概念、書き方（plugin.yaml、config.yml、plugin.py）、外部プラグインの登録を説明しています。
- **実行・テスト：** **docs/RunAndTestPlugins.md** で Core、WebChat、登録、サンプルプロンプトの手順を説明しています。
- **パラメータ収集と設定：** **docs/PluginParameterCollection.md** で `profile_key`、`config_key`、`confirm_if_uncertain` を説明しています。
- **標準と登録：** **docs/PluginStandard.md**、**docs/PluginRegistration.md**。

---

## 11. スキル

**スキル**はタスク向けの指示パッケージ（SKILL.md + オプションのスクリプト）で、**ツール**を使って目標を達成する*方法*をアシスタントに伝えます。LLM が指示に従って実行するワークフローであり、別のプラグインコードではありません。

- **有効化：** **`config/core.yml`** で **`use_skills: true`** と **`skills_dir`**（デフォルト `skills`）を設定し、Core を再起動します。
- **スキルの追加：** `skills_dir` 以下にフォルダを作り、**SKILL.md**（名前、説明、本文）を置きます。オプションで `scripts/` にスクリプトを置き、**run_skill** で参照します。
- **ベクトル検索：** スキルが多い場合は **`skills_use_vector_search: true`** にすると、クエリごとに関連スキルのみが注入されます。オプションは **docs/SkillsGuide.md** を参照。
- **OpenClaw のスキルの流用：** OpenClaw は別の拡張モデル（チャネル／プロバイダ／スキルを 1 つの manifest で）を使います。HomeClaw のスキルは **SKILL.md + scripts** を `skills/` 以下に置く形式です。OpenClaw の「スキル」を HomeClaw で使うには、指示を **SKILL.md**（名前、説明、手順本文）にまとめて `skills/<スキル名>/` に置いてください。ツール利用の手順で表現できる場合はコードの移植は不要です。OpenClaw と HomeClaw の対比は **docs/ToolsSkillsPlugins.md** §2.7 を参照。

**スキル完全ガイド：** **docs/SkillsGuide.md**（構造、利用、実装、テスト）。**docs/ToolsSkillsPlugins.md** でツール／スキル／プラグインの全体設計を説明しています。
