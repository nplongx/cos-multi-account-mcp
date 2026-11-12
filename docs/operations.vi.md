# Vận hành

> Ngôn ngữ: [English](operations.md) | Tiếng Việt

## Health và discovery

```bash
curl -fsS http://127.0.0.1:4444/health
```

Đường dẫn protected-resource metadata:

```text
https://<your-hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

Xác nhận các giá trị `resource`, `authorization_servers` và `scopes_supported` khớp với cấu hình Auth0 API đang chạy.

## A2A tự khởi động khi boot

Xem [hướng dẫn A2A autostart](a2a-autostart.vi.md) để bật bridge local bằng systemd user service, Docker startup, điều kiện OAuth lần đầu, health check và nghiệm thu reboot.

## Vòng đời service

```bash
docker compose ps
docker compose logs --tail=100 contextforge
docker compose restart contextforge
docker compose up -d
```

Tránh `docker compose down -v`; external volume chứa ContextForge database.

## Kiểm tra xác thực

- MCP POST chưa xác thực phải trả HTTP 401 và OAuth metadata challenge;
- OAuth metadata hợp lệ có thể public;
- request tới Admin UI/API phải được bảo vệ bởi Cloudflare Access;
- health hoặc metadata check thành công không chứng minh token validation, identity mapping hoặc RBAC.

## Sao lưu database

Dừng gateway hoặc đưa gateway về trạng thái quiescent trước khi sao lưu SQLite ở mức filesystem. Lưu backup ngoài repository, mã hóa, giới hạn quyền truy cập và kiểm thử quy trình restore. Database có thể chứa user, team membership, server configuration và upstream credential đã mã hóa.

## Log và chẩn đoán

Kiểm tra log cục bộ:

```bash
docker compose logs --tail=200 contextforge
```

Xóa/che Authorization header, cookie, bearer token, OAuth code, password, client secret và dữ liệu định danh cá nhân trước khi chia sẻ log. Không dán raw database row hoặc Auth0 event payload vào public issue.

## Ứng phó sự cố

Nếu credential bị lộ:

1. Thu hồi hoặc xoay credential bị ảnh hưởng tại issuer.
2. Xoay các application secret liên quan nếu signing key hoặc encryption key có thể bị lộ.
3. Kiểm tra Auth0 và Cloudflare audit log.
4. Cấp lại connection cho user bị ảnh hưởng.
5. Kiểm tra Git history và thu hồi token bị lộ kể cả khi file đã bị xóa sau đó.
