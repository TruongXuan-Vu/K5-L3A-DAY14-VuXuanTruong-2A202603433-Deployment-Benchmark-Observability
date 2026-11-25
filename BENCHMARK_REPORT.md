# Benchmark & Observability Report — Day 14

> Mọi con số ở Part 7 Bước 1 lấy từ file JSON thật trong `reports/` (đã copy từ `06-lab-complete/benchmark-observability/develop/reports/`). Các mục §4–§6 thuộc Bước 2 (stack production / CP8) — sẽ điền sau giờ lab.

**Họ tên:** Vũ Xuân Trường
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11, Python 3.12, CPU x64 (máy local). Load test chạy bằng `load_test.py` (httpx) với agent v1 cổng 8001 / v2 cổng 8002.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM ~150 ms; 500 ms là ngưỡng mặc định `load_test.py` (`--slo-p95-ms 500`), đủ chặt để bắt request chậm bất thường mà không quá khắt với tail latency. |
| Error rate `/ask` | < 2% | Mặc định `--slo-error-rate 0.02`; cho phép một vài lỗi 503 do mock (tỷ lệ `MOCK_SLOW_RATE`) nhưng vẫn bắt được suy thoái lớn. |
| Accuracy trên golden dataset | ≥ 80% (mục tiêu cuối 100%) | Ngưỡng quality gate mặc định `--min-accuracy 0.8`; Exercise 7.3 nâng lên 1.0 sau khi sửa KB. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Nguồn: `reports/load_v2_c{1,10,50,100}.json` (300 request mỗi mức, `MOCK_SLOW_RATE` mặc định 0.03).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.43 | 202.6 | 234.0 | 1699.3 | 0.67% | ✅ PASS |
| 10 | 31.64 | 199.9 | 1647.1 | 1713.5 | 0.00% | ❌ FAIL (p95) |
| 50 | 82.33 | 233.7 | 772.1 | 2049.6 | 0.33% | ❌ FAIL (p95) |
| 100 | 39.07 | 954.0 | 5208.1 | 5604.1 | 0.00% | ❌ FAIL (p95) |

**Nhận xét:** RPS **không tăng tuyến tính**: 1 → 10 concurrency tăng ~7× (4.43 → 31.64), 10 → 50 tăng ~2.6× (31.64 → 82.33), nhưng 50 → 100 lại **giảm** xuống 39.07. Lý do: uvicorn single-worker + mock LLM có `time.sleep` chặn event loop; khi concurrency vượt ngưỡng, request xếp hàng, p95/p99 tăng vọt (p95 234 ms → 5208 ms), client timeout và throughput sụp. Đây là điểm nghẽn CPU/event loop, không phải lỗi mạng — chứng minh của việc tăng replica (xem §5) và cần SLO theo p95/p99 thay vì trung bình.

### 2.2 Tail latency

Nguồn: `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json` (300 request, concurrency 20).

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 205.8 | 439.5 | 479.1 |
| 0.03 (mặc định) | 256.7 | 461.7 | 1680.2 |
| 0.1 | 319.8 | 1680.0 | 1708.3 |

**Nhận xét:** Chỉ số nhạy nhất là **p99** — tăng từ ~479 ms lên ~1680 ms (3.5×) khi tỉ lệ request chậm tăng từ 0 lên 0.1, trong khi **avg chỉ tăng ~55%** (205.8 → 319.8). p95 cũng nhảy mạnh ở mức 0.1 (1680 ms). SLO không nên đặt theo average vì average bị "kéo" bởi đa số request nhanh, che giấu thiểu số request cực chậm — chính những request này làm trải nghiệm người dùng tệ nhất. Dùng p95/p99 mới phản ánh đúng tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn: `reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json` (23 câu golden dataset).

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57.2 | 109.0 | 113.7 |
| Tổng cost (USD) | 0.000405 | 0.000760 | 0.000790 |
| Cost / câu đúng (USD) | 0.00040515 | 0.00003619 | 0.00003436 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm entry `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py`, mô tả HPA scale theo CPU/memory/custom metrics. |
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm entry `["jwt"]` mô tả JWT là token có chữ ký số, chứa thông tin user + thời điểm hết hạn; server verify chữ ký không cần tra DB. |

Sau khi sửa phải **tắt rồi bật lại v2** (app không reload code) rồi mới chạy eval cuối; kết quả 100% với 0 regression.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
v1 rẻ hơn và ít token hơn (57.2 so với 109.0) nhưng accuracy chỉ 4.35% → **cost/câu đúng rất cao** (0.000405 USD, gấp ~11× v2). v2 tốn gần gấp đôi token/câu do bước retrieval đưa context vào prompt, nhưng accuracy 91.3% → cost/câu đúng chỉ 0.00003619 USD. Sau khi sửa KB, v2 đạt 100% và cost/câu đúng giảm còn 0.00003436 USD — **thấp hơn cả v1 dù tổng cost cao hơn**. Bài học: so sánh hiệu quả chi phí phải dùng **cost / câu đúng**, không phải cost / câu; v2 "đắt hơn" nhưng "đáng hơn" rất nhiều. Đổi lại là p95 latency tăng (v1 1532 ms → v2 1722 ms) do RAG, và p95 load test vượt SLO ở concurrency cao (§2.1) — cần cân nhắc cache/retrieval tối ưu nếu đưa lên production.

