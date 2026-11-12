# Kiểm chứng và nghiệm thu

> Ngôn ngữ: [English](verification.md) | Tiếng Việt

## Kiểm tra baseline an toàn

Chạy từ deployment host:

```bash
curl -i http://127.0.0.1:4444/health
curl -i http://127.0.0.1:4445/healthz
curl -i https://<your-hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

Chỉ gửi POST chưa xác thực tới MCP endpoint như một negative test. Request phải fail closed với HTTP 401 và OAuth metadata challenge. Không bao giờ đưa token thật vào command line hoặc shell history.

## Nghiệm thu OAuth/RBAC end-to-end

Hoàn thành các bước sau bằng test account:

- [ ] ChatGPT hoàn tất Authorization Code + PKCE.
- [ ] Auth0 ghi nhận Google login và authorization-code exchange thành công.
- [ ] Auth0 access token dùng issuer đã cấu hình và MCP audience chính xác.
- [ ] Token có scope bắt buộc và email claim có namespace đã xác minh.
- [ ] ContextForge chấp nhận token.
- [ ] ContextForge ánh xạ claim tới đúng local user đang active.
- [ ] Team membership và RBAC chỉ cho phép Virtual Server/tool dự kiến.
- [ ] User không thuộc team bị từ chối.
- [ ] User đã disable bị từ chối.
- [ ] Token sai audience, sai issuer, hết hạn hoặc thiếu scope bị từ chối.
- [ ] Cùng MCP endpoint hoạt động với các ChatGPT account được authorize riêng biệt và không tái sử dụng credential của user này cho user khác.

Không đánh dấu integration sẵn sàng production cho tới khi các kiểm tra này PASS.

## Kiểm tra COS Control Broker

- [ ] `cos-control-broker` khỏe mạnh và chỉ lắng nghe trên `127.0.0.1:4445`.
- [ ] Broker xác thực được với COS `/v1/health`; các action route đã bật.
- [ ] Thiếu hoặc sai `X-Forwarded-User-Claims-Signature` khiến tool listing không trả tool nào và tool invocation thất bại.
- [ ] ContextForge identity hợp lệ gọi được `agent_register` và nhận broker `agent_id` dạng opaque.
- [ ] `agent_list`, `agent_get_status`, `agent_read_messages` và `agent_send_message` hoạt động với owner.
- [ ] `get_identity` trả HMAC-SHA256 fingerprint ổn định và số agent theo owner, không trả email, user ID, OAuth claim hoặc credential.
- [ ] Các OAuth session riêng biệt ánh xạ tới cùng ContextForge user trả cùng fingerprint; ContextForge user khác nhau trả fingerprint khác nhau.
- [ ] Chỉ diễn giải fingerprint trùng nhau là cùng ContextForge identity; điều này không chứng minh cùng ChatGPT account khi nhiều account dùng chung upstream Google identity.
- [ ] User thứ hai không thể liệt kê, đọc, gửi tới hoặc kiểm tra `agent_id` của user thứ nhất.
- [ ] Header admin/team không chữ ký hoặc do caller tự cung cấp không cấp quyền.
- [ ] Host COS token file được mount read-only; không xuất hiện trong tool result hoặc broker log.
- [ ] Broker registry tồn tại qua container recreation nhờ `cos-agent-broker-data`.
- [ ] Xác nhận COS ChatGPT profile local đang active là runtime account dự kiến; chat do broker tạo sử dụng account và quota đó.

## Kiểm tra A2A mailbox

- [x] Pilot WS1/WS3 live được ghi nhận hoàn tất ngày 2026-11-03; xem [a2a-pilot-2026-11-03.vi.md](a2a-pilot-2026-11-03.vi.md).
- [x] `cos-control-broker` Gateway refresh đã import bảy A2A tool; Virtual Server `COS Multi-Account` hiện có 35 tool, giữ nguyên 28 tool trước đó.
- [x] Conversation ChatGPT mới trong cả bốn account profile gọi thành công `a2a_endpoint_list` dưới các ContextForge identity khác nhau.
- [x] WS1 và WS3 endpoint được đăng ký bởi identity tương ứng, mặc định private, và cấu hình reciprocal ACL bằng fingerprint chính xác.
- [x] Luồng message live WS1 -> WS3 -> WS1 hoàn tất với cùng correlation ID; đã xác minh receiver read, reply và cả hai ACK state trong SQLite.
- [x] Broker container restart vẫn giữ cả hai endpoint, cả hai ACL entry và hai message đã ACK; health trả HTTP 200.
- [x] Unit/security suite: 23/23 passed; `py_compile`, `git diff --check` và `docker compose config -q` passed.
- [ ] Sau khi thay đổi broker tool, refresh `cos-control-broker` Gateway catalog, attach tường minh tool mới vào `COS Multi-Account` Virtual Server và refresh Settings -> Plugins riêng trong mỗi ChatGPT account profile.
- [ ] Xác minh từng tool trong bảy `a2a_*` tool bằng conversation mới cho mỗi account dự kiến; smoke test bốn profile chỉ gọi `a2a_endpoint_list`.
- [ ] Mỗi Workstream endpoint được đăng ký từ ContextForge identity đã xác thực riêng; chỉ ghi endpoint ID và public identity fingerprint trong coordination plan.
- [ ] Endpoint mới đăng ký có sender ACL rỗng và từ chối mọi sender.
- [ ] Endpoint owner có thể thêm/xóa fingerprint sender chính xác; identity khác không thể thay đổi ACL.
- [ ] Sender chỉ enqueue từ endpoint của chính nó và chỉ tới recipient endpoint đã allowlist sender fingerprint.
- [ ] Identity thứ hai không thể đọc hoặc ACK message gửi tới endpoint của identity thứ nhất.
- [ ] Message enqueue bền vững qua broker restart và idempotent khi lặp lại cùng sender endpoint + idempotency key.
- [ ] Inbox read đánh dấu message đã nhận; ACK đánh dấu hoàn tất; reply định tuyến về sender gốc, giữ correlation ID và ACK message gốc atomically.
- [ ] Message hết hạn không được giao; endpoint và pending-inbox quota từ chối công việc vượt giới hạn.
- [ ] Xác nhận không có A2A operation nào truy cập COS session của owner khác hoặc tuyên bố tự đánh thức ChatGPT tab. Hợp đồng delivery hiện tại là pull-based polling.

## Bằng chứng ghi nhận trong lần setup đầu

Môi trường test ban đầu ghi nhận:

| Kiểm tra | Kết quả quan sát |
| --- | --- |
| Local ContextForge health | HTTP 200 |
| RFC 9728 protected-resource metadata | HTTP 200 |
| MCP request không có bearer token | HTTP 401 |
| Auth0 Google login và code exchange | Thành công với một test identity |
| ChatGPT custom MCP connector | Đã tạo |
| Tool trong một ContextForge inventory | 22 tool qua ba upstream |
| Tool hiển thị trong một lần kiểm tra ChatGPT UI | 19 |
| Email-claim và team-RBAC acceptance phía server | Chưa được chứng minh end-to-end |

Chênh lệch số tool không nhất thiết là lỗi; hãy chạy lại `tools/list` bằng user token thực tế. Số lượng là snapshot, không phải acceptance criteria.

## Các production gate còn mở

- Thay Auth0 development/trial tenant và Google development keys.
- Rà soát mức phơi bày OAuth third-party trên toàn tenant.
- Chứng minh token thật được chấp nhận, email claim được mapping và team RBAC hoạt động.
- Xác định refresh-token policy trước khi yêu cầu `offline_access`.
- Kiểm thử database backup/restore và credential rotation.
- Rà soát Cloudflare Access policy và bề mặt public.

## Trạng thái triển khai A2A local — 2026-11-03

| Kiểm tra | Kết quả |
| --- | --- |
| Broker source compile và `git diff --check` | PASS |
| Broker unit/security tests | PASS, 21/21 |
| Docker image build | PASS |
| `cos-control-broker` runtime | PASS, version `0.3.0`, healthy trên `127.0.0.1:4445` |
| Direct broker MCP `tools/list` | PASS, 13 tool gồm đủ 7 tool `a2a_*` |
| Production SQLite schema | PASS, đã tạo `a2a_endpoints`, `a2a_endpoint_acl`, `a2a_messages` |
| Existing broker agent registry | Được giữ nguyên, 2 record trước/sau deployment |
| A2A production endpoint/message | Chưa provision, 0 endpoint và 0 message |
| ContextForge Gateway / Virtual Server catalog refresh | BLOCKED, local Admin session hết hạn; broker tool list đã cập nhật nhưng Gateway cache còn stale |
| A2A round-trip live hai tài khoản | CHƯA CHỨNG MINH; cần catalog refresh và endpoint provisioning |

A2A mailbox của broker dùng pull-based delivery. Deployment này không tuyên bố tự đánh thức ChatGPT tab hoặc cho phép truy cập COS session khác owner. Sau khi administrator đăng nhập ContextForge Admin UI local, hãy refresh tool của `cos-control-broker` Gateway, refresh association của `COS Multi-Account` Virtual Server và refresh ChatGPT connector action trong từng account trước khi đăng ký Workstream endpoint.
