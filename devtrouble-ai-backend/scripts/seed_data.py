"""
로컬 개발/데모용 더미 데이터 시딩 스크립트.

사용법 (devtrouble-ai-backend 루트에서):
    python scripts/seed_data.py

이미 만들어둔 유저/프로젝트/문서가 있으면 건너뛰고, 없는 것만 채워 넣는다
(여러 번 실행해도 중복 생성되지 않는다 — 이메일/프로젝트명/문서 제목 기준으로 존재 여부를 확인).

AI 검색까지 바로 되게 하려고, 문서를 만든 뒤 Celery(비동기 큐) 없이
EmbeddingService.index_document()를 직접(동기적으로) 호출해서 색인까지 한 번에 끝낸다.
(VECTOR_DB_PROVIDER=faiss 기본값이면 이 프로세스가 끝나는 순간 색인은 사라진다 —
AI 검색까지 유지하고 싶으면 .env에서 VECTOR_DB_PROVIDER=chroma로 바꿔서 실행할 것.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.bookmark import Bookmark
from app.models.comment import Comment
from app.models.project import Project
from app.models.recent_view import RecentView
from app.models.trouble_document import TroubleDocument
from app.models.user import User
from app.repositories.tag_repository import TagRepository
from app.repositories.user_repository import UserRepository
from app.services.ai.embedding_service import EmbeddingService

SEED_USERS = [
    {"email": "test1@test.com", "nickname": "정우", "password": "password123"},
    {"email": "dev2@test.com", "nickname": "서연", "password": "password123"},
    {"email": "dev3@test.com", "nickname": "민준", "password": "password123"},
    {"email": "dev4@test.com", "nickname": "지은", "password": "password123"},
    {"email": "dev5@test.com", "nickname": "현우", "password": "password123"},
]

SEED_PROJECTS = [
    {"name": "결제 시스템 리팩토링", "description": "레거시 결제 모듈을 정리하는 프로젝트"},
    {"name": "알림 서비스 안정화", "description": "푸시/이메일 알림 인프라 개선"},
    {"name": "프론트엔드 성능 개선", "description": "React 앱 렌더링/빌드 성능 최적화"},
    {"name": "인프라 마이그레이션", "description": "온프레미스에서 Kubernetes 기반으로 전환"},
]

# (project_index, author_index, title, problem_description, error_message,
#  stack_trace, solution, retrospective, tags)
SEED_DOCUMENTS = [
    (
        0, 0,
        "SQLAlchemy IntegrityError: Duplicate entry",
        "배포 중 결제 내역을 저장하는 API에서 갑자기 500 에러가 발생했다. "
        "동시에 여러 요청이 들어올 때만 재현되는 것으로 보인다.",
        "IntegrityError: (1062, \"Duplicate entry '1024' for key 'payments.PRIMARY'\")",
        (
            'Traceback (most recent call last):\n'
            '  File "app/services/payment_service.py", line 42, in create_payment\n'
            "    self.db.commit()\n"
            "sqlalchemy.exc.IntegrityError: ..."
        ),
        "PK 채번 로직이 애플리케이션 레벨에서 SELECT MAX(id)+1로 되어 있었던 게 원인이었다. "
        "AUTO_INCREMENT로 변경하고, 동시성이 필요한 곳은 UUID PK로 전환했다.",
        "동시성 테스트를 배포 전 체크리스트에 추가해야겠다.",
        ["mysql", "sqlalchemy", "deadlock"],
    ),
    (
        0, 0,
        "Redis 커넥션이 주기적으로 끊기는 현상",
        "운영 환경에서 몇 시간마다 Redis 커넥션이 끊기고, 재연결까지 몇 초간 요청이 실패한다.",
        "redis.exceptions.ConnectionError: Connection closed by server.",
        None,
        "Redis 서버의 timeout 설정(idle connection 정리 주기)이 짧게 잡혀있었다. "
        "커넥션 풀에 socket_keepalive=True와 health_check_interval을 설정해 해결했다.",
        None,
        ["redis", "timeout", "connection-pool"],
    ),
    (
        0, 1,
        "Celery 태스크가 재시도 없이 조용히 실패함",
        "임베딩 색인 태스크가 실패해도 로그에 아무것도 안 남고, 재시도도 안 되는 것을 발견했다.",
        None,
        None,
        "task 데코레이터에 bind=True, max_retries를 설정하지 않아서 기본값(재시도 없음)으로 "
        "동작하고 있었다. bind=True와 self.retry(exc=exc)를 추가해 재시도가 되도록 고쳤다.",
        "Celery 태스크는 항상 실패 시나리오를 먼저 테스트해야 한다는 걸 배웠다.",
        ["celery", "비동기", "재시도"],
    ),
    (
        1, 1,
        "Kafka Consumer Lag이 계속 쌓이는 문제",
        "알림 발송용 Kafka Consumer의 처리 지연이 시간이 지날수록 계속 누적된다.",
        None,
        None,
        "Consumer 그룹의 파티션 수 대비 인스턴스 수가 부족했다. 파티션 수를 늘리고 "
        "Consumer 인스턴스를 파티션 수만큼 늘려 병렬 처리량을 확보했다.",
        None,
        ["kafka", "consumer-lag"],
    ),
    (
        1, 0,
        "FCM 푸시 알림이 iOS에서만 전달되지 않음",
        "안드로이드는 정상인데 iOS 기기에서만 푸시 알림이 오지 않는다는 문의가 늘었다.",
        "APNs error: BadDeviceToken",
        None,
        "APNs 인증서가 프로덕션용이 아니라 샌드박스용으로 등록되어 있었다. "
        "프로덕션 인증서로 교체하고, 토큰 갱신 주기를 짧게 조정했다.",
        "iOS/Android 푸시는 인증서 환경(sandbox/production)을 항상 명시적으로 확인해야 한다.",
        ["fcm", "ios", "push-notification"],
    ),
    (
        2, 2,
        "React useEffect가 무한 루프에 빠짐",
        "컴포넌트가 계속 리렌더링되면서 브라우저가 멈추는 현상이 발생했다.",
        "Maximum update depth exceeded. This can happen when a component calls setState "
        "inside useEffect, but useEffect either doesn't have a dependency array...",
        None,
        "useEffect의 의존성 배열에 매 렌더링마다 새로 생성되는 객체를 그대로 넣고 있었다. "
        "useMemo로 감싸거나 의존성을 원시값으로 좁혀서 해결했다.",
        "의존성 배열은 항상 ESLint exhaustive-deps 규칙으로 검증하기로 했다.",
        ["react", "useeffect", "무한루프"],
    ),
    (
        2, 3,
        "Webpack 빌드가 갑자기 5배 느려짐",
        "어제까지 30초 걸리던 빌드가 오늘부터 2분 넘게 걸린다. 코드 변경 사항은 거의 없다.",
        None,
        None,
        "새로 추가한 라이브러리가 barrel file(index.ts에서 전체 re-export)을 쓰고 있어서 "
        "트리쉐이킹이 안 되고 있었다. 필요한 모듈만 직접 import하도록 바꾸고, "
        "babel-loader에 cacheDirectory 옵션을 켜서 해결했다.",
        None,
        ["webpack", "빌드성능", "번들사이즈"],
    ),
    (
        3, 4,
        "Kubernetes Pod가 CrashLoopBackOff 상태에 빠짐",
        "배포 직후 Pod가 계속 재시작을 반복하며 서비스가 올라오지 않는다.",
        "CrashLoopBackOff",
        (
            "Liveness probe failed: Get \"http://10.0.1.5:8080/health\": "
            "context deadline exceeded (Client.Timeout exceeded while awaiting headers)"
        ),
        "애플리케이션 초기화(DB 커넥션 풀 워밍업)에 5초 이상 걸리는데 livenessProbe의 "
        "initialDelaySeconds가 3초로 짧게 설정되어 있었다. initialDelaySeconds를 늘리고 "
        "startupProbe를 별도로 추가해 해결했다.",
        None,
        ["kubernetes", "k8s", "liveness-probe"],
    ),
    (
        3, 4,
        "Docker 이미지 빌드시 용량이 계속 커짐",
        "이미지 크기가 어느새 2GB를 넘어서, 배포할 때마다 pull 시간이 오래 걸린다.",
        None,
        None,
        "빌드 도구와 런타임을 한 스테이지에서 같이 쓰고 있었다. 멀티스테이지 빌드로 나눠서 "
        "builder 스테이지의 산출물만 최종 이미지에 복사하도록 바꿨더니 300MB대로 줄었다.",
        "Dockerfile 리뷰 체크리스트에 '멀티스테이지 적용 여부'를 추가했다.",
        ["docker", "이미지최적화", "멀티스테이지빌드"],
    ),
    (
        0, 0,
        "PostgreSQL 커넥션 풀이 고갈되어 신규 요청이 전부 실패",
        "트래픽이 몰리는 시간대에 DB 커넥션을 못 잡아서 요청이 타임아웃난다.",
        "FATAL: too many connections for role \"app_user\"",
        None,
        "여러 애플리케이션 인스턴스가 각자 커넥션 풀을 크게 잡고 있어서 DB의 "
        "max_connections을 초과하고 있었다. PgBouncer를 도입해 커넥션을 풀링하고, "
        "애플리케이션 쪽 풀 크기는 줄였다.",
        None,
        ["postgresql", "connection-pool", "pgbouncer"],
    ),
    (
        1, 1,
        "Nginx에서 502 Bad Gateway가 간헐적으로 발생",
        "트래픽이 많지 않은데도 하루에 몇 번씩 502가 찍힌다는 알림이 온다.",
        "upstream prematurely closed connection while reading response header from upstream",
        None,
        "백엔드 애플리케이션의 응답이 nginx의 proxy_read_timeout보다 오래 걸리는 요청이 "
        "가끔 있었다. 느린 엔드포인트를 별도로 파악해 timeout을 늘리고, 해당 API는 "
        "비동기 처리로 전환했다.",
        None,
        ["nginx", "502", "timeout"],
    ),
    (
        2, 2,
        "TypeScript strict 모드 전환 후 빌드 에러가 수백 개 발생",
        "타입 안정성을 높이려고 strict: true로 바꿨더니 기존 코드에서 에러가 쏟아졌다.",
        None,
        None,
        "한 번에 다 고치는 대신 tsconfig에서 파일 단위로 strict를 점진 적용하는 방식을 "
        "썼다. 새 코드부터 strict를 강제하고, 레거시 코드는 마이그레이션 일정을 잡아 "
        "단계적으로 정리했다.",
        "처음부터 strict 모드로 시작하는 게 나중에 훨씬 편하다는 걸 다시 느꼈다.",
        ["typescript", "strict-mode", "마이그레이션"],
    ),
    (
        0, 3,
        "JWT 토큰 만료 시각이 서버마다 다르게 계산됨",
        "같은 토큰인데 어떤 서버에서는 만료로 처리되고 어떤 서버에서는 유효하다고 나온다.",
        None,
        None,
        "서버 간 시스템 시간이 몇 초씩 어긋나 있었다(NTP 동기화 안 됨). 모든 서버에 "
        "chrony로 NTP 동기화를 설정하고, JWT 검증 시 약간의 leeway(허용 오차)도 뒀다.",
        None,
        ["jwt", "ntp", "timezone"],
    ),
    (
        3, 4,
        "GitHub Actions 캐시가 매번 miss로 뜸",
        "의존성 설치 캐시를 설정했는데도 매번 처음부터 다시 설치해서 CI가 느리다.",
        None,
        None,
        "cache key에 OS 버전만 포함하고 lock 파일 해시를 안 넣고 있어서, 사실상 "
        "항상 같은 키로 캐시를 찾고 있었다(그런데 실제로는 lock 파일이 자주 바뀌어 "
        "무효화가 필요한 상황이었음). key에 `hashFiles('**/package-lock.json')`을 "
        "추가해서 의도한 대로 캐시가 재사용되도록 고쳤다.",
        None,
        ["github-actions", "ci-cd", "캐시"],
    ),
    (
        1, 0,
        "WebSocket 연결이 로드밸런서 뒤에서 자꾸 끊김",
        "실시간 알림용 WebSocket이 몇 분마다 재연결되면서 알림이 누락되는 경우가 있다.",
        "WebSocket connection closed with code 1006 (abnormal closure)",
        None,
        "로드밸런서의 idle timeout이 WebSocket의 하트비트 주기보다 짧게 설정되어 "
        "있었다. 로드밸런서에 sticky session과 더 긴 idle timeout을 설정하고, "
        "클라이언트 쪽 하트비트 주기도 줄였다.",
        None,
        ["websocket", "load-balancer", "sticky-session"],
    ),
]

SEED_COMMENTS = [
    (0, 1, "저희 팀도 똑같은 문제 겪었어요. UUID PK 전환 방식 자세히 공유해주실 수 있나요?"),
    (1, 1, "health_check_interval 값은 몇 초로 설정하셨나요?"),
    (5, 3, "혹시 useCallback도 같이 써야 하나요?"),
    (7, 0, "저희도 liveness probe 타임아웃 때문에 고생했어요. startupProbe 설정값 공유 가능할까요?"),
    (9, 2, "PgBouncer는 transaction 모드로 쓰시나요, session 모드로 쓰시나요?"),
    (13, 1, "leeway는 몇 초 정도로 두셨어요?"),
]

# (user_index, document_index)
SEED_BOOKMARKS = [
    (1, 0),
    (1, 5),
    (2, 7),
    (3, 9),
]

# (user_index, document_index)
SEED_RECENT_VIEWS = [
    (0, 1),
    (0, 3),
    (1, 5),
    (2, 8),
]


def get_or_create_user(db, user_repo: UserRepository, spec: dict) -> User:
    existing = user_repo.get_by_email(spec["email"])
    if existing:
        print(f"  [skip] 이미 존재하는 유저: {spec['email']}")
        return existing

    user = User(
        email=spec["email"],
        password_hash=hash_password(spec["password"]),
        nickname=spec["nickname"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"  [생성] 유저: {spec['email']} (비밀번호: {spec['password']})")
    return user


def get_or_create_project(db, spec: dict, owner: User) -> Project:
    existing = db.query(Project).filter(Project.name == spec["name"]).one_or_none()
    if existing:
        print(f"  [skip] 이미 존재하는 프로젝트: {spec['name']}")
        return existing

    project = Project(owner_id=owner.id, name=spec["name"], description=spec["description"])
    db.add(project)
    db.commit()
    db.refresh(project)
    print(f"  [생성] 프로젝트: {spec['name']}")
    return project


def main():
    db = SessionLocal()
    try:
        print("1) 유저 생성")
        user_repo = UserRepository(db)
        users = [get_or_create_user(db, user_repo, spec) for spec in SEED_USERS]

        print("2) 프로젝트 생성")
        projects = [get_or_create_project(db, spec, owner=users[0]) for spec in SEED_PROJECTS]

        print("3) 트러블슈팅 문서 생성 + AI 검색용 색인")
        tag_repo = TagRepository(db)
        embedding_service = EmbeddingService(db=db)
        documents: list[TroubleDocument] = []

        for project_idx, author_idx, title, desc, err, trace, solution, retro, tag_names in SEED_DOCUMENTS:
            existing = db.query(TroubleDocument).filter(TroubleDocument.title == title).one_or_none()
            if existing:
                print(f"  [skip] 이미 존재하는 문서: {title}")
                documents.append(existing)
                continue

            tags = [tag_repo.get_or_create(name) for name in tag_names]
            document = TroubleDocument(
                project_id=projects[project_idx].id,
                author_id=users[author_idx].id,
                title=title,
                problem_description=desc,
                error_message=err,
                stack_trace=trace,
                solution=solution,
                retrospective=retro,
                tags=tags,
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            documents.append(document)

            embedding_service.index_document(document.id)
            print(f"  [생성+색인] {title}")

        print("4) 댓글 생성")
        for doc_idx, author_idx, content in SEED_COMMENTS:
            document = documents[doc_idx]
            existing = (
                db.query(Comment)
                .filter(Comment.document_id == document.id, Comment.content == content)
                .one_or_none()
            )
            if existing:
                print(f"  [skip] 이미 존재하는 댓글 (문서: {document.title})")
                continue

            db.add(Comment(document_id=document.id, author_id=users[author_idx].id, content=content))
            db.commit()
            print(f"  [생성] 댓글 (문서: {document.title})")

        print("5) 즐겨찾기 생성")
        for user_idx, doc_idx in SEED_BOOKMARKS:
            user, document = users[user_idx], documents[doc_idx]
            existing = (
                db.query(Bookmark)
                .filter(Bookmark.user_id == user.id, Bookmark.document_id == document.id)
                .one_or_none()
            )
            if existing:
                print(f"  [skip] 이미 존재하는 즐겨찾기 ({user.nickname} -> {document.title})")
                continue

            db.add(Bookmark(user_id=user.id, document_id=document.id))
            db.commit()
            print(f"  [생성] 즐겨찾기: {user.nickname} -> {document.title}")

        print("6) 최근 본 문서 생성")
        for user_idx, doc_idx in SEED_RECENT_VIEWS:
            user, document = users[user_idx], documents[doc_idx]
            existing = (
                db.query(RecentView)
                .filter(RecentView.user_id == user.id, RecentView.document_id == document.id)
                .one_or_none()
            )
            if existing:
                print(f"  [skip] 이미 존재하는 최근 본 문서 ({user.nickname} -> {document.title})")
                continue

            db.add(RecentView(user_id=user.id, document_id=document.id))
            db.commit()
            print(f"  [생성] 최근 본 문서: {user.nickname} -> {document.title}")

        print(f"\n완료! 유저 {len(users)}명, 프로젝트 {len(projects)}개, 문서 {len(documents)}개 준비됨.")
        print("로그인 계정:")
        for spec in SEED_USERS:
            print(f"  - {spec['email']} / {spec['password']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
