# Day 14 Lab — Mission Answers

> Họ tên: Vũ Xuân Trường · MSSV: 2A202603433
>
> Lớp K5 — các câu trả lời/dữ liệu dưới đây được lấy từ lệnh tự chạy trong repo fork cá nhân.

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (develop/app.py)

| # | Anti-pattern | Vị trí code | Hậu quả |
|---|--------------|-------------|---------|
| 1 | API key & DB URL hardcode trong source | `develop/app.py:17-18` (`OPENAI_API_KEY = "sk-hardcoded-..."`, `DATABASE_URL = "postgresql://admin:password123@..."`) | Push lên GitHub public là lộ secret ngay; bot quét GitHub tìm key trong vài phút. Không thể xoay key mà không đổi code + deploy lại. |
| 2 | Config cứng trong code, không đọc env | `develop/app.py:21-22` (`DEBUG = True`, `MAX_TOKENS = 500`) | Muốn đổi config phải sửa code/build lại; không theo 12-factor (Config in Env). |
| 3 | Dùng `print()` để log, và log cả secret | `develop/app.py:33-34` (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`) | Log không có cấu trúc → khó parse bởi Loki/Datadog;更重要 là **ghi lộ API key vào log**. |
| 4 | Không có health check / readiness endpoint | `develop/app.py:42` (chỉ có comments) | Platform (Railway/Render/K8s) không biết app còn sống hay đã sẵn sàng → không restart, không route traffic đúng. |
| 5 | Host/port cố định + `reload=True` | `develop/app.py:51-53` (`host="localhost"`, `port=8000`, `reload=True`) | `localhost` không bind được từ ngoài container; port cứng không nhận `PORT` do cloud inject; reload là debug mode, không dùng cho production. |
| 6 | Không xử lý SIGTERM gracefully | `develop/app.py:47-54` (chạy uvicorn thẳng, không lifespan/signal handler) | Khi platform gửi SIGTERM, request đang xử lý bị cắt ngang; không có cleanup. |

### Exercise 1.2: Chạy basic version

Lệnh (theo đúng K5 note số 3 — `question` truyền qua **query string**, không phải JSON):

```bash
cd 01-localhost-vs-production/develop
pip install -r requirements.txt
python app.py
curl -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả thật thu được:

```
$ curl -s http://localhost:8000/
{"message":"Hello! Agent is running on my machine :)"}

$ curl -s -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

$ curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" -d '{"question":"Hello"}'
422

$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health
404
```

**Quan sát:** App chạy được trên máy mình, nhưng gửi JSON thì 422 (đúng cảnh báo K5), `/health` trả 404 — tức là "chạy được" không đồng nghĩa với "sẵn sàng production".

### Exercise 1.3: Comparison table

| Feature | Basic (develop) | Advanced (production) | Tại sao quan trọng? |
|---------|-----------------|-----------------------|---------------------|
| Config | Hardcode (`DEBUG=True`, `MAX_TOKENS=500`) | Đọc từ env vars qua dataclass `Settings` (`config.py:17-35`) | Đổi config giữa dev/prod không phải sửa code hay build lại; đúng 12-factor III. |
| Secrets | `"sk-hardcoded-fake-key..."` ngay trong code | `os.getenv("OPENAI_API_KEY", "")` (`config.py:27`), production bắt buộc `AGENT_API_KEY` (`config.py:42-43`) | Tránh lộ key khi push code; xoay key không cần deploy code mới. |
| Port | Cố định `8000`, `host="localhost"` | `PORT`/`HOST` từ env, mặc định `0.0.0.0` (`config.py:17-18`) | Cloud inject `PORT`; bind `0.0.0.0` mới nhận kết nối từ ngoài container. |
| Health check | Không có (404) | `GET /health` liveness + `GET /ready` readiness (`app.py:135-161`) | Platform biết khi nào restart (liveness) và khi nào route traffic (readiness). |
| Shutdown | Đột ngột, không xử lý tín hiệu | `lifespan` đóng dần + handler SIGTERM (`app.py:39-67`, `180-189`) | Hoàn thành request hiện tại trước khi tắt, tránh lỗi cho client. |
| Logging | `print()`, có log cả secret | Structured JSON logging, **không log secret** (`app.py:27-32`, `111-122`) | Dễ parse/query bởi log aggregator; không rò rỉ dữ liệu nhạy cảm. |
| CORS | Không có | `CORSMiddleware` với `allow_origins` từ config (`app.py:77-82`) | Chặn origin trái phép gọi API từ browser. |
| Input | Query param, không validate | JSON body + trả 422 nếu thiếu `question` (`app.py:102-108`) | API rõ ràng, client biết lỗi do đâu. |

### Tự kiểm tra CP1 — 1 anti-pattern đã được sửa, kèm dòng code

**Anti-pattern:** API key hardcode.
- Develop (`01-localhost-vs-production/develop/app.py:17`):
  ```python
  OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
  ```
- Production (`01-localhost-vs-production/production/config.py:27`) đã thay bằng:
  ```python
  openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
  ```
  và validate fail-fast ở `config.py:42-43`:
  ```python
  if not self.api_key and self.environment == "production":
      raise ValueError("AGENT_API_KEY must be set in production!")
  ```

### Câu hỏi thảo luận

**1. Push code có API key hardcode lên GitHub public thì sao?**
Key bị lộ ngay: bot quét GitHub (truncate/security scanners) tìm key trong vài phút, kẻ xấu có thể dùng key đó để gọi API (tốn tiền, đốt quota), truy cập DB nếu URL+password cũng nằm trong code. GitHub có thể cảnh báo/revoke key, nhưng thiệt hại đã xảy ra. Cách xử lý: thu hồi key ngay, xoay key mới, lưu trong env/secret manager, và nhớ rằng **xoá file trong commit mới là chưa đủ** vì secret vẫn nằm trong lịch sử git — phải rotate.

**2. Tại sao stateless quan trọng khi scale?**
Nếu state (session, history) nằm trong RAM của từng instance, load balancer routing request tiếp theo tới instance khác sẽ không tìm thấy state → lỗi/không nhất quán. Muốn scale ngang (thêm replica) thì mọi instance phải có thể xử lý mọi request, tức là state phải đưa ra ngoài (Redis/DB). Khi đó thêm/bớt instance không mất dữ liệu, và có thể restart/thay instance bất kỳ lúc nào.

**3. "Dev/prod parity" nghĩa là gì trong thực tế?**
Giữ môi trường dev và production giống nhau nhất có thể: cùng phiên bản Python/dependency (dùng Docker + requirements khóa version), cùng config (chỉ khác giá trị qua env var), cùng cách chạy (một lệnh `docker compose up` ở cả hai nơi). Nhờ vậy lỗi "works on my machine" bị triệt tiêu: nếu chạy được ở local thì chạy được ở cloud, và ngược lại. 12-factor IX (dev/prod parity) khuyến khích deploy liên tục để khoảng cách này nhỏ lại.

---

## Part 2: Docker

> Build **từ gốc repo** (K5 note số 4) vì Dockerfile `COPY` theo đường dẫn tính từ root.

### Exercise 2.1: Dockerfile questions

**Base image:** `python:3.11` — full Python distribution (~1 GB), single-stage (`02-docker/develop/Dockerfile:8`).

**Working directory:** `/app` (`02-docker/develop/Dockerfile:11`).

**Tại sao `COPY requirements.txt` đứng trước `COPY . .`?**
Dependency file thay đổi ít hơn source code. Dockerfile copy `requirements.txt` rồi chạy `pip install` (`Dockerfile:14,17`) **trước khi** copy `app.py`/`utils` (`:20-24`). Khi sửa source, Docker vẫn dùng lại layer `pip install` đã cache → build nhanh hơn. (Lưu ý: `pip install --no-cache-dir` chỉ tắt cache tải của pip, **không** tắt Docker layer cache.) Demo Go trong `02-docker/layer-order/` cho thấy rõ: `deps-first` giữ `go mod download` được cache khi sửa `main.go`, còn `source-first` thì mất cache (`layer-order/README.md:78-115`).

**CMD vs ENTRYPOINT:**
- `CMD` đặt lệnh/args mặc định, bị ghi đè khi chạy `docker run <image> <cmd>`.
- `ENTRYPOINT` cố định executable, mọi arg truyền vào được nối sau nó.
Develop dùng `CMD ["python", "app.py"]` (`Dockerfile:30`); cả 2 Dockerfile đều không dùng ENTRYPOINT.

### Exercise 2.2: Chạy develop container

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d -p 8000:8000 --name k5-dev-agent my-agent:develop
```

Kết quả thật:
```
$ curl -s http://localhost:8000/health
{"status":"ok","uptime_seconds":1.8,"container":true}
$ curl -s -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 2.3: Image size comparison

```
$ docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
$ docker images --format "{{.Repository}}:{{.Tag}} {{.Size}}" | grep my-agent
my-agent:advanced 240MB
my-agent:develop 1.67GB
```

- Develop: **1.67 GB**
- Production: **240 MB**
- Chênh lệch: **(1.67 GB − 240 MB) / 1.67 GB ≈ 85.6%** — image production nhỏ hơn ~86%.

> Cả hai số đều đọc từ `docker images` như CP2 yêu cầu (không chép từ README).

**Multi-stage giảm dung lượng ở đâu?** Stage `builder` dùng `python:3.11-slim` + `gcc`/`libpq-dev` để cài dependency vào `/root/.local` (`02-docker/production/Dockerfile:16-50`); stage `runtime` là `python:3.11-slim` sạch, **chỉ copy `/root/.local`** rồi tạo user không-root (`:53-72`). Compiler, pip cache, build tool không bao giờ đóng vào image cuối. Demo Go: ~800 MB → ~15 MB (`multi-stages/README.md:43-49`).

Test advanced container chạy trực tiếp:
```
$ curl -s http://localhost:8000/health
{"status":"ok","uptime_seconds":1.0,"version":"2.0.0",...}
$ curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 2.4: Compose stack (Nginx + Redis + Qdrant + agent)

Tạo `.env.local` (repo không có sẵn — K5 note số 5), rồi bật stack:

```bash
cd 02-docker/production && touch .env.local
cd ../..
docker compose -f 02-docker/production/docker-compose.yml -p k5-day14-docker up -d --build
```

**Sơ đồ các service:**

```
                         Internet
                             │
                    ┌────────▼────────┐
                    │  nginx:alpine   │  host :80, :443
                    │  - rate limit   │
                    │  - proxy /health│
                    └────────┬────────┘
                             │ internal network
                    ┌────────▼────────┐
                    │  agent (:8000)  │  build target=runtime
                    │  uvicorn x2     │
                    └───┬─────────┬───┘
                        │         │
              ┌─────────▼──┐  ┌───▼──────────┐
              │ redis:7    │  │ qdrant:v1.9  │
              │ :6379      │  │ :6333        │
              └────────────┘  └──────────────┘
```

- `agent`: env `ENVIRONMENT=staging`, `REDIS_URL=redis://redis:6379/0`, `QDRANT_URL=http://qdrant:6333`; healthcheck `/health`; **không publish cổng ra host**.
- `redis` / `qdrant`: có volume + healthcheck; agent `depends_on` cả hai healthy.
- `nginx`: `80:80`, `443:443`; `location /` proxy tới `agent:8000` kèm rate limit 10r/s burst 20; `location /health` proxy không rate limit.

Kết quả test qua Nginx (chỉ Nginx publish cổng ra host):
```
$ curl -s http://localhost/health
{"status":"ok","uptime_seconds":5.9,"version":"2.0.0",...}
$ curl -s -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
$ curl -s http://localhost/ready
{"ready":true}
$ docker compose -f 02-docker/production/docker-compose.yml -p k5-day14-docker ps
# 4 container đều Up (agent healthy, redis healthy, qdrant healthy, nginx Up)
```

Dọn stack: `docker compose -f 02-docker/production/docker-compose.yml -p k5-day14-docker down -v`.

> **Lưu ý K5:** dùng `-p` cho mọi lệnh compose của bài này để tránh đụng project name với các folder `production/` khác (K5 note số 7).

---

## Part 3: Cloud Deployment

> Deploy chính: Railway. URL public: `[ĐIỀN URL SAU KHI DEPLOY — ví dụ https://xxx.up.railway.app]`
>
> Chi tiết cấu hình, biến môi trường và 4 lệnh curl tự kiểm: xem `DEPLOYMENT.md`. Ảnh: `screenshots/dashboard.png`, `running.png`, `test.png`.

### Exercise 3.1: Railway — 4 lệnh tự kiểm (CP6)

Sau khi deploy xong, chạy (đã che key):

```bash
BASE="[URL public]"
AGENT_API_KEY="[key đặt trên Railway]"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả thực tế (điền sau khi chạy): `___ / ___ / ___ / ___`. `/ready` trả 200 chứng tỏ Redis trên cloud đã kết nối được.

### So sánh `railway.toml` và `render.yaml` (Exercise 3.2 — nền tảng còn lại)

| Tiêu chí | `railway.toml` | `render.yaml` |
|---|---|---|
| Cú pháp | TOML, chia section `[build]` / `[deploy]` | YAML, dạng danh sách `services:` |
| Build | `builder = "DOCKERFILE"` + `dockerfilePath = "Dockerfile"` | `runtime: docker` + `dockerfilePath: ./Dockerfile` |
| Health check | `healthcheckPath = "/health"` (chuỗi, **nháy kép**) | `healthCheckPath: /health` (không nháy, **chữ hoa C** — khác Railway) |
| Port | Railway tự inject `PORT`; `startCommand` dùng `$PORT` (không có `{}`) | Render dùng `PORT` do nền tảng cấp; Dockerfile CMD đọc `${PORT:-8000}` |
| Secret | Đặt qua Dashboard → Variables (không nằm trong file) | Khai báo `envVars` nhưng `AGENT_API_KEY` dùng `generateValue: true`, `REDIS_URL` dùng `sync: false` — **không ghi giá trị thẳng** |
| Redis | Service Redis riêng trong project, biến `REDIS_URL` reference | Phải tự tạo Redis và khai báo `sync: false`, tự điền URL |

**Khác biệt cốt lõi:** Railway để secret hoàn toàn ở Dashboard (file config chỉ mô tả build/deploy), còn Render Blueprint cho phép khai báo env var ngay trong `render.yaml` nhưng bắt buộc secret phải `generateValue`/`sync: false`. Cả hai đều đọc cấu hình runtime từ `$PORT` do nền tảng inject — nhờ Dockerfile CMD dùng `${PORT:-8000}` nên chạy được ở cả hai mà không sửa code.

### Exercise 3.3: Cloud Run CI/CD pipeline (không cần deploy)

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`, pipeline đi qua 4 bước tuần tự: **(1)** `python:3.11-slim` cài requirements rồi chạy `pytest tests/` (dừng nếu test fail); **(2)** build Docker image, tag theo `$COMMIT_SHA` và `latest`, dùng `--cache-from latest` để tận dụng layer cache; **(3)** push tất cả tag lên `gcr.io/$PROJECT_ID/ai-agent`; **(4)** `gcloud run deploy` lên region `asia-southeast1` với `--min-instances=1` (tránh cold start), `--max-instances=10`, secret lấy từ Secret Manager. Trigger là push lên branch `main`. `service.yaml` là IaC định nghĩa cấu hình Service (Knative): scale 1–10, concurrency 80, CPU/memory limits, probe `/health` (liveness) và `/ready` (startup).

---

## Part 4: API Security

> K5 note số 6: bản develop chạy bằng `AGENT_API_KEY=secret-key-123`; bản production lấy token ở `POST /auth/token` với `student`/`demo123`; dùng `curl -i` để thấy mã HTTP và che token khi dán.

### Exercise 4.1: API Key authentication (develop)

```bash
cd 04-api-gateway/develop
pip install -r requirements.txt
AGENT_API_KEY=secret-key-123 python app.py
```

Key được kiểm tra trong dependency `verify_api_key()` (`develop/app.py:39-54`), inject vào `/ask` qua `Depends(...)` (`:70`). Thiếu header → **401**, sai key → **403**, đúng key → 200.

Kết quả thật (`curl -i`):

```bash
# Không có key → 401
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có key → 200
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" \
    -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"...mock..."}

# Sai key → 403 (lưu ý: KHÔNG phải 401)
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" \
    -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
```

**Xoay key (rotation) thế nào?** API key là chuỗi bí mật cố định; muốn xoay thì đổi giá trị biến `AGENT_API_KEY` trên server (env/secret manager) và update client. Vì key được đọc lúc import (`develop/app.py:35`), phải restart app để key mới có hiệu lực — đó là lý do production nên lưu key ở secret store thay vì hardcode.

### Exercise 4.2: JWT authentication (production)

```bash
cd ../production
pip install -r requirements.txt
python app.py
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"student","password":"demo123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Token là JWT HMAC-SHA256, hết hạn sau 60 phút (`auth.py:22-24,35-43`), trả về kèm `role`. Kết quả thật (token đã che):

```bash
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Not authenticated"}   # (đã che phần chi tiết)

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"...mock...","usage":{"requests_remaining":8,"budget_remaining_usd":3.5e-05}}
```

**JWT hoạt động thế nào?** Client gửi username/password → server cấp token đã ký số; mỗi request sau client gửi `Authorization: Bearer <token>`; server verify chữ ký + hạn (`auth.py:51-67`) mà **không cần lưu session** → phù hợp với API stateless. Admin dùng thuật toán/limit riêng: admin 100 req/min, user thường 10 req/min (`rate_limiter.py:7-10,86-87`).

### Exercise 4.3: Rate limiting (429)

Dùng chính `$TOKEN` ở trên, gửi 20 request liên tiếp:

```bash
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/ask \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"question\":\"Test $i\"}"
done | sort | uniq -c
```

Kết quả thật:

```
   8 200
  12 429
