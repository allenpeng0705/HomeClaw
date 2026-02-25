# HomeClaw — 설계 문서

이 문서는 **HomeClaw**의 아키텍처, 구성 요소, 데이터 흐름을 설명합니다. 프로젝트 이해와 향후 개발을 위한 기준 참고 문서입니다.

**다른 언어:** [English](Design.md) | [简体中文](Design_zh.md) | [日本語](Design_jp.md)

---

## 1. 프로젝트 개요

### 1.1 목적

**HomeClaw**은 **로컬 우선 AI 어시스턴트**로, 다음을 충족합니다.

- 사용자 기기(예: 가정용 PC)에서 실행됩니다.
- **로컬 LLM**(llama.cpp 서버)과 **클라우드 AI**(OpenAI 호환 API, **LiteLLM** 사용)를 지원합니다.
- **다중 채널**(이메일, IM, CLI)로 어시스턴트를 노출해 어디서든(예: 휴대폰) 자택 인스턴스와 상호작용할 수 있습니다.
- **RAG 스타일 메모리**를 사용합니다: **Cognee**(기본) 또는 자체 SQLite + Chroma; 선택적으로 사용자별 **프로필**과 **지식 베이스**. docs_design/MemoryAndDatabase.md 참조.
- **플러그인**(plugin.yaml + config.yml + plugin.py; route_to_plugin 또는 orchestrator), **스킬**(skills/ 아래 SKILL.md; 선택적 벡터 검색; run_skill 도구), **도구 계층**(use_tools: true — exec, browser, cron, sessions_*, memory_*, file_* 등)으로 동작을 확장합니다. docs_design/ToolsSkillsPlugins.md 참조.

### 1.2 설계 목표

- **로컬 우선**: 주로 로컬 하드웨어에서 동작; 클라우드는 선택.
- **단순 배포**: 최소 의존성(기본 SQLite, Chroma, 무거운 DB 없음).
- **채널 무관**: 이메일, Matrix, Tinode, WeChat, WhatsApp, CLI 중 어떤 것으로 연결해도 동일한 Core.
- **확장 가능**: 플러그인으로 기능 추가; 전용 HomeClaw 채널 가능성.
- **다중 모델**: 채팅용과 임베딩용으로 다른 모델; 설정으로 여러 모델 로드 가능.

---

## 2. 상위 아키텍처

(다이어그램은 Design.md §2와 동일: Channels → Core Engine → LLM Layer → Memory. Cognee 기본 또는 SQLite + Chroma; 선택적 profile, KB.)

- **채널**은 사용자 입력을 `PromptRequest`로 HTTP로 **Core**에 보냅니다.
- **Core**는 직접 처리(채팅 + 메모리/RAG)하거나 **플러그인**으로 라우팅합니다.
- **LLM** 호출은 단일 엔드포인트: 로컬 llama.cpp 서버 또는 LiteLLM 프록시(동일한 OpenAI 호환 API).
- **Memory**는 채팅과 RAG용 벡터화 지식을 저장합니다.

---

## 3. 핵심 구성 요소

### 3.1 Core 엔진(`core/`)

- **역할**: 중앙 라우터, 권한 검사, 채팅 + 메모리 처리.
- **진입점**: `core/core.py` — `Core`(싱글톤)가 FastAPI 앱을 실행하고 LLM 매니저를 시작합니다.
- **주요 엔드포인트**: `POST /process`, `POST /local_chat`, `POST /inbound`, `WebSocket /ws`, `POST /register_channel`, `POST /deregister_channel`.
- **설정**: `config/core.yml`(host, port, main_llm, embedding_llm, memory_backend, use_tools, use_skills, tools.*, result_viewer, auth_enabled, auth_api_key 등). **인증**: auth_enabled: true일 때 /inbound와 /ws에 X-API-Key 또는 Authorization: Bearer 필요. docs_design/RemoteAccess.md 참조. **결과 뷰어**: 선택적 save_result_page 도구 및 보고 서버(port, base_url). docs_design/ComplexResultViewerDesign.md 참조.

**Orchestrator**(`core/orchestrator.py`): 채팅 기록과 사용자 입력으로 의도(TIME/OTHER) 분류; OTHER일 때 Core가 플러그인 선택. **TAM**(`core/tam.py`): 시간 인식 모듈; TIME 의도(스케줄링 등) 처리. 라우팅 스타일은 core.yml의 **orchestrator_unified_with_tools**로 제어(기본 true = 메인 LLM이 도구와 함께 라우팅; false = 별도 orchestrator가 먼저 1회 LLM 호출).

