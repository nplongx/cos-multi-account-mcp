# Triển khai

> Ngôn ngữ: [English](deployment.md) | Tiếng Việt

## Điều kiện tiên quyết

- Linux host có Docker Engine và Docker Compose v2.
- Tài khoản Cloudflare và Named Tunnel đã cấu hình.
- Hostname thuộc domain do bạn kiểm soát.
- Docker volume persistent dành cho ContextForge database.
- Bốn file ContextForge overlay trong repository này.

## 1. Cấu hình secret

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
```

Tạo giá trị độc lập cho `JWT_SECRET_KEY` và `AUTH_ENCRYPTION_SECRET`; không dùng lại cùng một giá trị. Đặt mật khẩu bootstrap và default-user riêng biệt. Không bao giờ sao chép giá trị production vào `.env.example`.

Tạo thêm một giá trị độc lập cho `COS_IDENTITY_HMAC_SECRET` (ít nhất 32 byte ngẫu nhiên). Tạo bản sao token COS Control API có thể đọc bởi broker tại `/home/<user>/.config/chat-on-steroids/control-api/broker-token`, owner là host operator, group `10001`, mode `0640`. Giữ token gốc ở mode `0600`. Đặt `COS_CONTROL_API_TOKEN_HOST_PATH` trỏ tới đường dẫn tuyệt đối của `broker-token`. Không sao chép token vào `.env`.

Đặt:

- `APP_DOMAIN` thành external HTTPS origin, ví dụ `https://mcp.example.com`.
- `MCP_OAUTH_EMAIL_CLAIM` thành namespaced claim URI chính xác do Auth0 Action phát ra.

## 2. Build và khởi động

```bash
docker volume create cos-contextforge-data
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 contextforge
docker compose logs --tail=100 cos-control-broker
curl -fsS http://127.0.0.1:4444/health
curl -fsS http://127.0.0.1:4445/healthz
```

Compose dùng host networking và bind service vào `127.0.0.1:4444`. Không đổi thành `0.0.0.0` trừ khi bạn đã chủ động thiết kế và review một ranh giới mạng khác.

Broker chạy dưới UID/GID `10001:10001`, bind vào `127.0.0.1:4445`, mount read-only bản sao token dành riêng cho broker và xác minh ContextForge identity header có chữ ký. Bản thân Control API phải được bật bằng `controlApi.enabled=true` và `controlApi.allowActions=true` trong COS. Broker compose fail closed khi token, HMAC secret hoặc Control API health không khả dụng. Sau khi xoay COS token, tạo lại bản sao `broker-token` rồi restart `cos-control-broker`.

## 3. Cấu hình Named Tunnel

Cấu hình Cloudflare Tunnel ingress để chuyển MCP hostname tới:

```text
http://127.0.0.1:4444
```

Dùng Access application/policy riêng cho Admin UI/API. Không publish Admin UI nếu chưa có Cloudflare Access. Không đưa Tunnel credential hoặc Access service token vào repository.

Routing dự kiến:

- public: `/health`, OAuth discovery metadata và OAuth-protected MCP route;
- được Access bảo vệ: `/admin/*` và administrative API.

Review route thực tế của ContextForge và Cloudflare Access policy trước khi deploy; không giả định chỉ một ingress rule đã bảo vệ các administrative endpoint.

## 4. Tạo hoặc khôi phục team Virtual Server

Trong ContextForge:

1. Tạo team với membership least-privilege.
2. Thêm từng user dự kiến thành local ContextForge user đang active.
3. Chỉ cấp team role/RBAC cần thiết.
4. Cấu hình ba upstream MCP server và credential của chúng trong ContextForge protected admin interface.
5. Tạo Gateway tên `cos-control-broker` với URL `http://127.0.0.1:4445/mcp` và Gateway mode `direct_proxy`. Compose bật identity propagation toàn cục; không tắt signed identity claim cho Gateway này.
6. Gắn Gateway vào team Virtual Server dự kiến, rồi chỉ cấp cho team member được chọn quyền `tools.read` và `tools.execute` cần thiết.
7. Tạo một team-visible Virtual Server có bật OAuth.
8. Ghi lại server ID live và lấy protected-resource metadata theo RFC 9728.