```

**Giải thích:** giới hạn là 10 request/phút cho user `student`; do 2 request đã dùng ở bước 4.2 nên vòng lặp còn 8 request đầu trả 200, 12 request sau trả **429**. Response 429 kèm chi tiết:

```json
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":44}}
```

Rate limiter dùng sliding-window counter trong bộ nhớ (`rate_limiter.py:45-62`) và trả header `Retry-After`. (Lưu ý: CODE_LAB gốc dùng `/token` + `admin`/`secret` — **sai cho K5**, phải dùng `/auth/token` + `student`/`demo123`.)

### Exercise 4.4: Cost guard

`cost_guard.py` bảo vệ **tiền**, còn rate limiter bảo vệ **tốc độ** — cần cả hai vì một người có thể gửi ít request nhưng mỗi request cực tốn token (rate limit không chặn được).

Cơ chế:
- Giá GPT-4o-mini: input `$0.00015`/1K token, output `$0.0006`/1K token (`cost_guard.py:20-21`).
- Mỗi user có budget **$1/ngày**; global **$10/ngày**; cảnh báo ở **80%** (`:42-44`).
- `check_budget(user)` chạy **trước** khi gọi LLM — vượt budget user → **402**, global → **503** (`:60+`).
- `record_usage(user, in, out)` chạy **sau** khi có response, cộng dồn chi phí theo ngày (`:53-58,127-128`); reset khi sang ngày mới.
- Trong mock LLM chi phí rất nhỏ (~3.5e-05 USD ở response trên), nên 402 khó đạt trong lab. Production thực tế nên lưu record trong Redis/DB thay vì in-memory (`:9`) để chia sẻ giữa các instance.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health check & readiness (develop)

```bash
cd 05-scaling-reliability/develop
pip install -r requirements.txt
python app.py
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Kết quả thật:
```
$ curl -s http://localhost:8000/health
{"status":"ok","uptime_seconds":4.1,"version":"1.0.0","environment":"development","timestamp":"...","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}

$ curl -s http://localhost:8000/ready
{"ready":true,"in_flight_requests":1}

$ curl -s -X POST "http://localhost:8000/ask?question=hello"
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

**Liveness (`/health`) khác Readiness (`/ready`) ở đâu?**
- `/health` (`:104`): "process còn sống không?" — trả 200 khi app chạy; platform (K8s/Railway) restart container nếu trả non-200. Ở develop còn kèm check memory (`degraded` nếu ≥90%).
- `/ready` (`:147-161`): "đã sẵn sàng nhận request chưa?" — trả **503** trong lúc startup (chưa load xong model/kết nối DB) hoặc lúc đang shutdown (`_is_ready=False`). Load balancer chỉ route traffic khi endpoint này trả 200. `/ask` cũng từ chối khi chưa ready (`:95`).

### Exercise 5.2: Graceful shutdown

Cơ chế trong code: handler SIGTERM (`develop/app.py:177-186`) → uvicorn gọi `lifespan` shutdown (`:42-55`) → đặt `_is_ready=False` (để `/ready` trả 503, LB ngừng gửi request mới) → middleware `track_requests` đếm `_in_flight_requests`, chờ drain tới 0 (tối đa 30s) → process thoát.

**Lưu ý môi trường:** máy này đang chạy Python Windows (`os.name = nt`), Git Bash **không gửi được SIGTERM** đúng cách (README cảnh báo K5 note số 2). Nên mình không dùng kết quả shutdown trên Windows làm bằng chứng; cơ chế được giải thích từ code và sẽ được script `check_production_ready.py` kiểm tra trong WSL2 ở Part 6.

### Exercise 5.3: Stateless design (production)

Production đưa session/history ra **Redis** (`production/app.py:59-90`, TTL 3600s, tối đa 20 messages), không giữ trong RAM từng process. Mỗi instance tiếp nhận request đều đọc/ghi cùng một store → không cần "sticky session". Nhờ đó có thể scale ngang và restart instance bất kỳ mà không mất dữ liệu.

### Exercise 5.4: Scale 3 instances qua Nginx

```bash
cd 05-scaling-reliability/production
touch .env.local        # K5 note số 5 — repo không có sẵn
cd ../..
docker compose -f 05-scaling-reliability/production/docker-compose.yml \
  -p k5-day14-scaling up -d --build --scale agent=3
