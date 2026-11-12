# A2A tự khởi động cùng máy tính (Linux / systemd user)

> Ngôn ngữ: [English](a2a-autostart.md) | Tiếng Việt

Tài liệu này mô tả cấu hình hiện có trên máy COS và cách bật A2A bridge tự chạy sau khi máy khởi động. Không cần tạo cron job hoặc chạy terminal thủ công mỗi lần đăng nhập.

## 1. Thành phần và phạm vi

| Thành phần | Cách khởi động | Vai trò |
| --- | --- | --- |
| `cos-contextforge` | Docker Compose, `restart: unless-stopped` | MCP gateway, cổng loopback `4444` |
| `cos-control-broker` | Docker Compose, `restart: unless-stopped` | A2A broker, cổng loopback `4445` |
| `cos-mcp-tunnel.service` | systemd user service | Cloudflare Named Tunnel |
| `cos-multi-account-a2a.service` | systemd user service | Local OAuth MCP-to-A2A bridge, `127.0.0.1:8780` |

`cos-multi-account-a2a.service` là unit cần enable để local A2A bridge tự chạy. Unit hiện dùng:

- Script: `~/.config/mcp-a2a-bridge/run_bridge.py`
- Config: `~/.config/mcp-a2a-bridge/bridge.yaml`
- Environment: `~/.config/mcp-a2a-bridge/bridge.env`
- Python: `~/.local/share/pipx/venvs/mcp-a2a-bridge/bin/python`
- OAuth state: `~/.local/state/cos-multi-account-a2a/oauth.json`
- Listen address: `127.0.0.1:8780` (loopback only)

Không đưa `bridge.env`, OAuth state, token, Cloudflare token hoặc `.env` vào Git hay tài liệu chia sẻ.

## 2. Điều kiện trước khi bật tự khởi động

1. Docker Engine phải được bật cùng hệ thống nếu muốn ContextForge và broker tự chạy sau reboot:

   ```bash
   sudo systemctl enable --now docker
   systemctl is-enabled docker
   systemctl is-active docker
   ```

2. Đăng nhập OAuth lần đầu trong phiên desktop đang hoạt động. Unit chạy dưới user `long`; lần đầu chưa có OAuth state thì bridge sẽ mở browser để đăng nhập Auth0. Chạy:

   ```bash
   systemctl --user start cos-multi-account-a2a.service
   journalctl --user -u cos-multi-account-a2a.service -f
   ```

   Hoàn tất OAuth trong browser. Khi callback thành công, log phải có `OAuth MCP session initialized` và service phải ở trạng thái `active`. Kiểm tra file state tồn tại mà không in nội dung token:

   ```bash
   test -s ~/.local/state/cos-multi-account-a2a/oauth.json && echo 'OAuth state exists'
   stat -c '%a %U:%G %n' ~/.local/state/cos-multi-account-a2a/oauth.json
   ```

   File OAuth state phải chỉ user hiện tại đọc/ghi được (mode `600`). Không copy file này sang user hoặc máy khác.

3. Nếu lần đăng nhập đầu thất bại, xem journal, sửa nguyên nhân rồi thử lại. Không bật vòng restart liên tục khi OAuth chưa hoàn tất.

## 3. Bật chạy tự động sau reboot

Sau khi OAuth đã hoàn tất và service chạy ổn định:

```bash
systemctl --user enable cos-multi-account-a2a.service
systemctl --user enable cos-mcp-tunnel.service
systemctl --user enable cos-loop-watchdog.service
```

User manager hiện được cấu hình `Linger=yes`. Điều này cho phép systemd user manager và các unit `WantedBy=default.target` chạy sau boot, kể cả trước khi user đăng nhập GUI. Kiểm tra:

```bash
loginctl show-user "$USER" -p Linger
systemctl --user is-enabled cos-multi-account-a2a.service
systemctl --user is-enabled cos-mcp-tunnel.service
systemctl --user is-enabled cos-loop-watchdog.service
```

Nếu `Linger=no`, bật cho user hiện tại:

```bash
sudo loginctl enable-linger "$USER"
```

Linger không tự tạo OAuth token và không thay thế lần đăng nhập Auth0 ban đầu. Nên hoàn tất OAuth khi desktop đang hoạt động trước khi dựa vào auto-start.

## 4. Kiểm tra trạng thái và A2A endpoint

```bash
systemctl --user status cos-multi-account-a2a.service --no-pager
journalctl --user -u cos-multi-account-a2a.service -b --no-pager -n 100
curl -fsS http://127.0.0.1:8780/health

docker compose ps
curl -fsS http://127.0.0.1:4444/health
curl -fsS http://127.0.0.1:4445/healthz
```

Kỳ vọng:

- `cos-multi-account-a2a.service`: `active (running)`;
- local A2A health endpoint: HTTP 200;
- `cos-contextforge`: running/healthy;
- `cos-control-broker`: running/healthy.

Health check chỉ xác nhận process/HTTP endpoint sống. Nó không chứng minh peer ACL, inbox delivery, worker wake-up hoặc live A2A round-trip. Cần thực hiện message -> recipient inbox -> reply -> sender inbox để xác nhận liên workstream.

## 5. Điều khiển service

```bash
# Bật ngay và bật cùng boot
systemctl --user enable --now cos-multi-account-a2a.service

# Dừng tạm thời (không bỏ cấu hình auto-start)
systemctl --user stop cos-multi-account-a2a.service

# Chạy lại
systemctl --user start cos-multi-account-a2a.service

# Tắt auto-start
systemctl --user disable cos-multi-account-a2a.service

# Theo dõi log realtime
journalctl --user -u cos-multi-account-a2a.service -f
```

Không dùng `docker compose down -v` để restart gateway/broker; thao tác đó có thể xóa persistent data. Đối với container, dùng `docker compose up -d` hoặc `docker compose restart <service>` trong đúng thư mục deployment.

## 6. Giới hạn OAuth cần biết

Bridge hiện dùng OAuth Authorization Code + PKCE, lưu access token trong file user-only, không yêu cầu `offline_access` và không dùng refresh-token grant. Khi access token hết hạn, bridge cần browser sign-in Auth0 mới. Vì vậy:

- `Restart=on-failure` chỉ tự khởi động lại process khi lỗi; không tự gia hạn token;
- nếu bridge restart sau reboot và token còn hạn, nó có thể khởi tạo MCP session không cần thao tác;
- nếu token hết hạn, cần đăng nhập lại trong phiên desktop tương tác, sau đó start lại service;
- không bật `offline_access` hoặc tự lưu refresh token khi chưa có thiết kế rotation, revocation và recovery.

## 7. Gỡ auto-start

```bash
systemctl --user disable --now cos-multi-account-a2a.service
```

Lệnh trên chỉ disable/dừng local bridge; không xóa OAuth state, broker database, ContextForge database hoặc cấu hình Cloudflare.

## 8. Cấu hình hiện tại đã kiểm tra

Trên host được kiểm tra khi viết tài liệu:

- `cos-mcp-tunnel.service`: enabled;
- `cos-loop-watchdog.service`: enabled;
- `cos-multi-account-a2a.service`: tồn tại nhưng disabled và inactive;
- user lingering: enabled (`Linger=yes`);
- Docker Compose đặt `restart: unless-stopped` cho `contextforge` và `cos-control-broker`.

Do đó, thêm tài liệu này không đồng nghĩa A2A bridge đã được bật auto-start. Chỉ đánh dấu hoàn tất sau khi enable service, kiểm tra trạng thái và thực hiện reboot acceptance test.