---

## 4. Observability stack (production) — CP8

> Bật stack bằng `docker compose -p k5-day14-observability up -d --build`. Dùng image ổn định `prom/prometheus:v2.54.1`, `grafana/grafana:11.5.0`, `jaegertracing/all-in-one:1.62.0` (các bản v3.16/13.2/2.23 bị segfault exit 139 trên môi trường WSL2 này). Locust chạy headless từ host (container locust 2.47 lỗi `zope.interface` trên Python 3.14).

### 4.1 Screenshot ✅ (7 ảnh trong `screenshots/`)
- [x] `grafana-dashboard.png` — Dashboard Grafana đang có tải: Traffic 12.5 req/s, Error rate 1.53%, Latency p95 298ms, Instances 2, LLM cost 1h $0.0254.
- [x] `jaeger-slow-trace.png` — trace chậm nhất 1.71s, 4 spans.
- [x] `jaeger-error-trace.png` — trace lỗi, span có tag `error=true`, `http.status_code=503`.
- [x] `prometheus-alert-firing.png` — trang `/alerts` thấy **Firing (2)**: `AgentHighErrorRate` và `AgentHighLatencyP95`.
- (Part 3) `dashboard.png`, `running.png`, `test.png`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.3` | `AgentHighErrorRate` | ~1.5 phút (expr >5% trong 1m + `for: 1m`) | Error rate đỏ; trace lỗi trong Jaeger (`llm_error`, 503) |
| B | `MOCK_SLOW_RATE=0.5` | `AgentHighLatencyP95` | ~2.5 phút (p95>1s + `for: 2m`) | Latency p95/p99 tăng vọt, avg tăng ít hơn |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (khi load đủ lớn) | ~2 phút (`for: 2m`) | Panel LLM cost USD/giờ tăng ~16× |
| D | `docker pause` 1 instance | `AgentInstanceDown` | ~30s (`for: 30s`) | "Instances up" giảm; Locust thấy 504 |
| E | `AGENT_VERSION=v1` | Không có | — | Retrieval hit ratio mất, tokens/s giảm, bảng version đổi |

**Thí nghiệm thực tế:** A và B chạy **đồng thời** (`MOCK_ERROR_RATE=0.3`, `MOCK_SLOW_RATE=0.5` trong `.env`, `docker compose up -d --force-recreate agent`), Locust `-u 50 -t 3m`. Sau ~150 giây cả 2 alert chuyển `firing` — xác nhận qua `curl localhost:9090/api/v1/alerts`:

```
AgentHighErrorRate -> firing
AgentHighLatencyP95 -> firing
```

C, D, E được phân tích theo định nghĩa rule trong `alert_rules.yml` (không chạy riêng từng cái).

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
Đây là **lỗi chất lượng (silent failure)** — hạ tầng vẫn xanh (200, latency thấp, cost thấp) nên metric/alert không bắt được. Phát hiện bằng: (1) **eval quality gate** trên golden dataset chạy trong CI trước mỗi deploy (như `run_eval.py --min-accuracy`), so sánh accuracy/regression với baseline; (2) **synthetic canary** gửi câu hỏi mẫu có đáp án biết trước và kiểm tra nội dung câu trả lời; (3) theo dõi `retrieval_hit_ratio` và phân bố `agent_version` trên dashboard — bản v1 làm retrieval hit ratio tụt về 0. Nói cách khác: alert hạ tầng chỉ trả lời "service có chạy không", còn "service có trả lời đúng không" cần eval/kiểm thử chất lượng.

### 4.3 Debug bằng trace

- `trace_id`: `222309308a6ae63806314f132b312bd3` (trace chậm nhất)
- Tổng thời gian: **1711.4 ms**
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small` — 1692.3 ms (98.9%)**; các span khác: `agent.run` 1708.5ms, `POST /ask` 1711.4ms, `agent.retrieve_context` chỉ 15.8ms. → Nút thắt nằm ở LLM mock, không phải code retrieval.
- Trace lỗi: `eb64de4500b4905d06d8edac2d05d800` — span `chat mock-llm-small` có tag `error=true`, `error.type=upstream_unavailable`, `otel.status_description="LLMError: Upstream LLM error: 503 Service Unavailable (mock)"`.

Dòng log JSON cùng `trace_id` (từ `docker compose -p k5-day14-observability logs agent | grep <trace_id>`):