```

> Dùng `-p k5-day14-scaling` cho **mọi** lệnh compose của bài này (K5 note số 7) để tránh đụng project name với các folder `production/` khác. Cổng host là **8080**, endpoint **`POST /chat`** (không phải port 80 / `/ask` như CODE_LAB gốc).

Kết quả thật — 3 agent chạy healthy, Nginx publish `0.0.0.0:8080->80`:

```
NAME                            SERVICE  STATUS           PORTS
k5-day14-scaling-agent-1        agent    Up (healthy)     8000/tcp
k5-day14-scaling-agent-2        agent    Up (healthy)     8000/tcp
k5-day14-scaling-agent-3        agent    Up (healthy)     8000/tcp
k5-day14-scaling-nginx-1        nginx    Up               0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1        redis    Up (healthy)     6379/tcp

$ curl -s -X POST http://localhost:8080/chat -H "Content-Type: application/json" -d '{"question":"Hello"}'
{"session_id":"...","question":"Hello","answer":"...","turn":2,"served_by":"instance-b7b6c7","storage":"redis"}
```

Gửi 10 request liên tiếp, `served_by` luân phiên đều 3 instance (round-robin qua Nginx DNS `server agent:8000`):
```
instance-0a554d
instance-03d1d0
instance-b7b6c7
instance-0a554d
instance-03d1d0
instance-b7b6c7
instance-0a554d
instance-03d1d0
instance-b7b6c7
instance-0a554d
```

### Exercise 5.5: test_stateless.py

```bash
cd 05-scaling-reliability/production
python test_stateless.py
docker compose -f ../../05-scaling-reliability/production/docker-compose.yml -p k5-day14-scaling down -v
```

Output thật (tóm tắt):
```
Session ID: 3c303747-6e92-4eaf-8e73-d3edc23b0a83

