# --- Builder: cài dependencies vào /install ---
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime: chỉ copy kết quả, user non-root, uvicorn là PID 1 ---
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY utils/ ./utils/

RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/health', timeout=3).status==200 else 1)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
