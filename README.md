# DevTrouble AI — 전체 스택 Docker 실행

이 디렉토리는 `devtrouble-ai-backend`(FastAPI)와 `devtrouble-ai-frontend`(React)를
하나의 `docker-compose.yml`로 묶어 전체 스택을 한 번에 띄우기 위한 루트입니다.

```
devtrouble-ai/
├── docker-compose.yml          # 루트 오케스트레이션 (이 파일)
├── devtrouble-ai-backend/      # FastAPI + Celery
└── devtrouble-ai-frontend/     # React + Nginx
```

## 1. 실행 방법

```bash
cd devtrouble-ai

# 백엔드 환경변수 준비 — 반드시 .env.docker.example을 사용할 것 (아래 2번 참고)
cp devtrouble-ai-backend/.env.docker.example devtrouble-ai-backend/.env

# 전체 스택 빌드 + 기동
docker compose up --build
```

기동 후 접속:
- 프론트엔드: http://localhost:3000
- 백엔드 API: http://localhost:8000 (`/health`, `/docs`)
- MySQL: `127.0.0.1:3306` — Workbench에서 바로 접속 가능
  (Username: `devtrouble` / Password: `devtrouble` / Schema: `devtrouble`,
  전체 권한이 필요하면 `root`/`root`)
- Redis: localhost:6379, Qdrant: localhost:6333

`api` 컨테이너는 시작 시 `docker/entrypoint.sh`가 `alembic upgrade head`를 자동 실행한 뒤
uvicorn을 기동합니다. `celery-worker`는 같은 마이그레이션을 중복 실행하지 않도록
`RUN_MIGRATIONS=false`로 오버라이드되어 있습니다.

## 2. 왜 `.env.example`이 아니라 `.env.docker.example`을 써야 하는가

`devtrouble-ai-backend/.env.example`은 **호스트에서 직접 `uvicorn`을 실행할 때**
(DB/Redis가 `localhost` 포트로 노출된 상태)를 가정합니다.

반면 docker-compose로 `api`/`celery-worker` 컨테이너를 띄우면, 이 컨테이너들은
`mysql`/`redis`/`qdrant`라는 **서비스명**으로 서로를 찾습니다 (컨테이너에게 "localhost"는
자기 자신을 가리키므로 `localhost:3306`으로는 MySQL 컨테이너에 닿지 못합니다).
그래서 호스트를 서비스명으로 바꾼 `.env.docker.example`을 별도로 만들었습니다.

| | `.env.example` | `.env.docker.example` |
|---|---|---|
| 용도 | 호스트에서 `uvicorn` 직접 실행 | `docker compose up`으로 전체 스택 실행 |
| DB/Redis 호스트 | `localhost` | `mysql`, `redis` (서비스명) |
| VECTOR_DB_PROVIDER | `faiss` | `qdrant` (컨테이너로 항상 띄우므로) |

## 3. 프론트엔드가 백엔드를 찾는 방식

`devtrouble-ai-frontend`는 Nginx 컨테이너로 서빙됩니다. 브라우저가 `/api/v1/...`로
요청하면 **같은 origin(localhost:3000)** 으로 가고, Nginx(`docker/nginx.conf`)가
compose 네트워크 안에서 `http://api:8000/api/v1/...`로 프록시합니다. 그래서 프론트엔드
빌드 시 `VITE_API_BASE_URL=/api/v1`(상대 경로)이면 충분하며, CORS 설정도 필요 없습니다.

## 4. 개별 서비스만 띄우고 싶다면

각 프로젝트 폴더에도 자체 `docker/docker-compose.yml`이 있습니다.

```bash
# 백엔드 + 인프라만
cd devtrouble-ai-backend
cp .env.example .env   # 호스트에서 프론트엔드 없이 API만 테스트할 때
docker compose -f docker/docker-compose.yml up --build
```

프론트엔드만 별도로 띄우려면 `devtrouble-ai-frontend`에서 `npm run dev`로 로컬 개발
서버(Vite proxy 사용)를 쓰는 것을 권장합니다. Docker로 프론트엔드 이미지만 빌드하려면:

```bash
cd devtrouble-ai-frontend
docker build -f docker/Dockerfile -t devtrouble-ai-frontend .
```

## 5. 검증 범위 (정직하게 밝힙니다)

이 개발 환경에는 Docker 데몬이 없어 `docker compose up`을 실제로 실행해보지는 못했습니다.
대신 다음을 확인했습니다.
- 두 `docker-compose.yml` 모두 YAML 문법 검증 통과 (`yaml.safe_load`)
- Dockerfile 내 `COPY`/`ARG`/`ENV` 경로가 실제 프로젝트 구조(빌드 컨텍스트 기준 상대경로)와 일치하는지 수동 대조
- `nginx.conf`는 표준 리버스 프록시 + SPA fallback 패턴으로, 로컬에 nginx 바이너리를 설치할
  수 없어 `nginx -t` 문법 검사는 하지 못함

로컬 Docker 환경에서 `docker compose up --build` 한 번 실행해 실제 기동을 확인해 보시길
권장합니다. 특히 MySQL 최초 초기화(healthcheck 통과)까지 시간이 걸릴 수 있습니다.

## 6. CI/CD (GitHub Actions)

`.github/workflows/backend-ci.yml`, `frontend-ci.yml`이 있습니다. 둘 다 `paths` 필터로
해당 프로젝트 디렉토리가 변경됐을 때만 실행되고, `working-directory`를 각 프로젝트
폴더로 고정합니다 (이 `devtrouble-ai/` 모노레포 구조 기준).

- **backend-ci.yml**: `ruff check` → `pytest`(SQLite 기반, 별도 DB 서비스 불필요) →
  Alembic 마이그레이션 스모크 테스트(`upgrade head` → `downgrade base`)
- **frontend-ci.yml**: `tsc -b`(타입체크) → `oxlint` → `npm run build`

각 스텝은 로컬에서 개별적으로 실행해 통과를 확인했습니다(`ruff check` 결과 실제 버그
1건 발견 및 수정 — `app/models/user.py`에 `TYPE_CHECKING` import 누락). 다만 **GitHub
Actions 러너에서 워크플로 전체를 통째로 실행해본 적은 없으므로**, 실제 저장소에 push한
뒤 Actions 탭에서 한 번 확인해 보시길 권장합니다.

## 7. 다음 단계

- 운영 배포용 `docker-compose.prod.yml`(포트 미노출, 이미지 태그 고정, 리소스 제한) 분리
- Helm Chart 작성 (PRD의 EKS 배포 목표 대응)
- CI에 Docker 이미지 빌드/푸시 스텝 추가 (현재는 테스트만 실행)
