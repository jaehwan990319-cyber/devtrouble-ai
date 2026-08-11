# EKS 배포 가이드

`.github/workflows/`의 세 워크플로(`eks-create-cluster.yml`, `eks-deploy.yml`,
`eks-teardown.yml`)와 `deploy/helm/devtrouble-ai/` Helm chart로 구성되어 있습니다.
전부 `workflow_dispatch`(수동 실행)라 push해도 저절로 실행되지 않습니다 — Actions 탭에서
직접 "Run workflow" 버튼을 눌러야 합니다.

## 1. GitHub Secrets 등록 (필수, 실행 전에 전부 넣어야 함)

저장소 Settings → Secrets and variables → Actions → New repository secret:

| Secret 이름 | 값 |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM 사용자 Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | IAM 사용자 Secret Access Key |
| `DATABASE_URL` | RDS 만든 뒤의 접속 문자열 (예: `mysql+pymysql://user:pw@호스트:3306/devtrouble`) |
| `REDIS_URL` | ElastiCache 접속 문자열 (예: `redis://호스트:6379/0`) |
| `CELERY_BROKER_URL` | 위와 같은 호스트, DB 번호만 다르게 (예: `redis://호스트:6379/1`) |
| `CELERY_RESULT_BACKEND` | 위와 같은 호스트, DB 번호만 다르게 (예: `redis://호스트:6379/2`) |
| `JWT_SECRET_KEY` | 아무 랜덤 문자열 |

## 2. 실행 순서

1. **RDS(MySQL), ElastiCache(Redis)를 먼저 AWS 콘솔에서 만들기** — 이 워크플로들은
   EKS/애플리케이션만 다루고, DB는 의도적으로 자동화하지 않았습니다 (README 메인
   문서에서 설명한 대로, 상태 있는 DB는 콘솔에서 신중하게 만드는 걸 권장합니다).
2. **`EKS - Create Cluster`** 실행 (Actions 탭 → 워크플로 선택 → Run workflow).
   15~20분 정도 걸립니다. 클러스터 + AWS Load Balancer Controller까지 이 단계에서 준비됩니다.
3. **`EKS - Deploy`** 실행. 이미지 빌드 → ECR push → K8s Secret 갱신 → `helm upgrade --install`까지
   한 번에 합니다.
4. 완료되면 워크플로 로그(Summary)에 안내된 명령으로 ALB 주소 확인:
   ```
   kubectl get ingress devtrouble-ai
   ```
5. **다 확인했으면 `EKS - Teardown` 실행.** `confirm` 입력란에 정확히 `delete`를
   입력해야만 실제로 삭제가 진행됩니다 (오타 방지용 안전장치).

## 3. Teardown이 하는 일 (그리고 못 하는 일)

Helm release(ALB 포함) → Ingress/PVC → EKS 클러스터(VPC/NAT Gateway/노드까지) 순서로
지웁니다. 그런데 **`eksctl delete cluster`로도 100% 안 지워지는 경우가 실제로 있다고
공식 문서에 나와 있어서**, 워크플로 마지막에 로드밸런서/NAT 게이트웨이/Elastic
IP/EBS 볼륨이 남아있는지 "찾아서 목록으로 보여주는" 단계를 넣었습니다 — 자동으로
지우진 않습니다. **워크플로 실행 후 Summary 탭에서 이 목록이 정말 비어있는지 꼭
확인하시고, 혹시 모르니 AWS 콘솔에서도 한 번 더 눈으로 확인하세요.**

## 4. 정직하게 밝히는 검증 범위

이 Helm chart와 워크플로는 **실제 AWS 계정/EKS 클러스터로 끝까지 배포해본 적이
없습니다.** (이 세션에는 AWS 자격증명도, 인터넷 전체 접근도 없어서 실제로
`eksctl create cluster`를 실행해볼 방법이 없었습니다.) 대신 이렇게 확인했습니다:

- Helm chart의 모든 템플릿 파일 — Go 템플릿 지시문(`{{ }}`)을 제거한 뒤 순수 YAML
  구조가 유효한지 자동 검증 (들여쓰기/콜론 등 문법 오류는 이걸로 잡힘)
- GitHub Actions 워크플로 3개 — YAML 문법 자체는 파싱 검증 완료
- **실제로 발견해서 고친 설계 버그 하나**: API 파드를 2개(`replicaCount: 2`)로 뒀는데,
  원래 각 파드가 시작할 때마다 자체적으로 `alembic upgrade head`를 실행하는 구조였습니다
  (docker-compose 때부터 있던 동작). 이러면 배포/재시작마다 여러 파드가 동시에 DB
  마이그레이션을 시도하는 경쟁 상태가 생길 수 있어서, `migration-job.yaml`이라는
  별도의 Helm pre-upgrade hook Job이 딱 한 번만 마이그레이션을 실행하도록 바꾸고,
  각 파드는 `RUN_MIGRATIONS=false`로 그 동작을 껐습니다.
- 이 과정에서 hook 실행 순서 문제도 하나 있었습니다 — 처음엔 마이그레이션 Job이
  ConfigMap을 참조하게 만들었는데, Helm의 pre-upgrade hook은 일반 템플릿보다 먼저
  실행되므로 그 시점엔 ConfigMap이 아직 없어서 실패할 뻔했습니다. 마이그레이션은
  사실 `DATABASE_URL`(Secret) 하나만 있으면 되므로, ConfigMap 의존성 자체를
  없애서 문제를 해결했습니다.

이 두 가지는 실제 클러스터 없이 코드를 꼼꼼히 리뷰하다가 발견한 것들이라, **아직
실물 클러스터에서 안 돌려봤으니 첫 배포 때 예상 못 한 문제가 또 나올 수 있습니다.**
특히 다음은 직접 확인이 필요합니다:
- AWS Load Balancer Controller의 IAM 정책 URL(`kubernetes-sigs/aws-load-balancer-controller`
  저장소의 `iam_policy.json`)이 실행 시점에 그대로 유효한지
- ALB가 실제로 프로비저닝되어 도메인으로 접속되는지
- 프론트엔드 컨테이너의 `nginx.conf`가 K8s 환경에서도 정적 자산을 문제없이 서빙하는지
  (nginx.conf 자체는 안 건드렸고, API 프록시 규칙만 ALB가 먼저 가로채서 사실상 안 쓰이게 됨)

## 5. 아직 없는 것

- RDS/ElastiCache를 Terraform 등으로 자동 생성하는 코드 (지금은 콘솔에서 수동)
- HPA(오토스케일링) — 지금은 `replicaCount` 고정값
- 모니터링(CloudWatch Container Insights, Prometheus 등)
