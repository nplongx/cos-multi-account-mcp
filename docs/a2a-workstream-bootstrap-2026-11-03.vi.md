# Bootstrap A2A cho tám Workstream — 2026-11-03

> Ngôn ngữ: [English](a2a-workstream-bootstrap-2026-11-03.md) | Tiếng Việt

## Thay đổi broker

Broker hiện expose thêm hai tool:

- `a2a_directory_list`: directory endpoint đang active cho COS broker deployment đã xác thực.
- `a2a_endpoint_set_peer_acl`: allowlist do recipient sở hữu, chứa chính xác sender endpoint ID được phép.

`a2a_endpoint_list` vẫn giới hạn `endpoints` theo owner, đồng thời hiện trả thêm deployment-wide `peer_directory` để tương thích với ChatGPT session đã mở trước đó. Entry của directory chứa endpoint ID, label do owner tự khai, trạng thái active, HMAC owner fingerprint và giá trị `sender_acl_token` trong phạm vi broker. Directory không bao giờ publish ContextForge owner ID, email, credential hoặc COS session. Label do owner tự khai; broker không tự chứng minh label đó thuộc một Workstream cụ thể.

Exact endpoint ACL giải quyết xung đột identity giữa bốn profile và hai Workstream. Recipient cấu hình endpoint mode chỉ chấp nhận sender endpoint ID được liệt kê, kể cả khi sender endpoint chưa được liệt kê có cùng ContextForge fingerprint. Endpoint allowlist rỗng tường minh sẽ từ chối toàn bộ sender và ghi đè legacy fingerprint allowlist. Endpoint legacy chưa cấu hình endpoint mode vẫn giữ hành vi fingerprint ACL cũ cho tới khi owner migrate.

Input schema hiện tại của `a2a_endpoint_set_acl` vẫn dùng được: truyền giá trị `sender_acl_token` từ `peer_directory` vào array `allowed_sender_fingerprints` hiện có để kích hoạt exact endpoint mode. Truyền owner fingerprint thật chỉ giữ hành vi identity-level legacy trước khi endpoint migrate. Array rỗng kích hoạt chế độ exact deny-all. Tool catalog mới có thể dùng trực tiếp `a2a_directory_list` và `a2a_endpoint_set_peer_acl`.

## Inventory endpoint hiện có

Production broker SQLite database chứa tám endpoint active trước khi nâng cấp broker:

| Workstream | Endpoint ID | ContextForge owner fingerprint |
|---|---|---|
| WS1 | `fe692d74-c735-417f-8252-359e17453b22` | `491c059becfa27835614189cef1e11c575a6ec06ef5fc2a73943b1cde6f500ad` |
| WS2 | `437be3a9-103a-4a76-b214-a5925207df30` | `491c059becfa27835614189cef1e11c575a6ec06ef5fc2a73943b1cde6f500ad` |
| WS3 | `ea54914b-66e9-41ed-b051-ad315bacd6fd` | `334d233225177519736248d47f55d3d7dc0d7a188fc706cddf32c79756205957` |
| WS4 | `05ac6126-0e9a-4e95-9808-95172af91f2b` | `334d233225177519736248d47f55d3d7dc0d7a188fc706cddf32c79756205957` |
| WS5 | `7860fbee-58d9-483e-a0d5-df34785fbec1` | `9cfc18e6f5568b88d5806d33dd612d8442b68c77f024f033d005be05755527fa` |
| WS6 | `be6f2ea2-e6af-4758-a2c8-d72701d60a85` | `9cfc18e6f5568b88d5806d33dd612d8442b68c77f024f033d005be05755527fa` |
| WS7 | `37d75f7c-7873-4e33-955a-ac49f308eed6` | `0a4feaec030c4cff03d3681b35a089d1ca86f6cda9de0c6435f3fa6f49833171` |
| WS8 | `3ca5589a-b386-4e3c-9e17-c1fc25979e6d` | `0a4feaec030c4cff03d3681b35a089d1ca86f6cda9de0c6435f3fa6f49833171` |

Đây là snapshot inventory, không phải tuyên bố rằng cả tám endpoint owner đã cấu hình peer ACL hoặc hoàn tất live round-trip. WS1/WS2 dùng chung một authenticated identity; WS3/WS4 dùng chung identity khác; WS5/WS6 dùng chung identity khác; WS7/WS8 dùng chung identity khác. Vì vậy endpoint-specific ACL là bắt buộc để cách ly Workstream.

## Định tuyến dependency suy ra từ `EIGHT_PART_PARALLEL_PLAN.md`

Đồ thị contract của plan:

- WS6 -> WS1, WS2, WS7
- WS1 -> WS2, WS7
- WS2 <-> WS3; WS2 -> WS7
- WS3 -> WS4, WS5
- WS4 -> WS5
- WS5 -> WS7
- WS8 phát triển gateway client/mock dựa trên public contract của WS1–WS7; điều này tự nó không phải chỉ thị cho phép mọi cặp endpoint gửi message cho nhau.

Với directed producer/consumer edge A -> B, cấu hình recipient ACL của B để cho phép endpoint A. Chỉ cấu hình edge chiều ngược khi owner cần message độc lập theo chiều đó; reply được gửi về sender gốc và cũng phải được ACL của sender endpoint cho phép. Không dùng fingerprint ACL rộng thay cho mapping này.

## Trình tự vận hành bắt buộc sau deployment

1. Refresh `cos-control-broker` Gateway và attach hai tool mới vào `COS Multi-Account` Virtual Server.
2. Trong từng profile của bốn account, gọi `a2a_endpoint_list` và đọc `peer_directory` (hoặc gọi `a2a_directory_list` trong session đã refresh); so sánh ID/label/fingerprint với inventory này.
3. Mỗi endpoint owner cấu hình `a2a_endpoint_set_acl` với giá trị `sender_acl_token` chính xác, hoặc dùng `a2a_endpoint_set_peer_acl` với sender endpoint ID chính xác theo dependency graph.
4. Đọc lại `a2a_endpoint_list` và endpoint của từng owner để xác minh `acl_mode=endpoint` cùng số lượng allowlist chính xác.
5. Thực hiện live message -> inbox read -> reply -> reply inbox read -> ACK cho từng cross-profile edge bắt buộc. Mỗi test dùng correlation ID và idempotency key duy nhất.
6. Báo cáo directory, ACL setup và live round-trip thành các kết quả nghiệm thu riêng biệt. Directory read hoặc endpoint registration thành công không bao giờ đồng nghĩa connectivity PASS.

Mailbox delivery tiếp tục pull-based. Thay đổi này không tự đánh thức ChatGPT tab khác.

## Kết quả deployment và nghiệm thu

Broker `0.4.1` đã deploy và healthy. Virtual Server `COS Multi-Account` có 37 tool association; hai directory/peer-ACL tool mới đã được attach. ChatGPT session mở từ trước tiếp tục hoạt động qua schema tương thích ngược `a2a_endpoint_list` và `a2a_endpoint_set_acl`.

Live directory chứa tám endpoint active. ACL readback cuối cho thấy cả tám đều ở endpoint mode chính xác và không còn legacy fingerprint entry:

| Workstream endpoint | Sender endpoint được phép | Legacy fingerprint entry |
|---|---:|---:|
| WS1 | 3 | 0 |
| WS2 | 4 | 0 |
| WS3 | 4 | 0 |
| WS4 | 3 | 0 |
| WS5 | 4 | 0 |
| `workstream-6-governance-authority` | 4 | 0 |
| WS7 | 5 | 0 |
| WS8 | 7 | 0 |

Đã xác minh live A2A message round-trip:

- WS1 <-> WS2, cùng authenticated profile nhưng endpoint ACL riêng. Request `1b81d218-bb0e-423c-b2e9-239ede2a4ff3`; reply `8de3f4e0-183f-4d86-b105-8f056826bfcb`; đã xác minh reply ACK.
- WS3 <-> WS2, cross-profile. Correlation `COS-A2A-WS3-WS2-RECOVERY-20261103-01`; request `12628258-dc4f-4c82-884e-9301c5070968`; reply `ed5d9457-6cac-4295-aeb0-ed93d7b310e3`; đã xác minh reply ACK.
- WS4 <-> WS5, cross-profile. Correlation `COS-A2A-WS4-WS5-ROUNDTRIP-20261103-01`; request `86a16ec6-5db8-41ce-bfa3-934868194c74`; reply `9d1b2b99-5842-45b7-bb21-8b46b6080cca`; đã xác minh reply ACK. Broker message state của reply là `acked`.

A2A broker test suite passed `30/30` trong runtime container. `py_compile`, `git diff --check` và `docker compose config -q` đều passed. Runtime báo broker version `0.4.1`, container healthy và có đủ hai tool definition mới. SQLite endpoint/message record hiện có được giữ nguyên qua deployment; DB backup trước deployment nằm tại `/home/long/backups/cos-a2a-20261103-160228/`.

Phân biệt trạng thái nghiệm thu: peer discovery, endpoint-specific ACL isolation và các round-trip đã test là VERIFIED. Tự động đánh thức ChatGPT tab idle **CHƯA ĐƯỢC TRIỂN KHAI**; agent phải poll inbox hoặc dựa vào scheduler/worker bên ngoài để đánh thức. Không đánh dấu dependency edge chưa test là live-tested chỉ vì ACL entry của nó tồn tại.
