# DevTrouble AI — Backend

> 개발 단계: **4단계 (Folder Structure)**
> 이전 단계: PRD → ERD/DB 설계
> 다음 단계: API Spec 확정 → DB Schema(Alembic 마이그레이션 생성) → Backend 구현

---

## 1. 왜 이렇게 나눴는가 (설계 근거)

PRD의 아키텍처 원칙(Clean Architecture + DDD, Repository Pattern, DI)을 그대로 디렉토리에 매핑했습니다.

```
app/
├── main.py            # FastAPI 엔트리포인트. 미들웨어/라우터 조립만 담당
├── core/               # 프레임워크·인프라 관심사 (설정, DB 연결, 보안, 예외, 로깅)
├── domain/             # 순수 도메인 개념 (Entity/Enum) — ORM/Pydantic에 의존하지 않음
├── models/             # SQLAlchemy ORM (영속성 계층)
├── schemas/             # Pydantic (API 요청/응답 계약)
├── repositories/        # DB 접근 캡슐화 (Repository Pattern)
├── services/            # Business Logic (Service Layer) — 여기에만 로직을 둔다
│   └── ai/               # RAG 파이프라인 컴포넌트 (Embedding/Retriever/Prompt/LLM)
├── api/                 # Controller 계층 (라우터 + Dependency)
│   └── v1/
├── middleware/           # 횡단 관심사 (예외 처리, 로깅, Request ID)
├── workers/              # Celery 비동기 작업
└── utils/                # 순수 함수 유틸리티
```

### 레이어별 의존 방향 (Clean Architecture)

```
api → services → repositories → models
        ↓
     domain (모든 계층이 참조 가능한 핵심 개념)
```

- **api**는 **services**만 호출한다. Repository나 SQLAlchemy Session을 직접 다루지 않는다.
- **services**는 **repositories**를 통해서만 DB에 접근한다. HTTP(status code 등)를 모른다.
- **repositories**는 **models**(ORM)만 알고, 비즈니스 규칙을 갖지 않는다.
- 이 원칙 덕분에 `services`는 FastAPI 없이도(예: Celery 태스크, 배치 스크립트) 재사용 가능하고, 단위 테스트 시 Repository만 mocking하면 된다.

### 예외/응답 처리를 미들웨어로 일원화한 이유

`core/exceptions.py`에 도메인 예외(`NotFoundError`, `DuplicateError` 등)를 정의하고,
`middleware/error_handler.py`에서만 HTTP status code로 변환합니다.
Service 코드 어디에도 `HTTPException`이 등장하지 않는 것이 원칙입니다 —
Service가 "지금 이게 웹 요청으로 호출됐는지"를 몰라야 Celery 태스크 등에서도 그대로 재사용할 수 있기 때문입니다.

### AI(RAG) 모듈을 별도 서브패키지로 분리한 이유

PRD의 AI 파이프라인 7단계(질문분석 → Embedding → VectorSearch → TopK → Prompt → LLM → 출처)를
`services/ai/` 아래 컴포넌트 단위로 1:1 매핑했습니다.

| 파이프라인 단계 | 담당 모듈 |
|---|---|
| Embedding 생성 | `embedding_service.py` |
| Vector Search / Top-K | `retriever_service.py` |
| Prompt 생성 | `prompt_builder.py` |
| LLM 응답 생성 | `llm_client.py` |
| 전체 오케스트레이션 + 출처 표시 | `rag_service.py` |

`retriever_service.py`와 `llm_client.py`는 인터페이스로 두고 실제 구현(FAISS vs Qdrant, OpenAI 등)을
`api/v1/ai_search.py`의 DI 조립 지점에서 주입하도록 설계했습니다. `settings.VECTOR_DB_PROVIDER` 값만 바꾸면
개발 환경(FAISS)에서 운영 환경(Qdrant)으로 전환할 수 있습니다.

---

## 2. 현재 구현 상태

이번 단계는 **Folder Structure** 단계이므로, 다음 기준으로 구현 범위를 나눴습니다.

