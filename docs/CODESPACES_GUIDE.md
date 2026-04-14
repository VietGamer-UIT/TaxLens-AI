# 🚀 TaxLens-AI — Hướng Dẫn Vận Hành Trên GitHub Codespaces

> **Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)**

---

## ⚡ TL;DR — Chạy Ngay (3 Bước)

```bash
# Bước 1: Khởi động toàn bộ stack
docker compose up --build

# Bước 2: Mở tab Ports trong VS Code Codespaces
# → Đổi Port 8000 và 3000 sang "Public"

# Bước 3: Click vào URL của Port 3000 → TaxLens-AI đã hoạt động!
```

---

## 🔍 Tại Sao Không Cần Cấu Hình URL Nữa?

### Kiến trúc Smart URL Resolution

```
Trình duyệt người dùng mở:
  https://laughing-space-abc123-3000.app.github.dev
                              ↓
  api.ts phát hiện hostname kết thúc bằng .app.github.dev
                              ↓
  Tự động thay -3000. thành -8000.
                              ↓
  API calls tới: https://laughing-space-abc123-8000.app.github.dev ✅
```

**Mỗi Codespace session có URL khác nhau** — không thể hardcode. Đây là lý do
tại sao cách tiếp cận "bake URL vào build" thất bại, và tại sao Smart Resolver
là giải pháp đúng đắn.

---

## 🛡️ Bước Quan Trọng Nhất — Chuyển Port Sang Public

### Vì Sao Phải Làm Điều Này?

GitHub Codespaces mặc định đặt tất cả forwarded ports ở chế độ **Private**.
Điều này có nghĩa:

| Port Visibility | Hành vi | Kết quả |
|---|---|---|
| `Private` | Yêu cầu GitHub Session Cookie | Trình duyệt nhận `401 Unauthorized` cho cross-origin requests |
| `Public` | Không cần xác thực | Axios/fetch gọi được từ Frontend → Backend ✅ |

**Tại sao `Private` gây lỗi?** Khi Frontend (port 3000) gọi Backend (port 8000),
đây là một **cross-origin request**. Trình duyệt không đính kèm GitHub session
cookie vào request này, nên Codespaces proxy trả về `401` — giống như bị CORS block.

### Hướng Dẫn Từng Bước

#### Cách 1: Qua Tab Ports (Khuyến Nghị)

```
1. Trong VS Code Codespaces, nhìn xuống dưới cùng
2. Click vào tab "PORTS" (cạnh TERMINAL, OUTPUT, PROBLEMS)
3. Tìm dòng Port 3000 (Frontend):
   - Right-click → "Port Visibility" → chọn "Public"
4. Tìm dòng Port 8000 (Backend):  
   - Right-click → "Port Visibility" → chọn "Public"
5. Cột "Visibility" của cả hai port phải hiện "Public" (có icon địa cầu 🌐)
```

#### Cách 2: Qua GitHub.com

```
1. Vào https://github.com/codespaces
2. Click vào Codespace đang chạy
3. Tab "Ports" ở trên cùng
4. Đổi visibility cho port 3000 và 8000 → Public
```

#### Cách 3: Qua VS Code Command Palette

```
1. Ctrl+Shift+P → "Ports: Make Port Public"
2. Nhập 8000 → Enter
3. Lặp lại với 3000
```

---

## 🔒 CORS Configuration (Đã Được Cấu Hình Sẵn)

Backend FastAPI sử dụng **regex pattern** thay vì danh sách tĩnh:

```python
_CORS_ORIGIN_REGEX = (
    r"http://localhost:\d+"                          # Phát triển local
    r"|http://127\.0\.0\.1:\d+"                     # Loopback
    r"|http://frontend:\d+"                          # Docker internal
    r"|https://[\w\-]+-\d+\.app\.github\.dev"       # ← Codespaces
    r"|https://[\w\-]+\.preview\.app\.github\.dev"  # ← Codespaces preview
)
```

Pattern `https://[\w\-]+-\d+\.app\.github\.dev` khớp **mọi** Codespace URL dù
hostname thay đổi mỗi session. Không cần update code khi restart Codespace.

---

## 🌐 Luồng Request Đầy Đủ Trên Codespaces

```
┌─────────────────────────────────────────────────────────────┐
│                   Trình Duyệt Người Dùng                    │
│                                                             │
│  Mở: https://abc123-3000.app.github.dev                    │
│                                                             │
│  api.ts resolveApiBase():                                   │
│    hostname = "abc123-3000.app.github.dev"                  │
│    ↓ endsWith('.app.github.dev') = true                     │
│    ↓ replace /-\d+\.app\.github\.dev$/ → '-8000.app...'    │
│    API_BASE = "https://abc123-8000.app.github.dev"  ✅      │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS (Public port)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Codespaces Port Proxy                   │
│         (Chỉ hoạt động đúng khi Port = Public)             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           Docker Container: taxlens_backend                 │
│           FastAPI trên 0.0.0.0:8000                         │
│                                                             │
│  CORS check:                                                │
│    Origin: "https://abc123-3000.app.github.dev"             │
│    Regex: https://[\w\-]+-\d+\.app\.github\.dev            │
│    ✅ MATCH → Access-Control-Allow-Origin header được gửi   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏭 Triển Khai Trên Môi Trường Khác

### Local Development (Windows/Mac/Linux)

```bash
cd Frontend
npm install
npm run dev
# → http://localhost:3000 (api.ts tự detect http://localhost:8000)
```

### Docker Compose (Local)

```bash
docker compose up --build
# → http://localhost:3000
# Không cần cấu hình gì thêm
```

### VPS / Production

```bash
# Tạo file .env tại gốc repo với:
NEXT_PUBLIC_API_URL=https://api.yourdomain.com

# Chỉ lúc này mới cần cấu hình URL — Priority 1 sẽ được dùng
docker compose up --build
```

---

## 🔧 Xử Lý Sự Cố Thường Gặp

| Triệu Chứng | Nguyên Nhân | Giải Pháp |
|---|---|---|
| `ERR_NETWORK` / `Failed to fetch` | Port 8000 chưa Public | Đổi Port 8000 → Public trong tab Ports |
| `401 Unauthorized` trên API call | Port Private + cross-origin | Đổi cả Port 3000 và 8000 → Public |
| CORS error trong browser console | Backend không nhận Origin | Kiểm tra `allow_origin_regex` trong main.py |
| Frontend load nhưng giá trị API_BASE sai | `NEXT_PUBLIC_API_URL` được baked vào với giá trị cũ | `docker compose build --no-cache frontend` |
| Backend không response | Container chưa bind `0.0.0.0` | Kiểm tra `--host 0.0.0.0` trong Dockerfile.backend |

### Debug API_BASE hiện tại

Mở Developer Tools (F12) → Console, nhập:
```javascript
// Kiểm tra URL backend đang được dùng
fetch('/').then(() => console.log('Check Network tab for actual API calls'))
```

Hoặc vào trang Dashboard, khi backend offline, bảng "Kết Nối Backend" sẽ hiển thị
URL đang được dùng để kết nối.

---

## 📋 Checklist Triển Khai Codespaces

- [ ] `docker compose up --build` chạy thành công
- [ ] Port 8000 đã đổi sang **Public**
- [ ] Port 3000 đã đổi sang **Public**  
- [ ] Mở URL Port 3000 → Dashboard hiện giao diện TaxLens-AI
- [ ] Indicator "Kết Nối Backend" hiện màu xanh ✅
- [ ] Thử điều tra với Incident ID: `IR-TEST-001`

---

*TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer) — Multi-Agent IR Platform*
