# Chính sách bảo mật

> Ngôn ngữ: [English](SECURITY.md) | Tiếng Việt

## Phạm vi

Repository này chứa ContextForge deployment overlay và tài liệu vận hành. Đây không phải repository lưu credential.

## Không bao giờ công khai

Không commit hoặc dán vào GitHub, Gist, issue hay log các nội dung sau:

- `.env`, database file, backup hoặc production configuration dump;
- JWT signing secret, encryption key, bootstrap password hoặc Basic Auth password;
- Auth0 client secret, Google OAuth client secret, Cloudflare Tunnel token hoặc Cloudflare Access service token;
- access token, refresh token, authorization code, cookie, browser profile data hoặc upstream COS capability credential;
- personal identity record hoặc user list không cần thiết cho public runbook.

Chỉ dùng `.env.example` làm template chứa placeholder. File `.env` thật chỉ được phép đọc bởi deployment operator (`chmod 600 .env`).

## Bảo vệ deployment

- Bind ContextForge vào `127.0.0.1`; không expose trực tiếp port 4444.
- Chỉ publish MCP route qua Cloudflare Tunnel được chỉ định.
- Bảo vệ Admin UI/API path bằng Cloudflare Access.
- Giữ MCP endpoint được OAuth bảo vệ. `tools/list` chưa xác thực chỉ có thể expose fixed name và JSON schema, không được lộ user/session data.
- Mọi `tools/call` phải fail closed nếu ContextForge không cung cấp signed user identity hợp lệ; áp dụng owner scoping cho mọi agent/session operation.
- Mọi A2A endpoint và mailbox operation phải gắn với signed owner identity. Routing Workstream mới phải dùng recipient-owned exact sender-endpoint allowlist, sender endpoint ownership, TTL/size/queue giới hạn và idempotency. Tenant-wide directory chỉ được expose endpoint ID, label do owner tự khai, state và pseudonymous owner fingerprint; không expose owner ID, email, credential hoặc COS session. Legacy fingerprint ACL chỉ giữ vì tương thích ngược. Không bao giờ chấp nhận sender identity do caller tự cung cấp làm thẩm quyền hoặc dùng mailbox để tra cứu COS session của owner khác.
- Xác thực token signature, issuer, exact resource audience, expiry, scope và email identity đã xác minh.
- Ánh xạ email claim tới local user đang active và áp dụng team membership/RBAC trên mọi request.
- Không chia sẻ OAuth credential giữa các ChatGPT account.

## Báo cáo sự cố

Nếu nghi ngờ có vulnerability, tránh đăng chi tiết khai thác hoặc credential trong public issue. Liên hệ riêng repository owner và cung cấp commit bị ảnh hưởng, tác động và bước tái hiện an toàn. Thu hồi và xoay mọi credential có thể đã bị lộ.