Request 1: [instance-03d1d0]  Q: What is Docker?
Request 2: [instance-b7b6c7]  Q: Why do we need containers?
Request 3: [instance-0a554d]  Q: What is Kubernetes?
Request 4: [instance-03d1d0]  Q: How does load balancing work?
Request 5: [instance-b7b6c7]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-03d1d0', 'instance-b7b6c7', 'instance-0a554d'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10   (5 user + 5 assistant, đúng thứ tự ban đầu)
✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:** 5 câu trong cùng một `session_id` được 3 instance khác nhau phục vụ theo round-robin, nhưng lịch sử vẫn có đủ 10 message đúng thứ tự — chứng minh state nằm ở Redis chứ không phải RAM. Nếu state nằm trong RAM, mỗi instance chỉ thấy 1–2 message và câu trả lời sẽ bị rời rạc/không liên tục.

---

## Part 6: Final Project — Production-ready Agent

Làm ngay trong `06-lab-complete/`, sửa lần lượt các `TODO` theo thứ tự gợi ý: `/health` → `config.py` → log JSON → `auth.py` → `redis_client.py` + `/ready` → `rate_limiter.py` → `cost_guard.py` → graceful shutdown → `Dockerfile` + `.dockerignore` → `docker-compose.yml` → deploy config.

