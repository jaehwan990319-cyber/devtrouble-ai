# EKS 배포 가이드

`.github/workflows/`의 세 워크플로(`eks-create-cluster.yml`, `eks-deploy.yml`,
`eks-teardown.yml`)와 `deploy/helm/devtrouble-ai/` Helm chart로 구성되어 있습니다.
전부 `workflow_dispatch`(수동 실행)라 push해도 저절로 실행되지 않습니다 — Actions 탭에서
직접 "Run workflow" 버튼을 눌러야 합니다.

## ⚠️ 이 폴더를 받으셨다면 반드시 통째로 교체하세요

`deploy/helm/devtrouble-ai/` 전체와 `.github/workflows/eks-*.yml` 세 개를 **기존 파일을
지우고 이걸로 다시 덮어써 주세요.** 이전에 드렸던 버전은 두 가지 서로 다른 방식으로 만들어진
파일이 같은 폴더에 섞여 들어가 있어서(헬퍼 함수 이름과 `values.yaml` 구조가 파일마다 달랐음),
`helm install`을 돌리는 순간 바로 에러가 나는 상태였습니다. 지금 버전은 전체를 하나의
일관된 구조로 다시 맞추고, 아래 세 가지를 실제로 교차 검증했습니다:

1. 모든 템플릿이 `include`하는 헬퍼 함수 이름이 `_helpers.tpl`에 실제로 정의되어 있는지
2. 모든 템플릿이 참조하는 `.Values.*` 경로가 `values.yaml`에 실제로 존재하는지
3. 같은 이름+같은 kind의 리소스가 중복 정의되어 있지 않은지 (예: `-api` Service가
   `api-deployment.yaml`과 `api-service.yaml` 양쪽에 다 있었던 문제)

## 1. GitHub Secrets 등록 (필수 5개 + 선택 5개)

저장소 Settings → Secrets and variables → Actions → New repository secret:

| Secret 이름 | 필수 여부 | 값 |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | 필수 | IAM 사용자 Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | 필수 | IAM 사용자 Secret Access Key |
| `JWT_SECRET_KEY` | 필수 | 아무 랜덤 문자열 |
| `DATABASE_URL` | 필수 | RDS 접속 문자열 (예: `mysql+pymysql://user:pw@호스트:3306/devtrouble`) |
| `REDIS_URL` | 필수 | ElastiCache 접속 문자열, db 0 (예: `redis://호스트:6379/0`) |
| `CELERY_BROKER_URL` | 필수 | 위와 같은 호스트, db 1 (예: `redis://호스트:6379/1`) |
| `CELERY_RESULT_BACKEND` | 필수 | 위와 같은 호스트, db 2 (예: `redis://호스트:6379/2`) |
| `OPENAI_API_KEY` | 선택 | `AI_PROVIDER=openai`로 바꿀 때만 |
| `WATSONX_API_KEY` / `WATSONX_PROJECT_ID` | 선택 | `AI_PROVIDER=watsonx`로 바꿀 때만 |
| `COHERE_API_KEY` | 선택 | `RERANK_PROVIDER=cohere`로 바꿀 때만 |
| `LANGSMITH_API_KEY` | 선택 | `LANGSMITH_TRACING=true`로 바꿀 때만 |

선택 항목은 등록 안 해도 워크플로가 실패하지 않습니다 (빈 값으로 채워지고, 기본값인
`AI_PROVIDER=local`이 그 빈 값들을 안 씁니다).

## 2. 실행 순서

1. **RDS(MySQL), ElastiCache(Redis)를 먼저 AWS 콘솔에서 만들기** — 이 워크플로들은
   EKS/애플리케이션만 다루고, DB는 의도적으로 자동화하지 않았습니다.
2. **`EKS - Create Cluster`** 실행. 15~20분 정도 걸립니다.
3. **`EKS - Deploy`** 실행. 이미지 빌드 → ECR push → `helm upgrade --install`까지 한 번에
   합니다 (DB 비밀번호 등은 Helm chart 자체의 `templates/secret.yaml`이 관리합니다 —
   별도로 `kubectl create secret`을 먼저 실행하지 않습니다).
4. 완료되면 Summary에 안내된 명령으로 ALB 주소 확인:
   ```
   kubectl get ingress devtrouble-ai
   ```
5. **다 확인했으면 `EKS - Teardown` 실행.** `confirm` 입력란에 정확히 `delete`를 입력해야
   실제로 삭제가 진행됩니다.

## 3. Teardown이 하는 일 (그리고 못 하는 일)

Helm release(ALB 포함) → Ingress/PVC → EKS 클러스터(VPC/NAT Gateway/노드까지) 순서로
지웁니다. `eksctl delete cluster`로도 100% 안 지워지는 경우가 실제로 있어서, 워크플로
마지막에 로드밸런서/NAT 게이트웨이/Elastic IP/EBS 볼륨이 남아있는지 목록으로 보여주는
단계를 넣었습니다 (자동으로 지우진 않습니다). **Summary 탭에서 이 목록이 비어있는지 꼭
확인하시고, AWS 콘솔에서도 한 번 더 확인하세요.**

## 4. 정직하게 밝히는 검증 범위

**이 Helm chart와 워크플로는 실제 AWS 계정/EKS 클러스터로 끝까지 배포해본 적이
없습니다.** (AWS 자격증명도, 클러스터 접근도 없는 환경에서 만들었습니다.) 대신
이렇게 확인했습니다:

- 모든 템플릿 파일 — Go 템플릿 지시문을 제거한 뒤 순수 YAML 구조가 유효한지 검증
- 위 "1번" 섹션에서 설명한 헬퍼/값 경로/리소스 이름 교차 검증
- GitHub Actions 워크플로 3개 — YAML 문법 자체는 파싱 검증 완료

다음은 실제 클러스터에서 처음 돌려볼 때 직접 확인이 필요합니다:
- AWS Load Balancer Controller의 IAM 정책 URL이 실행 시점에 그대로 유효한지
- ALB가 실제로 프로비저닝되어 도메인으로 접속되는지
- `secrets.databaseUrl` 등에 담긴 값에 YAML이 힘들어하는 특수문자(예: 비밀번호에
  `#`, `:` 등)가 있을 때도 문제없이 전달되는지 — `eks-deploy.yml`은 이를 피하려고
  `--set` 대신 Python으로 YAML 파일을 생성해 `-f`로 넘기는 방식을 씁니다

## 5. 아직 없는 것

- RDS/ElastiCache를 Terraform 등으로 자동 생성하는 코드 (지금은 콘솔에서 수동)
- HPA는 만들어뒀지만 기본값은 꺼짐(`autoscaling.api.enabled: false`) — metrics-server
  설치 여부에 따라 켜야 할 수도 있어 우선 꺼둠
- 모니터링(CloudWatch Container Insights, Prometheus 등)
