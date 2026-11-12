# Kiến trúc và ranh giới tin cậy

> Ngôn ngữ: [English](architecture.md) | Tiếng Việt

## Luồng request

1. Mỗi tài khoản ChatGPT tạo kết nối OAuth riêng tới cùng một ContextForge Virtual Server.
2. ChatGPT thực hiện OAuth 2.0 Authorization Code với PKCE thông qua Auth0.
3. Auth0 xác thực người dùng bằng Google social connection đã cấu hình.
4. Auth0 phát access token đã ký cho đúng MCP resource. Token chứa MCP scope bắt buộc và email claim có namespace chỉ khi email Google đã được xác minh.
5. ContextForge xác thực token, trích xuất email claim được cấu hình, ánh xạ tới local user đang hoạt động, rồi áp dụng team membership và RBAC.
6. Team-visible Virtual Server điều phối request tới các upstream COS Core, Desktop và Plugins đã cấu hình.
7. Virtual Server cũng có thể điều phối request tới COS Control Broker chỉ lắng nghe trên loopback thông qua Gateway `direct_proxy`. ContextForge chuyển tiếp danh tính user đã xác thực cùng chữ ký HMAC.
8. Broker xác minh chữ ký đó và ánh xạ broker agent ID dạng opaque sang COS session ID trong registry SQLite riêng tư. Mọi truy vấn đều được lọc theo owner ID đã xác minh. Token dùng chung toàn instance của COS chỉ nằm bên trong broker.
9. Tin nhắn A2A liên tài khoản dùng một nhóm bảng khác trong cùng database broker persistent. Endpoint được liên kết với owner identity đã ký. Directory toàn tenant đã xác thực chỉ công bố endpoint ID đang hoạt động, nhãn do owner tự khai báo, trạng thái và owner fingerprint giả danh; không bao giờ công bố owner ID, email, credential hoặc COS session. Peer ACL do recipient sở hữu cấp quyền theo đúng sender endpoint ID, nhờ đó hai Workstream dùng chung một ContextForge identity vẫn được cách ly. Legacy fingerprint ACL chỉ tiếp tục được hỗ trợ đối với endpoint chưa bật chế độ peer ACL chính xác.

## Mô hình danh tính

Có ba danh tính tách biệt:

- **ChatGPT account:** sở hữu một connector authorization và bộ OAuth credential riêng.
- **Auth0 social identity:** xác định người dùng được Google xác thực. Social identity có thể được tạo ở lần authorization thành công đầu tiên.
- **ContextForge local user:** phải tồn tại từ trước, đang hoạt động và thuộc team sở hữu Virtual Server.

Chỉ trùng email không được phép vượt qua các kiểm tra active user, team membership, visibility hoặc RBAC.

## Hợp đồng token

Triển khai yêu cầu:

- chữ ký hợp lệ từ issuer đã cấu hình;
- resource audience chính xác được quảng bá qua protected-resource metadata;
- token chưa hết hạn;
- scope `mcp:connect` bắt buộc;
- email đã xác minh được phát ra dưới claim name đã cấu hình trong `MCP_OAUTH_EMAIL_CLAIM`.

Auth0 Post-Login Action và setting ContextForge phải dùng cùng một claim URI. Dùng URI thuộc domain do chủ triển khai kiểm soát; giá trị ví dụ trong `.env.example` không phải giá trị production.

## Protected-resource discovery

Overlay cung cấp RFC 9728 metadata cho team Virtual Server có bật OAuth tại:

```text
/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

Giá trị `resource` trả về là OAuth audience chuẩn. Sao chép nguyên giá trị đó vào Auth0 API Identifier và cấu hình ChatGPT connection. Không tự dựng lại từ trí nhớ hoặc dùng lại identifier của deployment cũ.

Metadata discovery public không làm MCP endpoint trở thành public. Request MCP chưa xác thực vẫn phải nhận OAuth challenge.

## Ranh giới mạng

- ContextForge chỉ bind vào loopback.
- Cloudflare Named Tunnel publish hostname MCP được chỉ định tới loopback origin.
- Cloudflare Access bảo vệ Admin UI/API.
- Docker database volume và toàn bộ upstream credential vẫn nằm trên host.
- Broker chỉ lắng nghe tại `127.0.0.1:4445`; COS Control API vẫn ở `127.0.0.1:37121`.
- Broker token được mount read-only từ host. Token không bao giờ được chuyển tới ContextForge user hoặc trả về từ tool.
- Broker chỉ tin cặp `X-Forwarded-User-Id` + `X-Forwarded-User-Email` có chữ ký. Header team/admin không có chữ ký sẽ bị bỏ qua.
- Broker duy trì owner registry tường minh. User không thể liệt kê, định địa chỉ hoặc gửi tin nhắn tới session chưa đăng ký dưới identity đã xác minh của họ.

## Danh tính broker và ranh giới tài khoản

`IDENTITY_PROPAGATION_ENABLED=true` và `IDENTITY_SIGN_CLAIMS=true` là bắt buộc. `IDENTITY_CLAIMS_SECRET` phải là secret độc lập, entropy cao, chỉ được chia sẻ giữa ContextForge và broker. Broker xác minh chữ ký HMAC-SHA256 trên `user_id:email` và yêu cầu mapping ContextForge hiện tại trong đó user ID bằng email đã xác minh. Không bật chuyển tiếp identity không chữ ký.

Các tool `agent_register`, `agent_list`, `agent_send_message`, `agent_read_messages` và `agent_get_status` chỉ thao tác trên bản ghi broker do caller sở hữu. Agent đăng ký mới sẽ mở chat mới thông qua COS runtime local đang hoạt động. Vì vậy, các chat này đều dùng tài khoản ChatGPT đang đăng nhập vào COS runtime đó; đây không phải cơ chế ủy quyền credential riêng cho từng tài khoản.

`get_identity` trả về pseudonym HMAC-SHA256 được tạo từ ContextForge `owner_id` đã xác minh, cùng số lượng broker registry record thuộc identity đó. Fingerprint ổn định giữa các session ánh xạ tới cùng ContextForge user và dùng chung broker identity secret. Tool cố ý không trả về email, `owner_id`, OAuth claim hoặc credential. Fingerprint bằng nhau có nghĩa là ContextForge owner identity bằng nhau trong broker identity domain này; **không** chứng minh hai ChatGPT tab thuộc cùng ChatGPT account. Hai ChatGPT account đăng nhập bằng cùng Google/ContextForge user upstream sẽ không thể phân biệt qua tool này. Số lượng bao gồm mọi registry record do owner sở hữu, kể cả record có state `closed`.

## Hợp đồng A2A mailbox

- `a2a_endpoint_register` tạo endpoint gắn với owner. Endpoint mặc định ở trạng thái private.
- `a2a_endpoint_delete` thực hiện soft retirement trong phạm vi owner. Caller phải cung cấp label hiện tại chính xác và `confirm_delete=true`. Broker thu hồi ACL của chính endpoint đó, làm hết hạn các message queued/received liên quan, đánh dấu endpoint disabled và giữ lại các hàng endpoint/message để reference message và reply cũ vẫn hợp lệ. Cấu hình ACL của owner endpoint khác không bị viết lại; sender/recipient inactive sẽ bị từ chối ở mỗi lần gửi. Endpoint đã retire không tính vào active endpoint quota và active directory. Tool này không xóa cứng dữ liệu lịch sử.
- `a2a_directory_list` trả về routing record đang hoạt động trên toàn bộ broker deployment đã xác thực. Tool `a2a_endpoint_list` hiện tại cũng trả về `peer_directory` để tương thích ngược với ChatGPT tool catalog đã cài, đồng thời giữ endpoint của caller trong `endpoints`. Directory chỉ công bố endpoint ID, label do owner tự khai báo, state, pseudonymous owner fingerprint và `sender_acl_token` trong phạm vi broker. Nó không tiết lộ owner ID, email, credential hoặc COS session. Label là nội dung do endpoint owner tự khai, không phải danh tính Workstream được bên ngoài chứng thực.
- `a2a_endpoint_set_peer_acl` chỉ được sửa endpoint do caller sở hữu và chỉ allowlist sender endpoint ID đang hoạt động, chính xác. Đây là chế độ bắt buộc để cách ly Workstream-to-Workstream, kể cả nhiều Workstream dưới cùng một ContextForge identity. Danh sách rỗng tường minh từ chối mọi sender và ghi đè mọi fingerprint allowlist cũ. Message queued/received bị thu hồi sẽ hết hạn.
- `a2a_endpoint_set_acl` vẫn tương thích ngược với schema đầu vào 64-hex cũ. Truyền giá trị `sender_acl_token` từ `peer_directory` qua trường `allowed_sender_fingerprints` hiện có sẽ cấu hình exact sender endpoint ACL mode. Truyền owner fingerprint thật chỉ duy trì hành vi identity-level cũ trước khi endpoint được migrate. Danh sách rỗng chuyển sang chế độ exact deny-all. Sau khi exact peer ACL mode đã cấu hình, legacy setter từ chối hạ cấp endpoint về quyền identity-level rộng hơn.
- `a2a_send_message` yêu cầu sender endpoint do caller sở hữu, recipient endpoint đang hoạt động, được recipient ACL cho phép, có correlation ID, idempotency key và TTL có giới hạn. Exact endpoint ACL mode kiểm tra sender endpoint ID; endpoint legacy kiểm tra sender fingerprint đã xác minh. SQLite commit message trước khi tool báo queue acceptance bền vững.
- `a2a_inbox_read` chỉ đọc endpoint do caller sở hữu. Tool đánh dấu message queued thành received và cung cấp sequence cursor đơn điệu. `a2a_message_ack` chỉ xác nhận message gửi tới endpoint đó.
- `a2a_message_reply` yêu cầu message gốc được gửi tới endpoint của caller. Tool gửi về sender endpoint ban đầu, kiểm tra ACL chiều ngược của sender endpoint, giữ nguyên correlation ID và atomically ACK message gốc.
- Message body và internal owner ID không được hiển thị ra ngoài kết quả tool của sender/recipient. Không bao giờ chấp nhận sender identity do caller tự khai; sender fingerprint lấy từ ContextForge request đã xác minh.
- Mailbox read dùng mô hình pull. Phiên bản này không tự đánh thức ChatGPT tab, proxy nội dung sang conversation của tài khoản khác hoặc làm COS Control API session có thể được owner khác định địa chỉ.
- Legacy endpoint ACL fingerprint nằm trong phạm vi HMAC secret của broker này. Xoay secret đó sẽ làm fingerprint thay đổi; phải nạp lại legacy peer ACL sau khi phối hợp xoay secret. Exact endpoint ACL dùng endpoint ID bền vững nên không bị ảnh hưởng bởi việc xoay HMAC fingerprint.

Quick Tunnel hữu ích cho kiểm thử tạm thời nhưng không cung cấp hostname ổn định và vòng đời phù hợp với deployment vận hành lâu dài.