### Cách làm (tóm tắt)

| File | Nội dung đã implement |
|------|----------------------|
| `app/config.py` | Dataclass `Settings` đọc `PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD` từ `os.getenv`. |
| `app/auth.py` | `APIKeyHeader(name="X-API-Key", auto_error=False)` + `verify_api_key()` tự raise **401** khi thiếu/sai (dùng 401, không 403/422). |
| `app/redis_client.py` | `redis.from_url(settings.redis_url, decode_responses=True)` — **không ping lúc import**; `redis_healthy()` ping an toàn, trả False khi lỗi. |
| `app/rate_limiter.py` | Sliding window bằng Redis sorted set (ZREMRANGEBYSCORE → ZCARD → ZADD → EXPIRE), vượt → **429** + `Retry-After`; state nằm Redis nên restart vẫn giữ. |
| `app/cost_guard.py` | `check_budget()` trước LLM → **402** khi tổng chi phí vượt daily/monthly; `record_cost()` cộng vào Redis hash theo ngày/tháng. Giá GPT-4o-mini. |
| `app/main.py` | `JsonFormatter` (mỗi dòng log = 1 JSON object), `GET /health` (luôn 200), `GET /ready` (503 khi Redis chết), `POST /ask` nối auth + rate + cost, `lifespan` cho graceful shutdown (uvicorn tự xử lý SIGTERM). |
| `Dockerfile` | Multi-stage: builder cài vào `/install`, runtime `python:3.11-slim` copy kết quả, `USER appuser`, `HEALTHCHECK`, `CMD ["sh","-c","exec uvicorn ... --port ${PORT:-8000}"]` (exec-form → uvicorn là PID 1, `docker stop` êm). Image **56 MB**. |
| `docker-compose.yml` | service `agent` (build, REDIS_URL trỏ redis, depends_on healthy) + `redis:7-alpine` có healthcheck. |
| `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml` | Loại secret/cache; liệt kê đủ env; Railway builder DOCKERFILE + healthcheckPath "/health"; Render web + healthCheckPath /health + secret `generateValue`/`sync: false`. |