✅ **완전히 구현됨** (구조/인프라 성격이라 지금 확정해야 하는 부분)
- `core/` 전체 (설정, DB 세션, JWT, 예외, 로깅)
- `models/` 전체 — ERD 설계와 1:1 매핑된 13개 ORM 모델
- `middleware/` 전체
- `api/deps.py`, `api/v1/router.py` — 인증/DI 배선
- **`AuthService` — 회원가입/로그인/토큰 재발급(Rotation)/로그아웃, `tests/test_auth.py` 18개 통합 테스트로 검증 완료 (SQLite in-memory 기준)**
- **`DocumentService` — 트러블슈팅 문서 CRUD(FR-DOC-01~04) + 검색(FR-SEARCH-01~03), `tests/test_documents.py` 17개 통합 테스트로 검증 완료. 태그 upsert, 작성자 권한 검증(403), Soft Delete, 조회수 증가까지 포함**
- **`services/ai/*` — RAG 파이프라인 전체(청킹/임베딩/색인/검색/프롬프트/응답생성/출처표시),
  LangGraph(StateGraph)로 오케스트레이션 — 질문 압축(멀티턴), 질문 분류, 하이브리드(벡터+키워드)
  검색, 재랭킹(LLM 또는 Cohere), 구조화 출력, 토큰 스트리밍, 빈약한 결과/불확실한 답변에 대한
  재검색 루프, 자체 검증(self-critique), 비용 절감 토글, Context Caching(LLM 호출+임베딩),
  LangSmith 관측성까지 포함. `AI_PROVIDER`(local/openai/watsonx) +
  `VECTOR_DB_PROVIDER`(faiss/chroma/qdrant) + `RERANK_PROVIDER`(llm/cohere) +
  `CONTEXT_CACHE_BACKEND`(memory/redis) 선택. 170개 테스트로 검증 완료
  (`tests/test_rag_*.py`, `tests/test_ai_provider_selection.py`, `tests/test_chroma_vector_store.py`,
  `tests/test_observability.py`, `tests/test_context_caching.py` 등). 자세한 내용은 5번 섹션 참고**
- **`workers/tasks/embedding_tasks.py`, `services/document_indexer.py` — 문서 변경 시 비동기 색인 트리거(FR-AI-06)**
- **`ProjectService` — 프로젝트 CRUD(FR-PROJ-01/02), 소유자 권한 검증(403), `tests/test_projects.py` 17개 통합 테스트로 검증 완료. 이제 API만으로 프로젝트 생성 → 문서 생성까지 엔드투엔드 가능**
- **`TagService` — 태그 목록 조회 + 관리자 태그 통합(FR-ETC-04, `db-error`/`database-error` 같은 중복 정리), `tests/test_tags.py` 7개**
- **`CommentService` — 댓글 CRUD(FR-ETC-01), 작성자 권한 검증, `tests/test_comments.py` 9개**
- **`BookmarkService` — 즐겨찾기 토글(FR-ETC-02) + 최근 본 문서(FR-ETC-03, upsert 방식), `tests/test_bookmarks.py` 9개**
- **Alembic 초기 마이그레이션(`alembic/versions/60af6b288466_initial_schema.py`) — 14개 테이블 전부 생성/롤백 실제 검증 완료. 자세한 내용은 6번 섹션 참고**
- `main.py`, `workers/celery_app.py`, Docker/Compose 설정

🚧 **스켈레톤만 존재**
- 없음 (PRD의 핵심 기능 Service는 전부 구현 완료. 남은 것은 관리자 페이지 확장 정도)

---

## 5. RAG 파이프라인 구현 상세

### 5.1 컴포넌트 구성

PRD의 AI 7단계를 아래처럼 구현했습니다.

| 단계 | 담당 모듈 | 비고 |
|---|---|---|
| ① 질문 분석 / ② Embedding 생성 | `embedding_provider.py` | Provider 인터페이스 뒤로 운영/로컬 구현을 숨김 |
| ③ Vector Search | `vector_store.py` | FAISS(개발) / **Chroma(로컬 영속, 서버 불필요)** / Qdrant(운영) |
| ④ Top-K 문서 검색 | `retriever_service.py` | VectorStore 결과를 `document_embeddings` 테이블과 조인해 청크 원문 복원 |
| ⑤ Prompt 생성 | `prompt_builder.py` | JSON 구조화 출력 강제, `CONTEXT_JSON` 블록 포함 |
| ⑥ LLM 응답 생성 | `llm_client.py` | OpenAI / watsonx / Template(로컬 폴백) |
| ⑦ 출처 표시 | `rag_service.py` | **LangGraph(StateGraph)로 오케스트레이션.** retrieve → generate 2단계 그래프이며, 검색 결과가 없으면 조건부 엣지로 generate를 건너뛴다. 문서별 최고 유사도 청크로 인용 목록 구성 + `ai_query_logs`/`ai_query_citations` 감사 로그 |
| 색인 트리거 (FR-AI-06) | `document_indexer.py`, `workers/tasks/embedding_tasks.py` | `DocumentService` CRUD 이후 Celery로 비동기 색인 |

