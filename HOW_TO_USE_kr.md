# HomeClaw 사용 방법

이 가이드는 HomeClaw의 **설치**, **설정**, **사용** 방법을 설명합니다. 환경 구성, 코어·사용자 설정, 로컬·클라우드 모델, 메모리, 도구, 워크스페이스, 테스트, 플러그인, 스킬을 다룹니다.

**다른 언어:** [English](HOW_TO_USE.md) | [简体中文](HOW_TO_USE_zh.md) | [日本語](HOW_TO_USE_jp.md)

---

## 목차

1. [개요](#1-개요)
2. [설치](#2-설치)
3. [설정](#3-설정)
4. [로컬 GGUF 모델](#4-로컬-gguf-모델)
5. [클라우드 모드와 API 키](#5-클라우드-모드와-api-키)
6. [메모리 시스템](#6-메모리-시스템)
7. [개별 도구(웹 검색, 로컬 파일)](#7-개별-도구웹-검색-로컬-파일)
8. [워크스페이스 파일(config/workspace)](#8-워크스페이스-파일-configworkspace)
9. [시스템 테스트](#9-시스템-테스트)
10. [플러그인](#10-플러그인)
11. [스킬](#11-스킬)

---

## 1. 개요

HomeClaw은 사용자 기기에서 실행되는 **로컬 우선 AI 어시스턴트**입니다. **채널**(WebChat, Telegram, Discord, 이메일 등)로 대화합니다. 단일 **Core** 프로세스가 모든 채널을 처리하고 **메모리**(RAG + 채팅 기록)를 유지하며 **로컬**(llama.cpp, GGUF) 또는 **클라우드**(OpenAI, Gemini, DeepSeek 등) 모델을 사용할 수 있습니다. **플러그인**으로 날씨, 뉴스, 메일 등의 기능을 추가하고, **스킬**로 LLM이 도구를 사용해 수행하는 워크플로(예: 소셜 미디어 에이전트)를 추가합니다.

- **Core 실행:** `python main.py`(또는 `python main.py core`) — Core는 포트 9000에서 대기합니다.
- **채널 실행:** 예: `python main.py webchat` 또는 Core의 `/inbound` 또는 WebSocket으로 메시지를 보내는 채널 프로세스를 시작합니다.
- **CLI:** `python main.py`는 `llm set`, `llm cloud` 등의 하위 명령과 워크스페이스·LLM·채널·스킬을 대화형으로 설정하는 **온보딩**(`python main.py onboard`)을 지원합니다.

아키텍처와 기능은 메인 [README.md](README.md)를 참조하세요.

---

## 2. 설치

### 2.1 Python과 의존성

- **Python:** 3.10+ 권장.
- **requirements에서 설치:**

  ```bash
  pip install -r requirements.txt
  ```

  핵심 의존성에는 `loguru`, `PyYAML`, `fastapi`, `openai`, `litellm`, `chromadb`, `sqlalchemy`, `aiohttp`, `httpx`, `cognee` 등이 포함됩니다. [requirements.txt](requirements.txt) 참조.

### 2.2 선택 사항

- **브라우저 도구(Playwright):** `browser_navigate`, `browser_snapshot` 등. `pip install playwright` 후:
  ```bash
  python -m playwright install chromium
  ```
- **웹 검색(키 없음):** `duckduckgo-search`는 requirements에 포함됩니다. `tools.web.search.provider: duckduckgo`와 `fallback_no_key: true`로 키 없이 검색할 수 있습니다.
- **문서 처리(file_read / document_read):** requirements의 `unstructured[all-docs]`로 PDF, Word, HTML 등을 처리합니다.
- **그래프 DB(자체 RAG):** `memory_backend: chroma`일 때 `kuzu` 사용. Neo4j 사용 시 requirements에서 `neo4j` 주석 해제.
- **채널:** 일부 채널은 추가 패키지 필요(예: WeChat `wcferry`, WhatsApp `neonize`). requirements 주석 참조.

### 2.3 환경

- **가상 환경** 사용 권장(예: `python -m venv venv` 후 `source venv/bin/activate` 또는 `venv\Scripts\activate`).
- **클라우드 모델** 사용 시 **API 키 환경 변수** 설정 필요([§5](#5-클라우드-모드와-api-키) 참조).

---

## 3. 설정

주요 설정 파일은 **`config/core.yml`**(Core 동작, LLM, 메모리, 도구)과 **`config/user.yml`**(사용 가능한 사용자와 식별자)입니다.

### 3.1 core.yml(개요)

- **Core 서버:** `host`, `port`(기본 9000), `mode`.
- **경로:** `model_path`(GGUF 루트), `workspace_dir`(기본 `config/workspace`), `skills_dir`(기본 `skills`).
- **기능:** `use_memory`, `use_tools`, `use_skills`, `use_workspace_bootstrap`, `memory_backend`(예: `cognee` 또는 `chroma`).
- **LLM:** `local_models`, `cloud_models`, `main_llm`, `embedding_llm`([§4](#4-로컬-gguf-모델) 및 [§5](#5-클라우드-모드와-api-키) 참조).
- **메모리:** `memory_backend`, `cognee:`(Cognee 사용 시), 또는 `database`, `vectorDB`, `graphDB`(`memory_backend: chroma` 시). [§6](#6-메모리-시스템) 참조.
- **도구:** `tools` 섹션: `file_read_base`, `file_read_max_chars`, `web`(검색 프로바이더, API 키), `browser_enabled`, `browser_headless` 등. [§7](#7-개별-도구웹-검색-로컬-파일) 참조.
- **결과 뷰어:** `result_viewer`(활성화, 포트, 보고서 링크용 base_url).
- **지식 베이스:** `knowledge_base`(활성화, 백엔드, 청크 설정).

환경에 맞게 `config/core.yml`을 편집합니다(경로, 포트, 프로바이더).

### 3.2 user.yml(허용 목록 및 식별자)

- **목적:** 채널을 통해 Core와 대화할 수 있는 **사용자**를 정의합니다. 채팅·메모리·프로필은 모두 **시스템 사용자 id**로 구분됩니다.
- **구조:** `users` 목록. 각 사용자에:
  - **id**(선택, 기본값은 `name`), **name**(필수).
  - **email:** 이메일 주소 목록(이메일 채널용).
  - **im:** `"<채널>:<id>"` 목록(예: `matrix:@user:matrix.org`, `telegram:123456`, `discord:user_id`).
  - **phone:** 번호 목록(SMS/전화용).
  - **permissions:** 예: `[IM, EMAIL, PHONE]` 또는 `[]`로 모두 허용.
- **예시:**

  ```yaml
  users:
    - id: me
      name: Me
      email: [me@example.com]
      im: [telegram:123456, matrix:@me:matrix.org]
      phone: []
      permissions: []
  ```

`user.yml`의 항목과 채널 식별자가 일치하는 사용자만 허용됩니다. 자세한 내용은 **docs/MultiUserSupport.md**를 참조하세요.

---

## 4. 로컬 GGUF 모델

### 4.1 모델 배치

- **베이스 디렉터리:** `config/core.yml`의 **`model_path`**(기본 `../models/`)가 GGUF 파일의 루트입니다. **`local_models`**의 **path**는 **`model_path`에 대한 상대 경로**(절대 경로도 가능)입니다.
- GGUF 파일을 해당 루트 아래에 둡니다(예: 프로젝트 루트의 `models/` 또는 `../models/`).

### 4.2 로컬 모델 정의(임베딩 + 메인)

**`config/core.yml`**의 **`local_models`** 아래에 모델당 한 항목을 추가합니다:

- **id**, **alias**, **path**(`model_path`에 대한 상대 경로), **host**, **port**, **capabilities**(예: `[Chat]` 또는 `[embedding]`).
- **임베딩:** `capabilities: [embedding]` 한 개; **`embedding_llm`**을 `local_models/<id>`로 설정.
- **채팅:** `capabilities: [Chat]` 한 개 이상; **`main_llm`**을 `local_models/<id>`로 설정.

예시:

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

### 4.3 llama.cpp 서버 실행

- 각 모델마다 설정한 `host`와 `port`에서 **llama.cpp 서버를 하나씩** 실행합니다. config의 `path`(`model_path`에 대한 상대)와 동일한 경로를 사용합니다.
- 예(프로젝트 루트에서 `model_path: ../models/`): `llama-server`(또는 빌드)를 `-m <path>`와 포트로 실행. 플랫폼별 내용은 **llama.cpp-master/README.md**를 참조하세요.
- **테스트 완료 조합:** 임베딩 **bge-m3-Q5_K_M.gguf**, 채팅 **Qwen3-14B-Q5_K_M.gguf**. 로컬 RAG 및 대화에 적합합니다.

### 4.4 모델 크기와 양자화 선택

- **CPU만:** 작은 모델(1.5B–7B)과 높은 양자화(Q4_K_M, Q5_K_M) 권장. 14B+는 느릴 수 있습니다.
- **GPU(예: 8GB VRAM):** 7B–14B Q4/Q5가 일반적. 32B는 Q4 또는 offload가 필요할 수 있습니다.
- **GPU(16GB+ VRAM):** 14B–32B를 Q5 또는 Q8로 실행 가능.
- 모델 파일과 llama.cpp 프로세스에 충분한 시스템 RAM을 확보하세요(대략 파일 크기의 1–1.5배).

---

## 5. 클라우드 모드와 API 키

### 5.1 클라우드 모델 사용

- **`config/core.yml`**의 **`cloud_models`**에 클라우드 프로바이더(OpenAI, Gemini, Anthropic, DeepSeek 등)를 나열합니다. 각 항목에 **id**, **path**(예: `openai/gpt-4o`), **host**, **port**, **api_key_name**, **capabilities**를 지정합니다.
- **`main_llm`** 또는 **`embedding_llm`**을 `cloud_models/<id>`(예: `cloud_models/OpenAI-GPT4o`)로 설정하면 해당 모델을 사용합니다.
- 클라우드 API와의 통신에는 **LiteLLM**을 사용합니다. 프로바이더별로 LiteLLM 프록시를 실행하거나 하나의 프록시로 여러 개를 처리할 수 있으며, `host`와 `port` 설정으로 맞춥니다.

### 5.2 API 키(환경 변수)

- 각 클라우드 모델 항목에는 **`api_key_name`**(예: `OPENAI_API_KEY`, `GEMINI_API_KEY`)이 있습니다. Core를 시작하기 전에 **같은 이름의 환경 변수**에 API 키를 설정하세요.
- 예:
  - OpenAI: `export OPENAI_API_KEY=sk-...`
  - Google: `export GEMINI_API_KEY=...`
  - Anthropic: `export ANTHROPIC_API_KEY=...`
  - DeepSeek: `export DEEPSEEK_API_KEY=...`
- **Ollama** 항목에는 `api_key_name`이 없습니다(로컬, 키 불필요).
- 버전 관리되는 `core.yml`에 API 키를 넣지 마세요. 환경 변수 또는 로컬 오버라이드를 사용하세요.

### 5.3 로컬과 클라우드 전환

- 실행 중에는 CLI **`llm set`**(로컬 선택) 또는 **`llm cloud`**(클라우드 선택)로 메인 모델을 전환할 수 있습니다. 또는 config의 `main_llm`을 변경한 뒤 재시작해도 됩니다.

---

## 6. 메모리 시스템

### 6.1 백엔드

- **`memory_backend: cognee`**(기본): Cognee가 관계·벡터·그래프 저장을 담당합니다. **`cognee:`**(`config/core.yml` 내) 및/또는 Cognee의 **`.env`**로 설정합니다. Cognee 사용 시 core.yml의 `vectorDB`와 `graphDB`는 메모리에 **사용되지 않습니다**.
- **`memory_backend: chroma`:** 자체 RAG: Core는 core.yml의 **`database`**, **`vectorDB`**, 선택적으로 **`graphDB`**(SQLite + Chroma + Kuzu/Neo4j)를 사용합니다.

### 6.2 Cognee(기본)

- **`config/core.yml`**의 **`cognee:`**에서 관계형(sqlite/postgres), 벡터(chroma), 그래프(kuzu/neo4j) 및 선택적으로 LLM/embedding을 설정할 수 있습니다. LLM/embedding을 비우면 Core의 **main_llm**과 **embedding_llm**(동일 host/port)을 사용합니다.
- Cognee와 chroma의 매핑 및 Cognee `.env` 옵션은 **docs/MemoryAndDatabase.md**를 참조하세요.

### 6.3 메모리 초기화

- 테스트용 RAG 메모리 비우기: **`http://<core_host>:<core_port>/memory/reset`**에 `GET` 또는 `POST`(예: `curl http://127.0.0.1:9000/memory/reset`).
- 지식 베이스 비우기: **`http://<core_host>:<core_port>/knowledge_base/reset`**.

---

## 7. 개별 도구(웹 검색, 로컬 파일)

### 7.1 웹 검색

- **`config/core.yml`**의 **`tools.web.search`**에서:
  - **provider:** `duckduckgo`(키 없음), `google_cse`, `bing`, `tavily`, `brave`, `serpapi`. 사용할 것을 지정.
  - **API 키:** `google_cse`는 `api_key`와 `cx`. `tavily`는 `api_key`(또는 환경 변수 `TAVILY_API_KEY`). `bing`, `brave`, `serpapi`는 각 블록에서 설정.
  - **fallback_no_key:** `true`이면 메인 프로바이더가 실패하거나 키가 없을 때 DuckDuckGo(키 없음)로 폴백합니다. `duckduckgo-search`(requirements에 포함)가 필요합니다.

### 7.2 로컬 파일 처리

- **file_read / folder_list:** **`tools`** 내에서:
  - **file_read_base:** 파일 접근 베이스 경로(`.` = 현재 작업 디렉터리 또는 절대 경로). 모델은 이 베이스 아래의 파일만 읽습니다.
  - **file_read_max_chars:** 도구가 제한을 넘기지 않을 때 `file_read`가 반환하는 최대 문자 수(기본 32000. 긴 문서는 늘리세요).
- **document_read(PDF, Word 등):** `unstructured[all-docs]` 설치 시 Unstructured 사용. 동일 베이스 경로. 긴 PDF는 `file_read_max_chars`를 늘리세요.

### 7.3 브라우저 도구

- **browser_enabled:** `false`로 브라우저 도구를 완전히 비활성화(웹은 `fetch_url`과 `web_search`만 사용).
- **browser_headless:** `false`로 브라우저 창 표시(로컬 테스트용). Playwright와 `playwright install chromium` 필요.

---

## 8. 워크스페이스 파일(config/workspace)

**워크스페이스**는 프롬프트 전용입니다. Markdown 파일이 **시스템 프롬프트에 주입**되어 LLM의 정체성과 능력을 전달합니다. 이 파일들에서 코드는 실행되지 않습니다.

### 8.1 파일과 순서

- **`config/workspace/IDENTITY.md`** — 어시스턴트 정체성(톤, 스타일). `## Identity`로 주입.
- **`config/workspace/AGENTS.md`** — 상위 동작 및 라우팅 힌트. `## Agents / behavior`로 주입.
- **`config/workspace/TOOLS.md`** — 능력의 사람이 읽기 쉬운 목록. `## Tools / capabilities`로 주입.

이 순서로 연결한 뒤 RAG 응답 템플릿(메모리)을 추가합니다. 전체 흐름과 팁은 **config/workspace/README.md**를 참조하세요.

### 8.2 설정

- **`config/core.yml`**에서: **`use_workspace_bootstrap: true`**로 주입 활성화; **`workspace_dir`**(기본 `config/workspace`)가 로드 디렉터리입니다.
- 위 `.md` 파일을 편집해 정체성·동작·능력 설명을 조정합니다. 변경 사항 적용을 위해 Core를 재시작하거나, 캐시하지 않는 경우 새 메시지를 보냅니다.

### 8.3 팁

- 각 파일을 짧게 유지해 프롬프트가 비대해지지 않게 하세요.
- 파일을 비우거나 삭제하면 해당 블록이 건너뜁니다.

---

## 9. 시스템 테스트

### 9.1 빠른 확인

- Core 시작: `python main.py`(또는 `python main.py core`). Core는 포트 9000에서 대기합니다.
- WebChat 시작(활성화된 경우): WebChat URL에 연결해 메시지를 보냅니다. `user.yml`에서 자신의 식별자가 허용되는지 확인하세요.
- **메모리 초기화:** `curl http://127.0.0.1:9000/memory/reset`로 RAG를 비워 깨끗한 테스트를 할 수 있습니다.

### 9.2 도구 트리거

- **`use_tools: true`**일 때 LLM이 도구를 호출할 수 있습니다. 자주 쓰는 트리거 예:
  - **time:** "지금 몇 시야?"
  - **memory_search:** "나에 대해 뭘 기억해?"
  - **web_search:** "웹에서 … 검색해"
  - **file_read:** "파일 X 읽어줘" / "… 내용 요약해"
  - **cron_schedule:** "매일 9시에 알려줘"
- 도구별 예시 메시지 전체 목록은 **docs/ToolsAndSkillsTesting.md**를 참조하세요.

### 9.3 테스트(pytest)

- 테스트 실행: 프로젝트 루트에서 `pytest`. requirements에 `pytest`, `pytest-asyncio`, `httpx`가 포함됩니다.

---

## 10. 플러그인

플러그인은 **단일 기능**(날씨, 뉴스, 메일 등)을 추가합니다. **내장**(Python, 프로세스 내) 또는 **외부**(HTTP 서비스)일 수 있습니다.

- **사용·개발:** **docs/PluginsGuide.md**에서 플러그인 개념, 작성 방법(plugin.yaml, config.yml, plugin.py), 외부 플러그인 등록을 설명합니다.
- **실행·테스트:** **docs/RunAndTestPlugins.md**에서 Core, WebChat, 등록, 예시 프롬프트의 단계별 안내를 제공합니다.
- **파라미터 수집 및 설정:** **docs/PluginParameterCollection.md**에서 `profile_key`, `config_key`, `confirm_if_uncertain`을 설명합니다.
- **표준 및 등록:** **docs/PluginStandard.md**, **docs/PluginRegistration.md**.

---

## 11. 스킬

**스킬**은 **도구**를 사용해 목표를 달성하는 *방법*을 어시스턴트에게 알려주는 작업 지향 지시 패키지(SKILL.md + 선택적 스크립트)입니다. LLM이 지시에 따라 실행하는 워크플로이며, 별도 플러그인 코드가 아닙니다.

- **활성화:** **`config/core.yml`**에서 **`use_skills: true`**와 **`skills_dir`**(기본 `skills`)를 설정한 뒤 Core를 재시작합니다.
- **스킬 추가:** `skills_dir` 아래에 폴더를 만들고 **SKILL.md**(이름, 설명, 본문)를 넣습니다. 선택적으로 `scripts/` 아래에 스크립트를 두고 **run_skill**로 참조합니다.
- **벡터 검색:** 스킬이 많으면 **`skills_use_vector_search: true`**로 쿼리당 관련 스킬만 주입할 수 있습니다. 옵션은 **docs/SkillsGuide.md**를 참조하세요.
- **OpenClaw 스킬 재사용:** OpenClaw은 다른 확장 모델(채널/프로바이더/스킬을 하나의 manifest로)을 사용합니다. HomeClaw 스킬은 **SKILL.md + scripts**를 `skills/` 아래에 두는 형태입니다. OpenClaw "스킬"을 HomeClaw에서 쓰려면 지시를 **SKILL.md**(이름, 설명, 단계 본문)로 정리해 `skills/<스킬명>/`에 넣으면 됩니다. 도구 사용 단계로 표현 가능하면 코드 이식은 필요 없습니다. OpenClaw와 HomeClaw 비교는 **docs/ToolsSkillsPlugins.md** §2.7을 참조하세요.

**스킬 전체 가이드:** **docs/SkillsGuide.md**(구조, 사용, 구현, 테스트). **docs/ToolsSkillsPlugins.md**에서 도구/스킬/플러그인 전체 설계를 설명합니다.
