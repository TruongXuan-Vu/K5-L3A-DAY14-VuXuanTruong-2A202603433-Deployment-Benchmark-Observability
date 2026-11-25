"""Cost guard (tiêu chí 8) — tổng chi phí vượt budget → 402."""
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _cost_keys() -> tuple[str, str]:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = day[:7]
    return f"cost:daily:{day}", f"cost:monthly:{month}"


def _total_cost() -> float:
    daily_key, monthly_key = _cost_keys()
    try:
        daily = float(r.get(daily_key) or 0)
        monthly = float(r.get(monthly_key) or 0)
        return max(daily, monthly)
    except Exception:
        return 0.0


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(402)."""
    spent = _total_cost()
    if spent >= settings.daily_budget_usd or spent >= settings.monthly_budget_usd:
        raise HTTPException(status_code=402, detail="Budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng, trả về chi phí."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    cost = round(cost, 8)
    try:
        daily_key, monthly_key = _cost_keys()
        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, 60 * 60 * 24 * 2)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, 60 * 60 * 24 * 32)
        pipe.execute()
    except Exception:
        pass
    return cost
