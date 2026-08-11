#!/bin/sh
# 컨테이너 시작 시 DB 마이그레이션을 먼저 적용한 뒤 원래 CMD를 실행한다.
#
# RUN_MIGRATIONS=false로 오버라이드하면 마이그레이션을 건너뛴다
# (예: celery-worker는 api 컨테이너가 이미 마이그레이션을 적용하므로 중복 실행하지 않는다).
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] Running database migrations (alembic upgrade head)..."
  alembic upgrade head
  echo "[entrypoint] Migrations complete."
fi

exec "$@"
