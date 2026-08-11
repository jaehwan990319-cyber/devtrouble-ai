from datetime import datetime, timezone


def utc_now() -> datetime:
    """tz-aware UTC 시각을 반환한다."""
    return datetime.now(timezone.utc)


def naive_utcnow() -> datetime:
    """
    DB의 DateTime(timezone 미지정) 컬럼과 비교/저장할 때 쓰는 naive UTC 시각.
    항상 UTC 기준이라는 전제하에 tzinfo만 제거한다 (변환 아님).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