**1 Core, 다중 LLM(로컬 + 클라우드)**: 설정에서 `local_models`, `cloud_models`; `main_llm`, `embedding_llm`은 참조(예: local_models/xxx 또는 cloud_models/xxx). 런타임에 Util.main_llm(), Util.get_llm(name)으로 해석; 선택적 llm_name으로 호출별로 모델 전환 가능. **sessions_spawn** 도구로 llm_name을 지정해 다른 모델로 일회성 하위 작업 실행 가능.

**1 에이전트 vs 다중 에이전트**: 현재는 **1 에이전트**(하나의 identity, 도구 세트, 스킬 세트); 다중 에이전트(에이전트별 identity, 도구/스킬 서브세트, 선택적 기본 LLM)로 확장 가능. 권장 기본은 「1 에이전트, 다중 LLM」.

### 3.2 채널(`channels/`, `main.py`, Core `/inbound` 및 `/ws`)

사용자 또는 봇이 Core에 도달하는 경로. **전체 채널**(별도 프로세스, BaseChannel, 비동기/동기 응답)과 **최소**(BaseChannel 프로세스 없음, POST /inbound 또는 WebSocket /ws로 동기 응답) 두 패턴. 권한은 `config/user.yml`로 통일.

**기존 채널**: Email, Matrix, Tinode, WeChat, WhatsApp, Telegram, Discord, Slack, WebChat, Google Chat, Signal, iMessage, Teams, Zalo, Feishu, DingTalk, BlueBubbles, CLI(main.py). 채널 실행: `python -m channels.run <name>`. 자세한 내용은 Design.md §3.2 참조.

**Webhook 및 WebSocket**: Core `POST /inbound`(최소 HTTP API); Webhook 채널 `POST /message`로 중계; Core `WebSocket /ws`로 자체 클라이언트(WebChat 등). 새 봇은 Core `/inbound` 또는 Webhook `/message`에 `{ user_id, text }`를 POST하고 반환된 text를 사용자에게 전달; user.yml에 user_id 등록.

### 3.3 LLM 계층(`llm/`)

