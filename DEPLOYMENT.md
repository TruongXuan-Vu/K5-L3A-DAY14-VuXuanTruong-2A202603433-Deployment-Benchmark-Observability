# Deployment Information

> Họ tên: Vũ Xuân Trường · MSSV: 2A202603433

## Public URL

https://k5-l3-day14-deployment-agent-benchmark-observabi-production.up.railway.app

## Platform

Railway (project `energetic-forgiveness`, environment `production`). Deploy thư mục `06-lab-complete/` (agent Part 6 đã `PASS 12/12`), **không phải** app mẫu trong `03-cloud-deployment/`.

## Cấu hình deploy

- **Root Directory:** `06-lab-complete`
- **Builder:** Dockerfile (tự động detect, build qua BuildKit)
- **Healthcheck Path:** `/health`
- **Public domain:** `k5-l3-day14-deployment-agent-benchmark-observabi-production.up.railway.app` (target port 8000)
- **Redis:** service Redis riêng trong project, biến `REDIS_URL` trỏ tới `redis.railway.internal:6379`.

## Biến môi trường đã đặt trên Railway

| Biến | Giá trị |
|------|---------|
| `PORT` | `8000` (đặt tay để khớp target port của domain & healthcheck) |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | `k5-2A202603433-key` (đặt trong Dashboard, **không ghi vào code**) |
| `REDIS_URL` | `redis://default:***@redis.railway.internal:6379` (đã che mật khẩu) |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `MONTHLY_BUDGET_USD` | `10.0` |

## Test Commands (4 lệnh tự kiểm theo CP6)

```bash
BASE="https://k5-l3-day14-deployment-agent-benchmark-observabi-production.up.railway.app"
AGENT_API_KEY="k5-2A202603433-key"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

**Kết quả thực tế:** `200 / 200 / 401 / 200` ✅

Response bodies:
```
$ curl -sS "$BASE/health"   → {"status":"ok","environment":"production"}
$ curl -sS "$BASE/ready"    → {"ready":true}
```

> **Ghi chú quá trình debug:** Lần đầu deploy fail do (1) Root Directory trống và (2) builder Railpack thay vì Dockerfile. Sau khi đặt Root Directory = `06-lab-complete`, builder = Dockerfile, thêm đủ biến môi trường + Redis service, và **commit/push code Part 6 đã sửa lên GitHub** (Railway build từ commit cũ khi code chưa được push), deploy thành công. `railway up --detach` từ `06-lab-complete/` được dùng để deploy trực tiếp bản cuối.

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
