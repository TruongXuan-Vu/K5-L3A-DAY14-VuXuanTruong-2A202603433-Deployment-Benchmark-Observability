"""Kết nối Redis dùng chung cho rate limiter và cost guard."""
import redis

from app.config import settings

# from_url không mở kết nối ngay — app vẫn khởi động được khi Redis chưa sẵn.
r = redis.from_url(settings.redis_url, decode_responses=True)


def redis_healthy() -> bool:
    """Ping Redis; lỗi kết nối → False (dùng cho GET /ready)."""
    try:
        return bool(r.ping())
    except Exception:
        return False
