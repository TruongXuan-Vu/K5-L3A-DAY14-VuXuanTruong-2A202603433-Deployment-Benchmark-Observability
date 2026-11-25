"""Production AI Agent — Part 6 Final Project."""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# --- Structured JSON logging (mỗi dòng là 1 JSON object hợp lệ) ---
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
        }
        message = record.msg
        if isinstance(message, dict):
            payload.update(message)
        else:
            payload["event"] = record.getMessage()
        return json.dumps(payload, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Graceful shutdown: uvicorn tự xử lý SIGTERM và chờ request hiện tại xong."""
    logger.info("startup: agent ready")
    yield
    logger.info("shutdown: finishing in-flight requests")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health():
    # Liveness: luôn 200 khi process còn chạy, kể cả Redis chết.
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    # Readiness: 503 khi Redis không kết nối được.
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    started = time.monotonic()
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    in_tokens = max(1, len(body.question.split()))
    out_tokens = max(1, len(answer.split()))
    cost = record_cost(in_tokens, out_tokens)
    ms = (time.monotonic() - started) * 1000
    logger.info({
        "event": "request",
        "path": "/ask",
        "status": 200,
        "ms": round(ms, 2),
        "cost_usd": cost,
    })
    return {"question": body.question, "answer": answer}
