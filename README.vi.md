# COS Multi-Account MCP

> Ngôn ngữ: [English](README.md) | Tiếng Việt

Dự án triển khai ContextForge MCP gateway đa người dùng, đứng trước COS Core, Desktop và Plugins với xác thực OAuth riêng cho từng user và RBAC giới hạn theo team.

> **Trạng thái: development / trial.** Đường triển khai và OAuth đã có một phần bằng chứng live, nhưng luồng đầy đủ ChatGPT-issued token -> email claim -> ContextForge RBAC chưa được nghiệm thu end-to-end. Không coi cấu hình Auth0/Google hiện tại là sẵn sàng production.

## Phạm vi client được hỗ trợ

Repository này **chỉ dành cho [Chat on Steroids](https://github.com/totec448-spec/chat-on-steroids)**. Đây là client integration duy nhất nằm trong phạm vi setup và acceptance của dự án. Việc sử dụng với MCP client, desktop application, agent hoặc hệ thống automation khác **chưa được kiểm chứng hoặc xác nhận**; không được mặc định rằng các use case đó tương thích hoặc được hỗ trợ.

## Repository này bao gồm

- ContextForge image được pin phiên bản và Docker build overlay.
- Định tuyến protected-resource metadata theo RFC 9728 cho team Virtual Server bật OAuth.
- Ánh xạ email claim JWT có thể cấu hình cho MCP access token.
- Docker Compose deployment template chỉ bind loopback.
- COS Control API broker chỉ bind loopback, quản lý conversation ownership theo từng ContextForge user.
- A2A mailbox bền vững, xác thực theo owner, có endpoint allowlist, idempotent delivery, TTL, ACK và reply.
- Runbook Auth0 / Google OAuth, Cloudflare Tunnel và RBAC.
- Environment template chỉ chứa placeholder, không chứa deployment credential.

Các Python file được điều chỉnh từ IBM ContextForge và giữ SPDX notice Apache-2.0. Xem [LICENSE](LICENSE) và [NOTICE](NOTICE).

## Kiến trúc

```text
ChatGPT connection (one per user)
        |
        | OAuth 2.0 Authorization Code + PKCE
        v
Auth0 tenant (Google social login)
        |
        | RS256 access token; resource audience + verified email claim
        v
Cloudflare Named Tunnel
        |
        v
ContextForge MCP gateway (127.0.0.1:4444)
        |
        | active local user -> team membership -> RBAC
        v
Team Virtual Server
   |          |          |                    |
 COS Core  COS Desktop  COS Plugins   COS Control Broker
                                           (127.0.0.1:4445)
                                                 |
                              +------------------+------------------+
                              |                                     |
                     owner-scoped agent registry           shared A2A mailbox
                              |                           (SQLite + recipient ACL)
                              v                                     |
                    COS Local Control API                 Account A <-> Account B
                    (127.0.0.1:37121)                    via signed ContextForge identities
```

Mỗi ChatGPT account tự authorize và nhận user token riêng. Không chia sẻ bearer token, refresh token, Auth0 client secret hoặc upstream capability credential giữa các user.

## Sơ đồ repository

| Đường dẫn | Mục đích |
| --- | --- |
| `Dockerfile`, `compose.yaml` | Build local image có thể tái lập và deployment chỉ bind loopback |
| `config.py` | ContextForge configuration overlay, gồm MCP email claim có thể cấu hình |
| `streamablehttp_transport.py` | MCP OAuth challenge và access-token identity mapping |
| `routers/well_known.py` | RFC 9728 protected-resource metadata endpoint |
| `services/server_service.py` | Tra cứu protected-resource metadata có xét team/OAuth |
| `cos_control_broker.py` | Broker ký danh tính, theo từng user, cho COS Local Control API |
| `.env.example` | Template secret/configuration chỉ chứa placeholder |
| `docs/README.vi.md` | Mục lục song ngữ cho toàn bộ tài liệu |
| `docs/dashboard-walkthrough.vi.md` | Tutorial Auth0/Cloudflare bằng ảnh chụp, tiếng Việt |
| `docs/architecture.vi.md` | Ranh giới tin cậy và request flow |
| `docs/deployment.vi.md` | Docker và Cloudflare deployment |
| `docs/oauth-setup.vi.md` | Auth0, Google và ChatGPT setup |
| `docs/sso-user-provisioning.vi.md` | Provision Gmail không password, được admin phê duyệt và thêm vào COS team |
| `docs/operations.vi.md` | Health, access, backup và recovery |
| `docs/verification.vi.md` | Acceptance check và bằng chứng hiện có |
| `docs/deployment-guide.vi.md` | Operator runbook từng bước |
| `docs/getting-started.vi.md` | Hướng dẫn setup end-to-end và production gate |
| `docs/dashboard-walkthrough.vi.md` | Hướng dẫn Auth0/Cloudflare bằng ảnh chụp, tiếng Việt |
| `SECURITY.vi.md` | Quy tắc xử lý secret và báo cáo bảo mật |

Toàn bộ tài liệu có phiên bản tiếng Anh và tiếng Việt. Xem [docs index](docs/README.md).

## Quick start

1. Đọc [SECURITY.md](SECURITY.md), [docs/deployment.vi.md](docs/deployment.vi.md) và [docs/oauth-setup.vi.md](docs/oauth-setup.vi.md).
2. Copy `.env.example` thành `.env`, thay mọi placeholder và đặt permission file thành `0600`.
3. Tạo persistent volume, build và start gateway:

   ```bash
   cp .env.example .env
   chmod 600 .env
   # Chỉnh sửa .env trước khi khởi động.
   docker volume create cos-contextforge-data
   docker compose build
   docker compose up -d
   ```

4. Xác nhận `curl -fsS http://127.0.0.1:4444/health` chạy thành công.
5. Publish loopback origin qua Cloudflare Named Tunnel. Giữ Admin UI/API phía sau Cloudflare Access.
6. Cấu hình Auth0 và Google bằng đúng resource URI do live ContextForge Virtual Server metadata công bố. Không đoán hoặc dùng lại resource identifier cũ.
7. Chạy đầy đủ các kiểm tra trong [docs/verification.vi.md](docs/verification.vi.md).

Repository này không chứa `.env` live, database, tunnel credential, Auth0 secret hoặc ChatGPT token.

## Hợp đồng deployment

- Base image được pin bằng digest trong [Dockerfile](Dockerfile).
- ContextForge chỉ lắng nghe trên `127.0.0.1:4444`.
- Docker dùng host networking và persistent volume `cos-contextforge-data`.
- Public MCP endpoint là `https://<your-hostname>/servers/<server-id>/mcp`.
- RFC 9728 metadata path tương ứng là `https://<your-hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp`.
- Auth0 API identifier, ContextForge protected resource và metadata `resource` phải khớp từng byte.
- Không expose Admin UI/API trực tiếp ra Internet; dùng Cloudflare Access.
- COS Control Broker chỉ bind `127.0.0.1:4445`; Control API token được mount read-only và không bao giờ trả về MCP client.
- Broker chỉ tin ContextForge user ID/email header có chữ ký HMAC. Broker bỏ qua admin/team claim được forward và authorize agent operation bằng owner registry riêng.
- A2A endpoint/message lưu trong broker persistent SQLite volume. Endpoint ACL mặc định private và được khóa theo sender's verified ContextForge identity fingerprint.
- A2A mailbox delivery là pull-based, bền vững. Nó không tự đánh thức ChatGPT tab khác, đọc conversation của account khác hoặc ủy quyền ChatGPT credential.

## Cross-account A2A mailbox

Mỗi Workstream đăng ký endpoint riêng bằng `a2a_endpoint_register` dưới ContextForge identity đã xác thực của chính nó. Gọi `a2a_directory_list` hoặc đọc `peer_directory` từ tool `a2a_endpoint_list` hiện có để khám phá endpoint đang hoạt động trong broker deployment. Endpoint owner cấu hình `a2a_endpoint_set_peer_acl` với sender endpoint ID chính xác, hoặc dùng schema tương thích ngược `a2a_endpoint_set_acl` với giá trị `sender_acl_token` lấy từ `peer_directory`. Cách này giữ Workstream tách biệt kể cả khi hai Workstream dùng chung một ContextForge identity. Truyền owner fingerprint thật vào setter cũ chỉ duy trì hành vi ACL cấp account legacy cho endpoint chưa migrate. Dùng `a2a_endpoint_delete` để retire endpoint do caller sở hữu; cần xác nhận label chính xác, thu hồi ACL của chính endpoint đó, làm hết hạn message đang xử lý và giữ history endpoint/message dưới dạng tombstone disabled. Endpoint đã retire không còn chiếm active endpoint quota. Sender dùng `a2a_send_message`; receiver dùng `a2a_inbox_read`, sau đó `a2a_message_ack` hoặc `a2a_message_reply`. Reply giữ correlation ID gốc và ACK message gốc một cách atomic. `idempotency_key` ngăn enqueue trùng khi retry. Mailbox delivery vẫn pull-based; message được queue không đánh thức ChatGPT tab khác.

Message được lưu bền vững qua broker restart, hết hạn theo TTL yêu cầu (mặc định 24 giờ, tối đa 7 ngày), và bị giới hạn bởi endpoint/pending-inbox limit. Message đã queue không chứng minh agent nhận đã đọc hoặc hành động. `a2a_inbox_read` đánh dấu message đã nhận; ACK hoặc reply là tín hiệu hoàn tất tường minh. Implementation đầu tiên này là mailbox/router, không phải transport tự động đánh thức worker.

## Trạng thái nghiệm thu hiện tại

Bằng chứng được ghi nhận trong lần setup ban đầu:

| Kiểm tra | Trạng thái |
| --- | --- |
| ContextForge health endpoint | Đã quan sát HTTP 200 |
| RFC 9728 protected-resource metadata | Đã quan sát HTTP 200 |
| MCP POST chưa xác thực | Đã quan sát HTTP 401 |
| Auth0 Google login và authorization-code exchange | Đã quan sát với một test identity |
| Tạo ChatGPT custom MCP connector | Hoàn tất trong ChatGPT UI |
| ContextForge-issued tool inventory | Đã quan sát 22 tool qua ba upstream |
| ChatGPT UI tool inventory | Đã quan sát 19 tool trong một lần kiểm tra UI; số lượng có thể khác |
| Server-side custom email claim và team RBAC cho ChatGPT-issued token | **Chưa được chứng minh end-to-end** |
| Production IdP / Google OAuth client | **Chưa sẵn sàng**; đã dùng credential development/trial |

Không đánh dấu OAuth/RBAC acceptance hoàn tất cho tới khi ContextForge xác thực ChatGPT-issued token thật và identity user cùng quyền team được xác minh phía server. Xem [docs/verification.vi.md](docs/verification.vi.md).

## Hướng dẫn chi tiết

Setup walkthrough cũng được publish dưới dạng public GitHub Gist:

**[COS Multi-Account MCP — setup guide (English + Vietnamese)](https://gist.github.com/nplongx/4ef72aa285ee4887e5b9ac2959c182f7)**

Operator runbook chi tiết:

**[COS Multi-Account MCP — operator runbook (English + Vietnamese)](https://gist.github.com/nplongx/1f17336a782a99fb4d0d15181532a5b9)**

Dùng `docs/` trong repository làm nguồn sự thật được version-control. Gist chỉ là bản tiện tra cứu, không phải nơi lưu secret.

## Lưu ý bảo mật

- Setup thử nghiệm hiện tại dùng Auth0 development/trial tenant và Google development keys. Thay bằng Google OAuth client thuộc quyền sở hữu của bạn và IdP production-grade trước khi production.
- Rà soát mức expose toàn tenant khi Google social connection được bật cho third-party application.
- `offline_access` / refresh-token continuity không nằm trong phạm vi test ban đầu được chấp nhận.
- Auth0 Action phải từ chối email chưa xác minh và chỉ phát namespaced email claim cho đúng MCP audience.
- ContextForge phải ánh xạ email đã xác minh tới local user đang active và thực thi team membership/RBAC trên mọi request.
- Không bao giờ commit `.env`, database file, backup, bootstrap password, API key, client secret, private key, bearer token, refresh token, Cloudflare credential hoặc browser session data.
- Conversation do broker tạo chạy dưới ChatGPT account/profile đang đăng nhập trong COS runtime local. Đây không phải ChatGPT account credential độc lập và không cung cấp quota riêng cho từng account.

## License

ContextForge-derived overlay được đánh dấu Apache-2.0 trong source header. Repository có license text Apache-2.0 và attribution trong [NOTICE](NOTICE).