```json
{"ts": "2026-11-25T15:58:08.105044+00:00", "level": "INFO", "service": "observable-agent", "instance": "5377b5f74310", "event": "http_request", "trace_id": "5f5a1c268b734ca3428e185643069a8b", "span_id": "c4896eeab093fa80", "request_id": "be42db4778b3", "method": "POST", "route": "/ask", "status": 200, "ms": 1746.9}
{"ts": "2026-11-25T15:58:08.322944+00:00", "level": "INFO", "service": "observable-agent", "instance": "ff1f6754539e", "event": "llm_error", "trace_id": "d6665e3ed55102f84e7a31b979216f1e", "span_id": "5533b3fff280f192", "request_id": "ad9d37cff0a5", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

> Mọi log dòng đều có `trace_id` → dán vào ô tìm kiếm Jaeger để xem toàn bộ request. Ảnh slow/error trace trong `screenshots/`.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút) — CP8

Nguồn: `benchmark-results/scale_1_stats.csv`, `scale_3_stats.csv` (Locust headless từ host, `--host http://localhost:8080 -u 100 -r 10 -t 2m`).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 63.59 | 200 | 850 | 1700 | 55 |
| 3 | 65.06 | 200 | 290 | 1700 | 58 |

**Giải thích kết quả:** Scale 1→3 cải thiện rõ **p95: 850ms → 290ms** (-66%), còn p50 giữ nguyên 200ms, RPS gần như không đổi (63.6 → 65.1) và failures tương đương (55 → 58, đều là lỗi 503 mock `MOCK_ERROR_RATE` mặc định 1%). Kết luận: scale ngang giúp giảm **tail latency** do bớt xếp hàng khi có request chậm (`MOCK_SLOW_RATE=0.03`), nhưng **không tăng throughput** — nút thắt nằm ở LLM mock latency (~120ms + 1.5s cho request chậm), không phải số replica. Muốn tăng RPS phải giảm latency của chính LLM (cache, model nhỏ hơn), không phải chỉ thêm instance. Đây là bài học quan trọng: scale chỉ giải quyết tải khi nút thắt ở CPU/queue; nếu nút thắt ở downstream latency thì scale không giúp ích nhiều.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **SLO phải đặt theo p95/p99, không phải average** — số liệu §2.2 cho thấy avg tăng 55% trong khi p99 tăng 3.5× khi có request chậm.
  2. **Hiệu quả chi phí tính theo "cost / câu đúng"** — v2 đắt hơn v1 nhưng rẻ hơn ~11× trên mỗi câu trả lời đúng (§3).
  3. **RAG cải thiện độ đúng nhưng đẩy latency** — v2 accuracy 91.3% (→100% sau sửa KB) nhưng p95 tăng và vượt SLO ở concurrency cao; cần scale/cache để bù.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  1. **Business metric + alert**: accuracy/regression từ eval chạy định kỳ (bắt lỗi chất lượng như thí nghiệm E — alert hạ tầng không bắt được), và `retrieval_hit_ratio` tụt dưới ngưỡng.
  2. **IP/edge-level metric** (thí nghiệm D): giám sát 504/`up==0` ở Nginx và synthetic check từ ngoài vào — vì metric của agent không thấy request bị Nginx chặn.
  3. **Cost budget alert** theo ngày/tháng (đã có `LLMCostBurnRateHigh` theo giờ) + alert khi token growth bất thường; thêm SLO error budget burn-rate (multi-window) để cảnh báo sớm trước khi vi phạm SLO.
  
---

## AI log (bổ sung cho Bước 1)

| Lần | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra |
|-----|--------|---------|----------------------|
| 6 | Hỗ trợ Part 7 Bước 1: chạy v1/v2, load test, eval, sửa KB. | Hướng dẫn cổng 8001/8002, lệnh load test 4 mức + 3 mức slow, lệnh eval và 2 entry KNOWLEDGE_BASE cần thêm. | Tự chạy agent, 9 lệnh load/eval, tự sửa `mock_llm.py`, restart v2, tự copy JSON ra `reports/`. Mọi số trong bảng đọc trực tiếp từ file JSON, không ước lượng. |
| 7 | Hỗ trợ Part 3 deploy Railway + CP8 observability. | Giải thích debug deploy (Root Directory, builder Dockerfile, push code trước khi deploy, healthcheck), hướng dẫn lệnh CLI và chụp ảnh. | Tự cài Railway CLI + login, phát hiện nguyên nhân build nhầm bản cũ do chưa push, tự commit+push+`railway up` → 200/200/401/200. Tự chạy stack, đổi image monitoring bản ổn định khi bị segfault, tự chạy Locust scale 1/3, tự tạo fault injection để 2 alert firing, tự chụp 4 ảnh Part 7. Số liệu đọc từ CSV/API thật. |