**Lưu ý quan trọng đã tự sửa:** ban đầu dùng `CMD sh -c "..."` (shell-form) → `sh` là PID 1, không forward SIGTERM → `docker stop` bị SIGKILL (exit 137, 15.4s). Đổi sang exec-form `CMD ["sh","-c","exec uvicorn ..."]` → exit code **0 trong 0.6s**.

### Kết quả chấm (check_production_ready.py)

Chạy trên môi trường Linux (posix, có Docker + Redis) để graceful shutdown được kiểm tra thật — Windows/Git Bash không gửi được SIGTERM nên tiêu chí này luôn ⚠️ (README K5 note số 2). Dùng container `python:3.11-slim` với `--network host`, mount docker socket, cài `redis-server` + `docker.io` + compose v2 plugin.

```
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Các chi tiết đáng chú ý từ output: 429 sau đúng 5 request (`RATE_LIMIT_PER_MINUTE=5`) · state rate-limit vẫn giữ sau restart agent · 402 ở request thứ 1 với budget 0.000001 USD · `/ready` 503 khi Redis chết trong khi `/health` vẫn 200 · 7 dòng log JSON hợp lệ · SIGTERM lúc đang có request → request vẫn trả 200, exit code 0 · image 56 MB · `docker stop` exit 0 trong 0.6s.

---

## AI log

> Ghi theo RULES.md mục 1 — mỗi lần dùng AI cho câu trả lời/code Part 6 phải ghi lại.

| Lần | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra |
|-----|--------|---------|----------------------|
| 1 | Yêu cầu đọc README và giải thích bài lab Section 1 yêu cầu gì, có cần chụp ảnh không. | Tóm tắt các Exercise 1.1–1.3, sản phẩm CP1, và xác nhận Part 1 không cần screenshot (ảnh chỉ ở CP6/CP8). | Đối chiếu lại trực tiếp `CODE_LAB.md`, `CHECKPOINTS.md`, `SUBMISSION.md` và `RUBRIC.md` trong repo. |
| 2 | Nhờ hỗ trợ làm các phần chạy local, bắt đầu từ Part 1. | Soạn nội dung Part 1 (anti-patterns, bảng so sánh, câu hỏi thảo luận) và chạy thử develop/production để lấy output thật. | Tự chạy `python app.py` cho cả 2 bản, gọi curl `/`, `/ask`, `/health`, `/ready`, `/metrics`; đối chiếu output với code (`develop/app.py`, `production/app.py`, `config.py`). Số liệu trong bài là kết quả lệnh thật, không bịa. |
| 3 | Hỗ trợ Parts 2/4/5: build Docker, test auth/rate-limit, stateless scaling. | Gợi ý lệnh build từ gốc repo, curl `-i` cho 401/200/429, compose `-p` cho Part 5. | Tự build 2 image và đo bằng `docker images` (1.67GB vs 240MB), chạy compose stack và curl thật; tự cài `pyjwt` và lấy token `student/demo123`; tự chạy `test_stateless.py` thu output 3 instance. |
| 4 | Hỗ trợ Part 6: phân tích `check_production_ready.py` và viết TODO. | Chỉ ra chính xác 12 tiêu chí + các static/runtime check (regex, env, SIGTERM, docker stop), gợi ý implement từng file. | Tự viết toàn bộ `app/*.py`, Dockerfile, compose, deploy config. Chạy `--static-only` (28/28), `--skip-docker` (38/38), full trên Windows (41/42, chỉ graceful ⚠️ do OS). Tự phát hiện lỗi CMD shell-form → 137, đổi sang exec-form → exit 0. Cuối cùng tự chạy checker trong Linux container có Docker+Redis → **PASS 12/12, 43/43**. Không sửa script chấm. |
| 5 | Tư vấn cách chạy checker trên môi trường posix khi WSL Ubuntu cài không khởi động được. | Đề xuất dùng container `python:3.11-slim --network host` mount docker socket, cài redis-server + compose plugin. | Tự thử nhiều cấu hình; xác nhận graceful ✅ trên posix và Docker checks ✅; tự restart Docker Desktop khi daemon lỗi; đạt kết quả cuối 12/12. |
| 6 | Hỗ trợ Part 7 Bước 1 (load test + eval local). | Cổng v1=8001/v2=8002, 4 lệnh load concurrency, 3 lệnh slow-rate, eval v1/v2/fixed, 2 entry KNOWLEDGE_BASE. | Tự chạy toàn bộ, tự sửa `mock_llm.py`, restart v2, copy JSON ra `reports/`, điền `BENCHMARK_REPORT.md` (§1–§3) bằng số đọc từ JSON. Conflicts pydantic của `pip install` không ảnh hưởng chạy. |
