# DevTrouble AI — Frontend

React + TypeScript + Vite 기반 프론트엔드입니다. 백엔드(`devtrouble-ai-backend`)의
인증(JWT), 트러블슈팅 문서 CRUD, AI 검색(RAG) API를 그대로 소비합니다.

## 1. 폴더 구조 (PRD 기준)

```
src/
├── pages/        # 라우트 단위 화면 (Login, SignUp, ProjectList, DocumentList/Detail/Form, AiSearch, MyActivity)
├── components/   # 재사용 UI (Button, FormField, Feedback, TagBadge, MarkdownPreview, ProtectedRoute)
├── hooks/        # React Query 훅 (useDocuments, useAiSearch)
├── services/     # axios 기반 API 호출 함수 (authService, documentService, aiService)
├── layouts/      # MainLayout (상단 네비게이션)
├── types/        # 백엔드 Pydantic 스키마와 1:1 매핑된 TS 타입
├── store/        # AuthContext (전역 인증 상태)
└── lib/          # axios 인스턴스, 토큰 저장소
```

## 2. 핵심 설계 결정

### 인증 — Axios 인터셉터의 자동 Refresh
`lib/axios.ts`가 모든 요청에 Access Token을 자동으로 붙이고, 401 응답을 받으면
Refresh Token으로 자동 재발급 후 원래 요청을 재시도합니다. 동시에 여러 요청이 401을
맞아도 재발급은 한 번만 수행되도록 Promise를 공유합니다. 재발급마저 실패하면
(`refresh_token` 만료 등) `devtrouble:session-expired` 커스텀 이벤트를 쏘고,
`AuthContext`가 이를 구독해 전역 로그아웃 처리를 합니다 — axios 계층이 React Router를
직접 알 필요가 없도록 이벤트로 느슨하게 연결했습니다.

### API 응답 언래핑
백엔드는 `{success, data, error}` 표준 포맷을 쓰므로, `lib/axios.ts::unwrap()`이
성공 시 `data`만 꺼내고 실패 시 `ApiError`(코드+메시지)를 던지도록 통일했습니다.
각 `services/*.ts`는 이 함수를 통해 얇게 API를 감쌉니다.

### 상태 관리 — React Query + Context, 별도 전역 스토어 없음
서버 상태(문서 목록/상세)는 React Query가, 인증 상태만 Context로 관리합니다.
PRD 프론트엔드 스택에 Redux/Zustand가 명시되지 않아 추가하지 않았습니다.

### shadcn/ui 관련 안내
PRD 스택에 shadcn/ui가 명시되어 있으나, 이 저장소에는 shadcn CLI로 컴포넌트를
개별 추가하는 과정을 생략하고 **shadcn과 동일한 시각적 컨벤션(rounded-md, 여백, 포커스
링)을 따르는 경량 Tailwind 컴포넌트**를 직접 작성했습니다(`components/Button.tsx`,
`FormField.tsx` 등). 실제 shadcn 컴포넌트가 필요하면 `npx shadcn@latest add button input`
등으로 교체하면 기존 사용처는 거의 그대로 유지됩니다.

### AI 검색 — SSE 스트리밍은 axios가 아니라 순수 fetch로
`services/aiService.ts::searchStream()`만 axios 인스턴스를 안 쓰고 순수 `fetch` +
`ReadableStream`을 직접 씁니다. axios는 브라우저에서 스트리밍 응답을 다루기 번거롭고,
이 엔드포인트(`/ai/search/stream`)는 인증도 필요 없어서 인터셉터의 이점도 없기 때문입니다.
SSE 이벤트가 네트워크 청크 중간에서 잘려 오는 경우(`data: {...` 까지만 오고 나머지는
다음 청크로)를 버퍼링으로 재조합하는데, 실제로 이벤트가 중간에 끊기는 상황을
시뮬레이션해서 정상적으로 재조합되는지 확인했습니다.