Không export upstream capability credential vào repository hoặc cung cấp trực tiếp cho ChatGPT.

Broker cung cấp owner-scoped `agent_*` tool và `a2a_*` mailbox tool. Đăng ký agent tạo conversation cách ly dưới ChatGPT account hiện đang active trong COS; không đăng nhập hoặc mượn credential của ChatGPT account riêng thuộc từng ContextForge user. A2A endpoint là mailbox identity tách biệt, gắn với ContextForge user đã xác thực. Recipient chủ động pull message; message không tự đánh thức ChatGPT tab.

## Refresh Gateway catalog sau khi thay đổi broker tool

Deployment này giữ setting ContextForge global `auto_refresh_servers` ở trạng thái disabled. Không bật nó chỉ để refresh broker: setting áp dụng cho mọi Gateway đã cấu hình. Sau khi thêm hoặc thay đổi broker MCP tool, chỉ refresh `cos-control-broker`:

1. Mở ContextForge Admin -> Gateways -> `cos-control-broker` -> Refresh tools.
2. Mở `COS Multi-Account` Virtual Server và attach các broker tool mới được import vào tool association. Gateway refresh riêng lẻ không chứng minh Virtual Server đã expose các tool đó.
3. Trong từng ChatGPT account profile, mở Settings -> Plugins -> `COS Multi-Account` -> Refresh tools.
4. Mở conversation mới trong từng profile và xác minh tên broker tool dự kiến xuất hiện trước khi chạy cross-account A2A test.

Mười tool name của A2A mailbox là `a2a_endpoint_register`, `a2a_endpoint_delete` (owner-scoped soft retirement, xác nhận label chính xác và giữ message history), `a2a_endpoint_set_acl` (legacy fingerprint hoặc endpoint-token compatibility), `a2a_endpoint_set_peer_acl` (exact sender endpoint ACL), `a2a_endpoint_list` (endpoint của owner cùng deployment-wide `peer_directory`), `a2a_directory_list` (authenticated deployment-wide directory), `a2a_send_message`, `a2a_inbox_read`, `a2a_message_ack` và `a2a_message_reply`. Broker active-endpoint quota chỉ đếm hàng có `state='active'`; hàng đã retire với trạng thái `disabled` vẫn có trong history view của owner nhưng bị loại khỏi active routing directory. ChatGPT session hiện có vẫn dùng được `peer_directory` qua schema `a2a_endpoint_list` không đổi và cấu hình exact endpoint ACL qua schema `a2a_endpoint_set_acl` không đổi. Session mới có thể dùng directory tool và endpoint ACL tool tường minh hơn.

## 5. Cấu hình Auth0

Làm theo [oauth-setup.vi.md](oauth-setup.vi.md). Giữ Auth0 API identifier bằng chính xác giá trị `resource` do ContextForge metadata trả về. Claim URI trong Auth0 và `MCP_OAUTH_EMAIL_CLAIM` phải giống hệt nhau.

## 6. Cập nhật hoặc rollback

Sau khi thay overlay:

```bash
docker compose build
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:4444/health
```

Trước khi thay image đang chạy, hãy giữ một database backup:

```bash
docker compose stop contextforge
docker run --rm -v cos-contextforge-data:/data -v "$PWD":/backup alpine \
  tar -czf /backup/contextforge-data-backup.tgz -C /data .
docker compose up -d
```

Backup chứa dữ liệu identity và configuration. Giữ file ngoài Git và mã hóa khi lưu trữ. Chỉ restore sau khi xác nhận target volume và recovery plan.

## Cảnh báo vận hành

Ví dụ dùng external named Docker volume. Xóa volume sẽ phá hủy ContextForge state. Không bao giờ chạy `docker compose down -v` như lệnh restart thông thường.