> **LangGraph 도입 관련**: `RagService.search()`의 외부 시그니처는 그대로 두고, 내부 오케스트레이션만
> 수동 순차 호출에서 LangGraph `StateGraph`로 교체했습니다. `api/v1/ai_search.py`나 기존
> `tests/test_rag_pipeline.py`는 한 줄도 안 고쳤는데 그대로 통과하는 것으로 동작 동등성을
> 확인했습니다 — 리팩터링이 실제로 안전했다는 회귀 증거입니다.

### 5.1-0 재검색 루프 — LangGraph가 실제로 값어치를 하는 지점

처음 버전은 `retrieve → generate` 2단계뿐이라 사실 LangGraph 없이 일반 함수 호출로도
충분했습니다. 그래서 **검색 결과가 빈약하면 질문을 재구성해 재시도하는 루프**를 추가해
LangGraph의 조건부 엣지/순환 구조를 실제로 쓰게 했습니다.

```
retrieve ──(결과 충분)──────────────────────────► generate ─► END
   ▲   └──(결과 빈약 & 재시도 여력 있음)─► reformulate ─┘
   │                                                   (재구성된 질문으로 다시 retrieve)
   └──(결과 없음 & 재시도 소진)───────────────────► handle_no_results ─► END
```

- **"빈약하다"의 기준**: 문서를 아예 못 찾았거나, 최고 유사도 점수가 `RAG_RETRY_SCORE_THRESHOLD`
  미만일 때. 기본값 `0.05`는 LocalHash(대략 0~0.3)와 실제 임베딩(대략 0.5~0.95) 양쪽 모두에서
  "사실상 신호가 없는" 경우만 보수적으로 걸러내도록 잡았습니다. 실제 임베딩을 쓰면서 품질
  기준을 더 엄격히 걸고 싶다면 0.5 안팎으로 올리는 것을 고려하세요.
- **재시도 횟수**: `RAG_MAX_RETRIEVAL_ATTEMPTS`(기본값 1)만큼만 반복하고, 그래도 안 되면
  안내 메시지로 종료합니다. 무한 루프 걱정은 없습니다.
- **질문 재구성**: `LlmClient.reformulate()`가 담당합니다. 실제 LLM(OpenAI/watsonx)은 재구성을
  요청하는 프롬프트로 `generate()`를 호출하고, `TemplateLlmClient`(로컬 폴백)는 의문형
  어미/조사를 제거해 핵심 키워드만 남기는 규칙 기반 휴리스틱으로 대체합니다.
- **감사 로그**: 재구성된 질문이 아니라 사용자가 실제로 입력한 원문이 `ai_query_logs`에 남습니다.

**실제로 검증한 것** (`tests/test_rag_reformulation.py`, 5개): 재구성된 질문이 원본이 놓친
문서를 찾아내는 시나리오, 재시도해도 못 찾으면 정해진 횟수에서 멈추는 것, 처음부터 잘 찾으면
재구성이 아예 호출 안 되는 것, 감사 로그에 원문이 남는 것, `RAG_MAX_RETRIEVAL_ATTEMPTS=0`이면
재시도 자체가 꺼지는 것까지 확인했습니다. 테스트는 `TemplateLlmClient`의 실제 휴리스틱 품질에
기대지 않도록, 재구성 결과를 완전히 통제하는 Fake LLM 클라이언트로 그래프의 기계적 동작만
검증했습니다 (`TemplateLlmClient.reformulate()` 자체는 `tests/test_ai_provider_selection.py`에
별도 단위 테스트 3개로 검증).

### 5.1-1 VectorStore 3종 비교

| | FAISS | **Chroma** | Qdrant |
|---|---|---|---|
| 서버 필요 여부 | 불필요 (메모리) | **불필요 (로컬 파일)** | 필요 |
| 재시작 후 유지 | ❌ 사라짐 | **✅ 유지됨** | ✅ 유지됨 |
| 적합한 상황 | 빠른 개발/테스트 | **Redis/Docker 없이 로컬에서 AI 검색을 실제로 써보고 싶을 때** | 운영 배포 |

