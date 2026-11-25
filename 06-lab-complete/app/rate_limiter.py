"""Rate limiting (tiêu chí 7) — sliding window bằng Redis sorted set."""
import math
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Tối đa RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key. Vượt → 429."""
    now = time.time()
    redis_key = f"ratelimit:{key}"
    limit = settings.rate_limit_per_minute
    try:
        # Bỏ các mốc cũ ngoài cửa sổ trượt.
        r.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        count = r.zcard(redis_key)
        if count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                retry_after = max(1, math.ceil(oldest[0][1] + WINDOW_SECONDS - now))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        r.zadd(redis_key, {f"{now}:{uuid.uuid4().hex}": now})
        r.expire(redis_key, WINDOW_SECONDS)
    except HTTPException:
        raise
    except Exception:
        # Redis chưa sẵn: fail-open để agent vẫn trả lời (health/ready vẫn đúng).
        return