- **역할**: 로컬과 클라우드 LLM을 Core가 사용하는 하나의 OpenAI 호환 API로 통일.
- **설정**: `config/core.yml`의 `llama_cpp`, `local_models`(배열), `cloud_models`(배열) 및 선택된 `main_llm`, `embedding_llm`(id). 로컬: llama-server를 각 엔트리의 host/port로 시작; 바이너리는 **llama.cpp-master/**의 플랫폼별 서브폴더에서 자동 선택. llama.cpp-master/README.md 참조. 클라우드: LiteLLM; 각 cloud_models 엔트리에 **api_key_name**이 있으며 Core 실행 환경에서 **같은 이름의 환경 변수** 설정; core.yml에 키를 넣지 않음.

### 3.4 메모리(`memory/`)

- **역할**: 채팅 기록 + RAG(현재 쿼리와 관련된 과거 콘텐츠 저장 및 검색).
- **설계**: **Cognee(기본)**: 기본 SQLite + ChromaDB + Kuzu; Cognee `.env`로 Postgres, Qdrant 등 지원. **자체(chroma)**: core.yml로 SQLite + Chroma + 선택적 Kuzu/Neo4j. docs_design/MemoryAndDatabase.md 참조.
- **memory_backend**: `cognee`(기본) 또는 `chroma`. cognee일 때 **cognee:** 및/또는 Cognee `.env`로 설정; chroma일 때 core.yml의 vectorDB, graphDB 사용. **database**는 항상 Core의 채팅 세션, runs, 턴에 사용. **profile**(선택): 사용자별 JSON; profile.enabled, profile.dir. **knowledge_base**(선택): RAG 메모리와 별도; knowledge_base.enabled, knowledge_base.backend.
- **워크스페이스 부트스트랩(선택)**: `config/workspace/`의 IDENTITY.md, AGENTS.md, TOOLS.md; base/workspace.py에서 로드해 시스템 프롬프트에 추가. core.yml: use_workspace_bootstrap, workspace_dir.
- **세션 기록**: ChatHistory.get_transcript, get_transcript_jsonl, prune_session, Core.summarize_session_transcript 등. Comparison.md §7.6 참조.
- **최근 채널 저장**: base/last_channel.py — save_last_channel, get_last_channel; channel_send와 플러그인 응답을 올바른 채널로 전달.

### 3.5 플러그인(`plugins/`)

- **역할**: Core가 일반 채팅 + RAG로 직접 답하지 않을 때 **route_to_plugin** 또는 orchestrator로 **플러그인에 라우팅**해 처리.

**내장 플러그인 vs 외부 플러그인**

| 유형 | 언어 | 실행 위치 | 매니페스트 | 사용처 |
|------|------|------------|------------|--------|
| **내장** | Python만 | Core와 동일 프로세스 | `plugin.yaml`에 **type: inline**, `config.yml`, `plugin.py`(BasePlugin 상속)를 `plugins/<Name>/`에 둠 | 빠른 통합, 추가 프로세스 없음, Python 라이브러리 사용(Weather, News, Mail 등). |
| **외부** | 임의(Node.js, Go, Java 등) | 별도 프로세스 또는 원격 HTTP 서비스 | `plugins/` 아래 폴더에 `plugin.yaml`로 **type: http**, 또는 **POST /api/plugins/register**로 등록 | 기존 서비스, 다른 언어, 독립 배포; 서버가 POST PluginRequest를 받아 PluginResult를 반환. |

Core는 `plugins/`를 스캔해 plugin.yaml + plugin.py를 로드해 **내장** 플러그인을 발견; **외부** 플러그인은 폴더 내 선언(plugin.yaml type: http + 엔드포인트 URL) 또는 런타임 API로 등록. 둘 다 동일한 라우팅(orchestrator 또는 route_to_plugin). **docs_design/PluginsGuide.md**(§2 내장, §3 외부), **docs_design/PluginStandard.md**, **docs_design/RunAndTestPlugins.md** 참조.

- **매니페스트**: **plugin.yaml**(id, name, description, **type: inline** 또는 **type: http**, capabilities 및 매개변수). **config.yml**로 런타임 설정. **plugin.py**(내장만) — BasePlugin 상속, run() 및/또는 capability 메서드 구현. **로딩**: PluginManager가 plugins/를 스캔해 plugin.yaml(및 type: inline일 때 plugin.py)을 로드하고 설명을 등록; Core는 LLM으로 사용자 텍스트에 맞는 플러그인 또는 **route_to_plugin**을 실행하며, 내장은 plugin.run(), 외부는 HTTP POST.

### 3.6 플러그인 vs 도구: 차이와 설계

**플러그인** = 메시지를 하나의 핸들러로 라우팅해 실행 후 응답을 반환. **도구** = 모델이 이름과 구조화 인자로 함수를 호출; 실행 결과를 대화에 추가하고 모델이 계속 호출하거나 응답. HomeClaw는 **도구 계층**을 구현함(exec, browser, cron, sessions_*, memory_*, file_*, document_read, web_search, run_skill, route_to_plugin, route_to_tam, save_result_page, models_list, agents_list, channel_send, image; remind_me, record_date, recorded_events_list; profile_*, knowledge_base_*; tavily_extract/crawl/research, web_extract, web_crawl, web_search_browser, http_request 등); nodes/canvas는 범위 외. 전체 목록은 **Design.md §3.6** 참조. **docs_design/ToolsSkillsPlugins.md**, **Comparison.md** §7.10.2 참조.

- **구현**: `base/tools.py`(ToolDefinition, ToolContext, ToolRegistry), `tools/builtin.py`(register_builtin_tools); Core는 initialize()에서 등록하고 answer_from_memory에서 use_tools가 true일 때 도구를 붙여 호출하며 tool_calls 루프 실행. **설정**: core.yml에서 **use_tools: true** 및 **tools:**(exec_allowlist, file_read_base, tools.web, browser_*, run_skill_* 등). **docs_design/ToolsDesign.md**, **docs_design/ToolsAndSkillsTesting.md** 참조. 새 도구: execute_async 정의, ToolDefinition 구성, register_builtin_tools 내부 또는 get_tool_registry().register(tool)로 등록.

---

## 4. 엔드투엔드 흐름

### 4.1 사용자가 메시지 전송(예: 이메일 또는 IM)

채널이 메시지 수신 → PromptRequest 구성 → Core에 POST /process(CLI는 POST /local_chat) → Core가 권한 검사 → orchestrator 사용 시 의도 분류 및 플러그인 선택·실행, 또는 Core가 처리 → Core가 처리할 때: 채팅 기록 로드, 선택적으로 메모리에 enqueue, answer_from_memory(메모리 조회 Cognee/Chroma, LLM 호출; use_tools 시 tool_calls 루프 실행), 채팅 DB에 기록, AsyncResponse를 response_queue에 푸시 → 채널이 /get_response로 수신해 사용자에게 전달.

### 4.2 로컬 CLI(`main.py`)

사용자가 main.py를 실행해 콘솔에 입력; Core는 백그라운드 스레드로 실행; CLI는 local_chat(동기)를 사용하며 응답은 HTTP 본문으로 반환되어 콘솔에 출력. 접두사 `+`/`?`로 메모리 저장/검색에 매핑 가능.

---

## 5. 설정 요약

| 파일 | 목적 |
|------|------|
| `config/core.yml` | **단일 설정**: host/port, model_path, local_models, cloud_models, main_llm, embedding_llm, memory_backend, cognee:, database, vectorDB/graphDB(chroma 시), use_memory, use_workspace_bootstrap, workspace_dir, use_tools, tools:, use_skills, skills_dir, skills_use_vector_search, profile, knowledge_base, result_viewer, auth_enabled, auth_api_key 등. HOW_TO_USE.md 참조. |
| `config/user.yml` | 허용 목록: 사용자(id, name, email, im, phone, permissions); 채팅/메모리/프로필은 모두 시스템 사용자 id로 구분. |
| `config/email_account.yml` | 이메일 채널용 IMAP/SMTP 및 자격 증명. |
| `channels/.env` | CORE_URL, 각 채널 봇 토큰. |

Core는 core.yml에서 main_llm, embedding_llm(id)를 읽고 **local_models** 또는 **cloud_models**에서 host/port와 타입을 해석. 로컬 모델 path는 **model_path**에 대한 상대 경로. llama.cpp 서버 바이너리는 **llama.cpp-master/**의 플랫폼별 서브폴더(mac/, win_cuda/, linux_cpu/ 등)에 둠. llama.cpp-master/README.md 참조. 클라우드 API 키: 각 cloud 모델의 **api_key_name**과 동일한 이름의**환경 변수** 설정(예: OPENAI_API_KEY).

---

## 6. 확장 포인트 및 향후 작업

- **채널**: 최소 — 임의 봇이 POST /inbound 또는 Webhook /message; 전체 — channels/에 BaseChannel 서브클래스 추가하고 /get_response 구현. 전용 앱은 WebSocket /ws 사용 가능.
- **LLM**: core.yml의 local_models 또는 cloud_models에 엔트리 추가; 로컬은 엔트리별로 llama-server 시작.
- **메모리/RAG**: 기본 Cognee; 대안 memory_backend: chroma. docs_design/MemoryAndDatabase.md 참조.
- **플러그인**: plugins/ 아래에 폴더 추가하고 plugin.yaml, config.yml, plugin.py(내장) 또는 type: http + 엔드포인트(외부); 외부는 POST /api/plugins/register도 가능. docs_design/PluginsGuide.md, docs_design/PluginStandard.md, docs_design/RunAndTestPlugins.md 참조.
- **도구 계층**: §3.6 참조; 내장 도구는 구현됨; 선택적으로 플러그인이 get_tools()/run_tool()로 도구 노출 가능.
- **스킬(SKILL.md)**: 구현됨; base/skills.py가 skills/에서 로드; use_skills, skills_dir, skills_use_vector_search; run_skill 도구. docs_design/SkillsGuide.md, docs_design/ToolsSkillsPlugins.md 참조.
- **TAM**: 시간 의도는 분류됨; 스케줄링/리마인더 확장 가능.

---

## 7. 주요 파일 빠른 참조

| 영역 | 주요 파일 |
|------|------------|
| Core | core/core.py, core/coreInterface.py, core/orchestrator.py, core/tam.py |
| Channels | base/BaseChannel.py, base/base.py(InboundRequest), channels/, main.py. 실행: `python -m channels.run <name>`. |
| LLM | llm/llmService.py, llm/litellmService.py |
| Memory | memory/base.py, memory/mem.py, memory/chroma.py, memory/storage.py, memory/embedding.py, memory/chat/chat.py; memory/graph/(chroma 시); memory/cognee_adapter.py(cognee 시); base/profile_store.py, database/profiles/; 지식 베이스는 core.yml 참조. 워크스페이스: base/workspace.py, config/workspace/. 스킬: base/skills.py, skills/; run_skill은 tools/builtin.py. docs_design/MemoryAndDatabase.md, docs_design/SkillsGuide.md 참조. |
| Tools | base/tools.py, tools/builtin.py; 설정은 core.yml tools:. docs_design/ToolsDesign.md, docs_design/ToolsAndSkillsTesting.md 참조. |
| Plugins | base/BasePlugin.py, base/PluginManager.py, plugins/Weather/(plugin.yaml, config.yml, plugin.py); 외부: POST /api/plugins/register. docs_design/PluginsGuide.md, docs_design/PluginStandard.md 참조. |
| Shared | base/base.py(PromptRequest, AsyncResponse, 열거, 설정 데이터클래스), base/util.py |

---

이 Design.md는 현재 코드베이스를 반영하며, HomeClaw의 추가 개발과 리팩터링을 위한 기준 문서로 사용됩니다.