Redis/Celery 없이 로컬에서 개발 중이라면 `VECTOR_DB_PROVIDER=chroma`가 FAISS보다 실용적입니다 —
서버 재시작해도 색인이 안 날아가기 때문입니다. 실제로 upsert/검색/삭제/**프로세스 재시작 후 유지**까지
`tests/test_chroma_vector_store.py` 5개로 검증했습니다.

### 5.1-2 최종 그래프 구조 (condense → classify → 하이브리드 검색 → rerank → generate → validate)

```
condense ─► classify ──(off-topic)───────────────► handle_off_topic ─► END
              │
              ▼ (on-topic)
           retrieve ──(결과 충분)───────► rerank ─► generate ─► validate ──(근거 있음)──► END
              ▲   └─(빈약 & 재시도 여력)─► reformulate ┘                        │
              │                              ▲                          (근거 불확실 & 재시도 여력)
              └─(결과 없음 & 재시도 소진)──► handle_no_results ─► END            │
                                              ▲                                │
                                              └────────────────────────────────┘
```

| 기능 | 노드/구현 | 검증 |
|---|---|---|
| **질문 압축(condensation)** | `condense` — 멀티턴 후속 질문을 독립 질문으로 재구성해 검색에도 반영 | `tests/test_rag_condense.py` |
| **질문 분류** | `classify` — 인사/잡담이면 검색 없이 바로 안내 문구 반환 | `tests/test_rag_classify_validate.py` |
| **하이브리드 검색** | `retrieve`에서 벡터 검색 + 키워드(LIKE) 검색을 함께 수행해 문서 단위로 병합 | `tests/test_rag_hybrid_search.py` |
| **재랭킹** | `rerank` — `Reranker`(LLM 또는 Cohere)로 청크를 질문 관련도 순으로 재정렬 | `tests/test_rag_rerank.py` |
| **구조화 출력** | `generate` — `with_structured_output(RagAnswer)`로 원인/유사사례/해결방법을 받음 (JSON 파싱 실패 가능성 자체를 제거) | `tests/test_rag_pipeline.py`, `tests/test_rag_rerank.py` |
| **토큰 스트리밍** | `generate` 실행 도중 `get_stream_writer()`로 부분 답변을 커스텀 이벤트로 방출 | `tests/test_rag_multiturn_streaming.py`, `tests/test_rag_pipeline.py` (HTTP 레벨) |
| **자체 검증(self-critique)** | `validate` — 답변이 CONTEXT에만 근거했는지 재확인, 불확실하면 재시도 | `tests/test_rag_classify_validate.py` |
| **멀티턴 대화** | `AiSearchRequest.history`를 프롬프트에 포함 + `condense`로 검색에도 반영 (서버는 대화를 저장하지 않음) | `tests/test_rag_multiturn_streaming.py`, `tests/test_rag_condense.py` |
| **비용 절감 토글** | `RAG_ENABLE_CLASSIFY`/`RAG_ENABLE_RERANK`/`RAG_ENABLE_VALIDATION`로 각 단계 LLM 호출 개별 차단 | `tests/test_rag_cost_toggles.py` |
| **관측성(LangSmith)** | `LANGSMITH_TRACING=true`면 모든 LangChain/LangGraph 호출이 대시보드에 자동 기록 | `tests/test_observability.py` |

**질문 분류/자체 검증/재랭킹/질문압축도 벤더별로 동작이 다릅니다**: 실제 LLM(OpenAI/watsonx)은
`LlmClient`의 `classify()`/`check_grounded()`/`rerank()`/`condense_query()` 기본 구현으로 LLM에게
직접 물어보고, `TemplateLlmClient`(로컬 폴백)는 생성 능력이 없으므로 각각 규칙 기반 휴리스틱(짧은
인사 패턴 매칭, 항상 `True`, 키워드 겹침 카운트, 직전 사용자 발화 이어붙이기)으로 대체합니다.

**실제로 잡은 버그 2건**:
1. `_RagState`(TypedDict)에 `on_topic` 필드 선언을 빼먹었더니, LangGraph가 그 키를 상태 채널로
   인식하지 못해 노드가 반환한 값이 조용히 버려지고 항상 기본값(`True`)으로 되돌아가는 버그가
   있었습니다. 분류 테스트를 실제로 돌려보고서야 발견했습니다.
2. `condense`/`rerank` 노드가 할 일이 없어서 빈 dict(`{}`)를 반환하면, LangGraph의 "updates"
   스트림 모드가 이를 `None`으로 보고한다는 걸 발견했습니다(`{'condense': None}`). 스트리밍
   엔드포인트가 `partial_state`를 dict로 가정하고 있어서 `TypeError`가 났고, `RagService.stream()`에서
   `partial_state or {}`로 방어해 해결했습니다. 둘 다 정적 분석으로는 못 잡고 테스트를 실제로
   돌려보고서야 발견한 버그입니다.

**구조화 출력 도입 배경**: 이전 버전은 "JSON으로만 답하라"고 프롬프트로 부탁하고 응답 문자열에서
코드펜스를 벗겨가며 파싱했습니다. `with_structured_output(RagAnswer)`로 바꾸면서 이 파싱 실패
가능성 자체가 사라졌습니다. OpenAI는 실제로 `.with_structured_output(...).invoke()`/`.stream()`
둘 다 정상 동작하는 걸 구조적으로 확인했고(가짜 키로 인스턴스 생성·메서드 체이닝까지 확인),
watsonx는 여전히 이 저장소 네트워크 정책상 실제 IBM 인증 서버까지 도달하는 것만 확인했습니다
(watsonx.ai 미검증 항목과 동일한 제약).

**토큰 스트리밍 구현 방식**: LangGraph 1.2의 `get_stream_writer()` + `stream_mode=["updates", "custom"]`
조합을 사용합니다. `get_stream_writer()`는 `.invoke()`로 실행될 때는 안전한 no-op이고 `.stream()`으로
실행될 때만 실제로 이벤트를 내보내므로, `_generate_node` 코드 하나로 스트리밍 여부와 무관하게
동작합니다. `TemplateLlmClient`(로컬 폴백)는 진짜 토큰이 없으므로 필드가 하나씩(원인 → +유사사례 →
+해결방법) 채워지는 것처럼 흉내내는데, 이것도 실제 SSE HTTP 응답으로 점점 길어지는 것까지 확인했습니다.

**재랭킹 구현 방식**: `services/ai/reranker.py`로 `LlmClient`에서 분리했습니다 — "일반 채팅
LLM에게 순서를 물어보는 것"과 "전용 재랭킹 모델(Cohere)을 쓰는 것"은 LLM 벤더 선택과는 독립적인
문제이기 때문입니다(`RERANK_PROVIDER=llm|cohere`). LLM 기반(`LlmReranker`, 기본값)은 번호 매긴
발췌 목록을 주고 순서를 물어본 뒤 숫자만 정규식으로 추출하는 가벼운 방식이고, `CohereReranker`는
전용 재랭킹 모델(`cohere.Client.rerank()`)을 씁니다. Cohere도 watsonx와 같은 방식으로 검증했습니다
— 가짜 키로 호출하니 실제로 `api.cohere.com`까지 네트워크 요청이 나갔고 이 환경 정책상 거기서만
막혔습니다. 재시도(reformulate)로 이어질 빈약한 결과에 재랭킹 비용을 쓰지 않도록, "결과가
충분하다"고 판단된 경로에서만 실행됩니다.

**멀티턴 후속 질문이 검색에도 반영됩니다**: 이전 버전의 한계였던 "history는 LLM 프롬프트에만
반영되고 검색(retrieve)은 항상 이번 질문 그대로 수행되어, 후속 질문이 엉뚱한 문서를 찾는 문제"를
`condense` 노드로 해결했습니다. 대화 이력이 있을 때만 동작하며(첫 질문이면 LLM 호출 자체를 안 함),
`reformulate`와 같은 "질문을 다시 쓴다"는 패턴을 그대로 재사용했습니다. 단, 완전한 대화형 검색
(예: 검색 결과 자체를 이전 턴에서 이어받는 것)까지는 아니며, 서버가 대화를 저장하지 않는 stateless
설계라 클라이언트가 매 요청마다 전체 이력을 실어 보내야 하는 것은 여전한 한계입니다.

**LangSmith 연동 시 주의**: pydantic-settings는 `.env` 값을 `Settings` 객체 필드로만 읽고
`os.environ`에는 반영하지 않는데, LangChain의 트레이싱은 `os.environ`을 직접 읽습니다. 그래서
`core/observability.py::configure_langsmith()`가 앱/워커 시작 시 명시적으로 값을 옮겨주도록
만들었습니다 — 이 부분을 놓치면 `LANGSMITH_TRACING=true`로 켜도 아무 일도 안 일어납니다.

**비용 절감 토글에 대해 솔직히**: 지금 질문 하나당 최소 LLM 호출은 classify+rerank+generate+validate
4번(+조건에 따라 condense/reformulate 추가)입니다. 토글은 있지만 "이 상황에서 자동으로 꺼야 한다"는
판단 로직은 없습니다 — 언제 끌지는 운영하면서 트래픽 패턴을 보고 사람이 결정해야 합니다.
(반복되는 질문/재검색으로 인한 중복 호출은 아래 5.1-3 Context Caching으로 상당 부분 줄어듭니다.)

### 5.1-3 Context Caching

같은 입력이면 같은 출력이 기대되는 호출들 — `classify`/`check_grounded`/`rerank`/
`condense_query`/`generate_structured` 및 임베딩 계산 — 을 캐싱해서, 반복되는 질문이나
재검색 루프에서 실제 LLM/임베딩 API를 다시 부르지 않도록 했습니다. `services/ai/caching_llm_client.py`,
`services/ai/embedding_provider.py::CachingEmbeddingProvider`가 각각 `LlmClient`/`EmbeddingProvider`를
감싸는 데코레이터입니다 — `AI_PROVIDER`/`VECTOR_DB_PROVIDER`와 같은 패턴으로,
`get_llm_client()`/`get_embedding_provider()` 팩토리가 `CONTEXT_CACHE_ENABLED`에 따라 자동으로 씌웁니다.

| | InMemoryCache (기본값) | RedisCache |
|---|---|---|
| 저장 위치 | 프로세스 메모리 | 이미 Celery로 쓰고 있는 Redis 재사용 |
| 여러 프로세스/워커 간 공유 | ❌ | ✅ |
| 적합한 상황 | 로컬 개발 | 운영(API 서버 여러 대, Celery 워커) |

**무엇을 캐싱하고 무엇을 안 하는지**: `generate()`(스트리밍용 원문 생성)와 `reformulate()`는
의도적으로 캐싱하지 않았습니다. `generate()`를 캐싱하면 캐시 히트 시 토큰 스트리밍 효과 자체가
사라져서(완성된 답이 통째로 나옴) 사용자 체감 품질이 떨어지고, `reformulate()`는 매번 다른
실패 맥락에서 호출되어 캐시 재사용률이 낮을 것으로 판단했습니다.

**실제로 검증한 것**: 이 환경에 Redis 서버가 없어서 `apt install redis-server`로 실제 서버를
설치해 띄우고(`redis-server --daemonize yes`), `RedisCache`가 진짜 서버를 대상으로 get/set/TTL
만료/네임스페이스 격리까지 되는 것을 확인했습니다(`tests/test_context_caching.py`,
`TestRedisCacheAgainstRealServer` 4개). 임베딩 캐싱 효과도 실측했습니다 — 같은 질문을 두 번
임베딩했을 때 첫 번째는 4.37ms, 캐시 히트인 두 번째는 0.12ms로 약 36배 빨랐습니다(`LocalHashEmbeddingProvider`
기준이라 실제 OpenAI/watsonx 임베딩 API 대비 절감 폭은 이것보다 훨씬 클 것으로 예상됩니다 — API
호출 자체의 네트워크 왕복 시간이 없어지기 때문입니다).

**부분 캐시 히트도 처리합니다**: `CachingEmbeddingProvider.embed_texts()`는 리스트 안에서 일부
텍스트만 캐시에 있어도, 캐시 미스인 것만 모아 한 번에 벤더 API를 호출합니다(`tests/test_context_caching.py::test_partial_cache_hit_only_computes_misses`로 검증).

### 5.2 AI_PROVIDER — 어떤 벤더의 Embedding/LLM을 쓸지 선택

`.env`의 `AI_PROVIDER` 값 하나로 임베딩·LLM 벤더가 함께 전환됩니다. (이전에는
`OPENAI_API_KEY` 유무로만 자동 분기했는데, IBM watsonx.ai를 추가하면서 두 개의
API 키가 동시에 있을 수 있는 상황이 애매해져 명시적인 선택 방식으로 바꿨습니다.)

| `AI_PROVIDER` | Embedding | LLM | Vector Store |
|---|---|---|---|
| `local` (기본값) | `LocalHashEmbeddingProvider` — Feature Hashing 기반 결정론적 벡터 | `TemplateLlmClient` — `CONTEXT_JSON`을 추출 요약(extractive)해 JSON 조립 | `FaissVectorStore` (`VECTOR_DB_PROVIDER` 설정을 따로 따름) |
| `openai` | `OpenAiEmbeddingProvider` (langchain_openai) | `OpenAiLlmClient` (langchain_openai `ChatOpenAI`) | 〃 |
| `watsonx` | `WatsonxEmbeddingProvider` (langchain_ibm) | `WatsonxLlmClient` (langchain_ibm `ChatWatsonx`) | 〃 |

`local`이 없는 환경(이 저장소의 CI/로컬 개발 포함)에서도 색인 → 검색 → 응답 생성까지
**의미 있게** 동작해야 파이프라인의 오케스트레이션 버그를 조기에 잡을 수 있다고 판단해
만든 폴백입니다. `LocalHashEmbeddingProvider`는 의미 기반 임베딩이 아니라 "같은 단어가
많이 겹치면 유사도가 높다"는 수준의 Bag-of-Words 해싱이지만,
`tests/test_rag_pipeline.py::TestRetrieval`에서 확인했듯 서로 다른 주제의 문서(Redis vs
Kafka)를 올바르게 구분해 순위를 매길 만큼은 동작합니다.

> ⚠️ **watsonx.ai 미검증 (부분)**: `tests/test_ai_provider_selection.py`로
> `AI_PROVIDER=watsonx`일 때 `WatsonxEmbeddingProvider`/`WatsonxLlmClient`가
> 올바르게 선택되는지, 그리고 `langchain_ibm.WatsonxEmbeddings`/`ChatWatsonx`
> 생성자에 넘기는 파라미터(`model_id`, `url`, `project_id`, `apikey`)가 실제로
> 유효한지는 확인했습니다 — 가짜 키로 호출했을 때 파라미터 검증을 통과하고
> IBM의 실제 인증 서버(`iam.cloud.ibm.com`)까지 요청이 나가는 것을 확인했고,
> 이 환경의 네트워크 정책상 그 도메인이 막혀있어 거기서 실패했습니다. 즉
> **연동 코드 자체는 실제 네트워크 호출까지 도달하는 것을 확인**했지만, 진짜
> watsonx 계정으로 임베딩/응답이 정상적으로 오는 엔드투엔드 테스트는 못
> 했습니다. 특히 `WATSONX_EMBEDDING_DIMENSION=384`는
> `granite-embedding-107m-multilingual` 모델의 알려진 차원을 그대로 적어둔
> 값이라, 실제 계정에서 한 번 확인해 보시길 권합니다 (차원이 다르면
> `FaissVectorStore`/`QdrantVectorStore` 색인 시점에 에러가 납니다).

> ✅ **Qdrant 실제 검증 완료**: 이 개발 환경에는 Docker가 없지만, Qdrant 바이너리를
> GitHub 릴리즈에서 직접 받아 실제로 띄우고 `QdrantVectorStore`를 통합 테스트했습니다
> (벡터 삽입/검색/삭제, `EmbeddingService`→`RetrieverService` 전체 파이프라인).
> 이 과정에서 실제 버그도 하나 발견해 고쳤습니다 — 최신 `qdrant-client`(1.18)에서
> `.search()` 메서드가 제거되고 `.query_points()`로 바뀐 것을 반영하지 못하고 있었습니다
> (`requirements.txt`의 `qdrant-client` 버전도 실제 검증한 1.18.0으로 갱신).
> 다만 이 서버는 임시로 띄운 로컬 바이너리이므로, 실제 `docker compose`로 띄운
> Qdrant 컨테이너에서도 한 번 더 확인해 보시길 권장합니다.

### 5.3 문서 변경 → 색인 트리거 흐름 (FR-AI-06)

```
DocumentService.create_document/update_document/delete_document
        ↓ (커밋 이후)
DocumentIndexer.index_document / remove_document
        ↓
CeleryDocumentIndexer (api 요청 경로에서 주입됨, api/deps.py get_document_service)
        ↓ .delay()  — 큐잉 실패 시 예외를 흡수하고 로깅만 함 (사용자 요청은 그대로 성공)
embedding.index_document / embedding.remove_document (Celery 워커)
        ↓
EmbeddingService.index_document/remove_document (새 DB 세션으로 실행)
```

`DocumentService`는 기본값으로 `NoOpDocumentIndexer`를 사용하므로, 단위 테스트나 배치 스크립트에서
Celery/Redis 없이도 CRUD 로직만 독립적으로 검증할 수 있습니다. 실제 API 요청 경로에서만
`api/deps.py::get_document_service`가 `CeleryDocumentIndexer`를 주입합니다.
`tests/test_rag_pipeline.py::TestAiSearchApiEndpoint`는 브로커가 없는 테스트 환경에서
큐잉이 실패하는 것을 감안해, Celery 워커가 할 일(`EmbeddingService.index_document`)을
테스트 코드에서 동기적으로 대신 호출해 API 엔드투엔드를 검증합니다.

### 5.4 테스트 커버리지 (`tests/test_rag_pipeline.py`, 18개)

- **청킹**: 짧은 텍스트/문단 결합/긴 문단 강제 분할(overlap 검증)/빈 텍스트
- **색인**: 임베딩 생성 및 저장, 재색인 시 중복 없이 교체, 문서 삭제 시 정리, Soft Delete된 문서는 색인 안 함
- **검색**: 서로 다른 주제 문서 중 관련도 높은 문서가 먼저 나오는지, 빈 인덱스에서 빈 결과
- **RagService 엔드투엔드**: 구조화된 답변 + 출처(citation) 반환, 검색 결과 없을 때 안내 메시지, `project_id` 스코프 필터링, 감사 로그 기록
- **DocumentService ↔ Indexer 연동**: create/update/delete가 정확한 시점에 인덱서를 호출하는지 (Celery 없이 Spy로 검증)
- **API 엔드투엔드**: `/api/v1/documents` → 색인 → `/api/v1/ai/search` 전체 흐름

---

## 6. DB 마이그레이션 (Alembic)

`alembic/versions/60af6b288466_initial_schema.py`가 ERD의 14개 테이블을 전부 생성하는
초기 마이그레이션입니다. `alembic revision --autogenerate`로 모델에서 자동 생성한 뒤,
ERD 설계 노트에 있던 MySQL FULLTEXT 인덱스(`title, problem_description, error_message`)는
SQLAlchemy ORM으로 표현할 수 없어 raw DDL로 직접 추가했습니다. 이 부분은 SQLite 등
다른 방언(테스트 환경 포함)에서는 건너뛰도록 방언을 체크해서, 마이그레이션 자체가 CI에서도
안전하게 실행됩니다.

**실제로 검증한 것**: 이 환경에는 살아있는 MySQL 서버가 없어, 로컬 MySQL에 대고 직접
`alembic upgrade head`를 실행해보지는 못했습니다. 대신 SQLite로 같은 것을 검증했습니다.
- `alembic upgrade head` — 빈 DB에서 14개 테이블 전부 생성 확인
- `alembic downgrade base` — 14개 테이블 전부 깨끗하게 롤백되는 것까지 확인

마이그레이션 스크립트 자체는 SQLAlchemy Core 연산(`op.create_table` 등)으로 되어 있어
방언에 무관하게 동일한 Python 코드가 실행되므로, MySQL에서도 동일하게 동작할 것으로
예상하지만 **실제 MySQL 서버에서 한 번 실행해 확인하시길 권장합니다.**

```bash
# 새 모델을 추가/수정한 뒤 마이그레이션을 추가로 생성하려면
alembic revision --autogenerate -m "설명"
alembic upgrade head
```

---

## 7. 로컬 실행

```bash
cp .env.example .env
pip install -r requirements.txt

# DB/Redis/Qdrant까지 한 번에 띄우고 싶다면
docker compose -f docker/docker-compose.yml up -d mysql redis qdrant

# 마이그레이션 적용 (docker-compose로 띄우면 entrypoint.sh가 자동으로 실행함)
alembic upgrade head

uvicorn app.main:app --reload
# http://localhost:8000/health
```

### 7.1 MySQL Workbench로 직접 접속하기

AWS 등 원격 배포 없이 로컬에서만 돌리는 경우, docker-compose가 띄운 MySQL 컨테이너의
3306 포트가 호스트에도 그대로 열려있으므로 Workbench에서 바로 접속할 수 있습니다.

| 항목 | 값 |
|---|---|
| Hostname | `127.0.0.1` (또는 `localhost`) |
| Port | `3306` |
| Username | `devtrouble` (전체 권한이 필요하면 `root`) |
| Password | `devtrouble` (root는 `root`) |
| Default Schema | `devtrouble` |

`Authentication plugin 'caching_sha2_password' cannot be loaded` 에러가 뜨면 MySQL 8의
기본 인증 방식 때문입니다 — 접속 설정 창에서 뜨는 "Get Server Public Key" 확인창을
승인하거나, Advanced 탭에서 SSL을 꺼보세요.

---

## 8. 다음 단계

1. **API Spec**: 각 엔드포인트의 요청/응답 예시, 에러 케이스를 표 형태로 확정 (OpenAPI 문서 fine-tuning 포함)
2. **실제 Docker MySQL/Qdrant 스모크 테스트**: `docker compose up` 이후 실제 컨테이너 대상으로 한 번 더 확인
   (이번에 로컬 바이너리로는 검증 완료 — 6번 섹션 참고)
3. **CI/CD**: `devtrouble-ai/.github/workflows/`에 backend-ci.yml/frontend-ci.yml 작성 완료.
   실제 GitHub 저장소에 push해서 워크플로가 정상 동작하는지 확인 필요 (로컬에서는 각 스텝을
   개별적으로 실행해 통과를 확인했지만, GitHub Actions 러너에서 통째로 돌려본 적은 없음)
4. **관리자 페이지**: 유저 관리, 문서 강제 삭제 등 (한 차례 구현했다가 이번 요청으로 롤백함 —
   필요해지면 태그 병합(`TagService.merge_tags`)과 같은 패턴으로 다시 추가하면 됨)
5. **프론트엔드는 스트리밍/멀티턴/on_topic·is_grounded까지는 반영했지만, 재랭킹/구조화 출력은
   API 계약이 그대로라 프론트 변경이 필요 없었습니다.** 실제 브라우저에서 눌러보며 확인은
   못 했으니(이 환경은 로컬 서버+브라우저 테스트가 안 됨) 한 번 직접 확인해 보시길 권합니다 —
   프론트 쪽 README(`devtrouble-ai-frontend/README.md`)에 검증 범위를 정리해 뒀습니다.

바로 다음으로 무엇을 진행할까요?
