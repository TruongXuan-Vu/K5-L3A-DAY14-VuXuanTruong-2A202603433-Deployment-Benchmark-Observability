# Deployment Information

> Họ tên: Vũ Xuân Trường · MSSV: 2A202603433
>
> ⚠️ File này là bản chuẩn bị sẵn. Điền **Public URL**, **API key đã đặt** và chụp ảnh sau khi deploy xong (xem hướng dẫn ở cuối file).

## Public URL

`[ĐIỀN URL SAU KHI DEPLOY — ví dụ: https://k5-day14-production.up.railway.app]`

## Platform

Railway (chọn Render thì sửa dòng này thành Render và dùng `render.yaml`).

## Deployed service

- Nguồn: thư mục `06-lab-complete/` (agent Part 6 đã `PASS 12/12`), **không phải** app mẫu trong `03-cloud-deployment/`.
- Build: Railway đọc `railway.toml` → `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`, `healthcheckPath = "/health"`.
- Redis: tạo một Redis service trên Railway, lấy **Redis connection URL** (dạng `redis://default:...@<host>:6379`) đưa vào biến `REDIS_URL` của service agent.

## Biến môi trường đã đặt trên Railway

| Biến | Giá trị / cách đặt |
|------|--------------------|
| `PORT` | Railway tự inject. Không cần đặt tay (Dockerfile CMD đã dùng `${PORT:-8000}`). |
| `ENVIRONMENT` | `staging` (hoặc `production`) |
| `AGENT_API_KEY` | `[ĐIỀN KEY BẠN ĐẶT TRONG RAILWAY DASHBOARD]` — đặt trong biến môi trường, **không ghi vào code**. |
| `REDIS_URL` | `[DÁN REDIS CONNECTION URL TỪ RAILWAY]` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `MONTHLY_BUDGET_USD` | `10.0` |

## Test Commands (4 lệnh tự kiểm theo CP6)

> Đặt `BASE` là URL public và `AGENT_API_KEY` là key bạn đặt trên Railway, rồi chạy. Mỗi lệnh chỉ in mã HTTP — chụp ảnh không lộ key.

```bash
BASE="[DÁN URL PUBLIC VÀO ĐÂY]"
AGENT_API_KEY="[DÁN KEY VÀO ĐÂY]"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả mong đợi: `200 / 200 / 401 / 200`. **Lưu ý:** `/ready` chỉ trả 200 khi Redis trên cloud kết nối được — nếu ra 503, kiểm tra lại biến `REDIS_URL`.

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png) — `[chụp sau khi deploy]`
- [Service running](screenshots/running.png) — `[chụp sau khi deploy]`
- [Test results](screenshots/test.png) — `[chụp output 4 lệnh curl -w, đã che key]`

---

## Hướng dẫn deploy trên Railway (để bạn làm theo)

1. Vào https://railway.app → đăng nhập → **New Project → Deploy from GitHub repo** → chọn repo fork đã đổi tên.
2. Trong project, **Add service → Database → Add Redis**. Railway tạo Redis + biến `REDIS_URL` nội bộ.
3. Chọn service agent → **Settings → Build** → xác nhận dùng `railway.toml` (builder `DOCKERFILE`). Nếu Railway không tự nhận, vào **Settings → Build → Custom Dockerfile** trỏ tới `06-lab-complete/Dockerfile`, và đặt **Root Directory** = `06-lab-complete`.
4. Tab **Variables** → thêm các biến ở bảng trên. Với `REDIS_URL`, có thể dùng biến reference của Railway trỏ tới service Redis (Railway tự điền URL). `AGENT_API_KEY` đặt giá trị bất kỳ (vd `k5-<mssv>-key`).
5. Railway tự deploy. Đợi tới khi log báo `Uvicorn running` và `/health` trả 200.
6. **Settings → Networking → Generate Domain** để lấy public URL.
7. Chạy 4 lệnh curl ở trên, chụp 3 ảnh, điền URL + key vào file này và mục Part 3 của `MISSION_ANSWERS.md`.
8. Kiểm tra thêm (tùy chọn, có Docker ở máy): `python check_production_ready.py --public-url <URL>` trong `06-lab-complete/`.
