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

## 4. Observability stack (production) — CP8 (sau giờ lab, chưa làm)

> Phần này yêu cầu bật stack Docker (Prometheus/Grafana/Jaeger/Locust) và chụp ảnh. Sẽ điền khi làm CP8.

### 4.1 Screenshot
- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (`prometheus-alert-firing.png`)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?** (chưa điền)

### 4.3 Debug bằng trace

- `trace_id`: (chưa có)
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút) — CP8 (chưa làm)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** (chưa điền)

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **SLO phải đặt theo p95/p99, không phải average** — số liệu §2.2 cho thấy avg tăng 55% trong khi p99 tăng 3.5× khi có request chậm.
  2. **Hiệu quả chi phí tính theo "cost / câu đúng"** — v2 đắt hơn v1 nhưng rẻ hơn ~11× trên mỗi câu trả lời đúng (§3).
  3. **RAG cải thiện độ đúng nhưng đẩy latency** — v2 accuracy 91.3% (→100% sau sửa KB) nhưng p95 tăng và vượt SLO ở concurrency cao; cần scale/cache để bù.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa? (chưa điền — sẽ bổ sung sau CP8)
  
---

## AI log (bổ sung cho Bước 1)

| Lần | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra |
|-----|--------|---------|----------------------|
| 6 | Hỗ trợ Part 7 Bước 1: chạy v1/v2, load test, eval, sửa KB. | Hướng dẫn cổng 8001/8002, lệnh load test 4 mức + 3 mức slow, lệnh eval và 2 entry KNOWLEDGE_BASE cần thêm. | Tự chạy agent, 9 lệnh load/eval, tự sửa `mock_llm.py`, restart v2, tự copy JSON ra `reports/`. Mọi số trong bảng đọc trực tiếp từ file JSON, không ước lượng. |