`hooks/useAiSearch.ts::useAiSearchStream()`이 이 스트림을 소비하면서 두 가지를 노출합니다:
- `stage` — 지금 그래프가 어느 노드(classify/retrieve/rerank/generate/validate)를
  지나는지, `AiSearchPage`가 한국어 라벨로 보여줍니다.
- `partialAnswer` — `generate` 노드 실행 중 점점 채워지는 답변(백엔드의 "token" 이벤트).
  실제 챗봇처럼 답변이 타이핑되듯 나오는 효과를 냅니다.

### 멀티턴 대화 UI
`AiSearchPage`를 단발성 검색 폼에서 카톡 같은 대화형 UI로 바꿨습니다. 질문/답변이
말풍선으로 쌓이고, 다음 질문을 보낼 때 지금까지의 turns를 `ConversationMessage[]`로
변환해 `history`에 실어 보냅니다 — 백엔드가 대화를 저장하지 않는 stateless 설계라서,
"이전 대화를 기억하는 것처럼 보이는" 책임은 전적으로 프론트가 매번 이력을 다시
보내는 데 있습니다.

## 3. 검증한 것 / 못한 것

✅ **실제로 검증**
- `npx tsc -b` — 타입 에러 없음
- `npm run build` (`tsc -b && vite build`) — 프로덕션 빌드 성공
- `npx oxlint` — 경고 1개(Fast Refresh 관련, 기능에 영향 없음), 에러 0개
- SSE 파싱 로직(`aiService.searchStream`의 버퍼링) — Node로 청크 경계에서 이벤트가
  잘리는 시나리오를 시뮬레이션해서 정상적으로 재조합되는 것까지 확인

⚠️ **검증하지 못함 (정직하게 밝힙니다)**
이 개발 환경은 루프백(localhost) 소켓 바인딩/접속이 제한되어 있어, `npm run dev`로
실제 서버를 띄우고 브라우저에서 동작을 확인하는 런타임 스모크 테스트는 하지 못했습니다.
빌드/타입체크가 전부 통과했으므로 정적으로는 문제가 없지만, 실제 로그인 → 문서 작성 →
AI 검색 흐름은 로컬(`npm run dev`, 백엔드는 `uvicorn app.main:app --reload`로 8000번 포트
기동)에서 한 번 확인해 보시길 권합니다.

## 4. 알려진 제약

- **즐겨찾기/최근 본 문서 목록에 문서 제목이 안 보입니다.** 백엔드 `GET /bookmarks`,
  `GET /bookmarks/recent-views`가 문서 ID 목록만 반환하기 때문입니다(`BookmarkService`
  설계 노트 참고). 문서 상세 조회 API(`GET /documents/{id}`)는 호출할 때마다 조회수를
  올리므로, 목록 화면에서 제목을 보여주려고 그 API를 그대로 재사용하면 목록을 열어보기만
  해도 조회수가 올라가는 부작용이 생겨 의도적으로 하지 않았습니다. 제목까지 보여주려면
  백엔드에 조회수를 올리지 않는 별도의 "제목만 가져오는" 엔드포인트가 필요합니다.

## 5. 로컬 실행

```bash
npm install
cp .env.example .env   # 기본값은 /api/v1 (vite dev proxy 사용)
npm run dev
# http://localhost:5173 (백엔드는 http://localhost:8000 에서 별도 기동 필요)
```

`vite.config.ts`의 `server.proxy`가 `/api` 요청을 `http://localhost:8000`으로 전달하므로,
개발 중에는 CORS 설정 없이 바로 연동됩니다. 운영 배포 시에는 `.env`의
`VITE_API_BASE_URL`을 실제 API 도메인으로 지정하세요.

## 6. 다음 단계

1. 로컬에서 백엔드와 함께 실제 브라우저 스모크 테스트
2. 즐겨찾기/최근 본 문서 목록에 문서 제목을 보여주려면 백엔드에 경량 조회 API 추가
3. Vitest + React Testing Library로 컴포넌트/훅 단위 테스트 추가
