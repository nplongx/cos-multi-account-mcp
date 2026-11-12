# Provision Gmail user trong ContextForge (Auth0)

> Ngôn ngữ: [English](sso-user-provisioning.md) | Tiếng Việt

Runbook dành cho deployment COS Multi-Account hiện tại. Tài liệu mô tả quy trình provision local user không password, được administrator phê duyệt tường minh. Đây không phải hướng dẫn thiết lập Auth0 application.

## Không nhầm lẫn hai lớp xác thực

- **ContextForge local user** là account và authorization record. User phải tồn tại và đang active trước khi email có thể được ánh xạ sang quyền ContextForge.
- **Auth0 + Google** xác thực người dùng. Sự kiện signup/login Google trong ChatGPT Auth0 application không tạo ContextForge user và không thêm team membership.
- **ChatGPT MCP OAuth** là một authorization-code flow riêng. Mỗi ChatGPT account tự hoàn tất authorization của nó; không bao giờ copy token giữa các account.

Với Gmail address đã được phê duyệt tường minh, dùng **EmailAuthService.create_sso_user()** từ `mcpgateway.services.email_auth_service`, sau đó thêm user vào COS team bằng **TeamManagementService.add_member_to_team()**.

Không dùng **SSOService.authenticate_or_create_user()** làm phương thức provision thủ công. Method đó xử lý inbound SSO callback và JIT path. Nó yêu cầu provider email claim đã xác minh; việc tạo user mới qua path này còn phụ thuộc auto-create policy của provider. Deployment hiện tại chủ đích đặt `auto_create_users=false`.

Hành vi quan trọng của phương thức dành cho administrator:

- Yêu cầu SSO provider record có ID resolve thành `auth0` và trường `is_enabled` là true.
- Cố ý bypass các JIT control như auto-create, trusted-domain check và pending-approval policy. Chỉ truyền những địa chỉ đã được administrator phê duyệt tường minh.
- Tạo account active, non-admin, không password với `auth_provider=auth0` và không có local password hash.
- Ban đầu đặt `email_verified=false`. Không tự đánh dấu địa chỉ là verified. Một SSO callback thành công sau đó có thể cập nhật verification từ provider's verified-email claim.
- Onboarding thông thường tạo personal team và gán default user/personal-team role đã cấu hình khi các feature đó được bật. Không tự tạo personal team thứ hai.

COS Multi-Account team membership là một grant riêng. Với quyền truy cập thông thường, dùng membership role `member`. Service chỉ chấp nhận `owner` hoặc `member`; `viewer` không phải EmailTeamMember role hợp lệ. Global RBAC role và team membership role là hai khái niệm tách biệt.

## Hợp đồng deployment hiện tại

Trạng thái được kiểm tra với live `cos-contextforge` runtime ngày 2026-11-05:

| Setting | Giá trị/ý nghĩa hiện tại |
| --- | --- |
| SSO provider ID | `auth0` |
| Provider state | Enabled; display name xác định đây chỉ là admin-provisioning |
| Provider auto-create | `false` — không kỳ vọng JIT user creation |
| Global `sso_enabled` | `false` |
| COS team | `COS Multi-Account`, active, non-personal |
| Default COS membership role cho Gmail user mới | `member` |

Service method tường minh hoạt động với provider record đã enable ngay cả khi global browser SSO đang tắt. REST provisioning router có điều kiện và không phải path hiện tại khi `sso_enabled=false`. Không bật global SSO chỉ để thêm một user.

Nếu `auth0` provider row bị thiếu hoặc disabled, **dừng lại**. Kiểm tra và khôi phục provider configuration đã biết qua change process được phê duyệt. Không tạo Auth0 application mới, xoay credential, chèn provider record tự đoán hoặc bật JIT làm workaround. Provider row là điều kiện tiên quyết cho service method; chỉ riêng việc row tồn tại không chứng minh browser SSO đã được cấu hình.

## Provision một hoặc nhiều địa chỉ đã phê duyệt

1. Xác nhận mỗi địa chỉ là Google account của đúng người và đã được phê duyệt quyền truy cập tường minh. Chuẩn hóa về chữ thường; loại bỏ bản trùng.
2. Làm theo hướng dẫn backup database trong [operations.vi.md](operations.vi.md) trước khi thay đổi theo lô.
3. Chạy script bên dưới từ host. Script resolve COS team theo tên thay vì dựa vào team UUID ghi nhớ từ trước.
4. Review output dry-run. Chỉ đổi `DRY_RUN` thành `False` sau khi xác nhận từng địa chỉ và target team.

```python
docker exec -i cos-contextforge python - <<'PY'
import asyncio

from mcpgateway.db import EmailTeam, EmailTeamMember, EmailUser, SSOProvider, SessionLocal
from mcpgateway.services.email_auth_service import EmailAuthService
from mcpgateway.services.team_management_service import TeamManagementService

EMAILS = [
    "new.person@gmail.com",
]
PROVISIONED_BY = "admin@cos.local"  # Use the actual administrator/audit identity.
DRY_RUN = True

async def main():
    emails = [value.strip().lower() for value in EMAILS]
    if not emails or any(not email for email in emails):
        raise ValueError("EMAILS must contain at least one non-empty address")
    if len(emails) != len(set(emails)):
        raise ValueError("EMAILS contains duplicates after lowercase normalization")

    with SessionLocal() as db:
        provider = db.query(SSOProvider).filter(SSOProvider.id == "auth0").one_or_none()
        if provider is None or not provider.is_enabled:
            raise RuntimeError("SSO provider 'auth0' is missing or disabled; stop and investigate")

        teams = db.query(EmailTeam).filter(
            EmailTeam.name == "COS Multi-Account",
            EmailTeam.is_active.is_(True),
            EmailTeam.is_personal.is_(False),
        ).all()
        if len(teams) != 1:
            raise RuntimeError(f"Expected exactly one active COS Multi-Account team; found {len(teams)}")
        team_id = teams[0].id

        auth = EmailAuthService(db)
        team_service = TeamManagementService(db)

        for email in emails:
            user = db.query(EmailUser).filter(EmailUser.email == email).one_or_none()
            if user is not None:
                if user.auth_provider != "auth0" or not user.is_active or user.is_admin or user.password_hash is not None:
                    raise RuntimeError(
                        f"{email}: existing account is not an active, non-admin, passwordless Auth0 account; manual review required"
                    )
                print(f"USER EXISTS: {email}")
            elif DRY_RUN:
                print(f"WOULD CREATE: {email} (passwordless, active, non-admin, provider=auth0)")
            else:
                await auth.create_sso_user(
                    email=email,
                    auth_provider="auth0",
                    is_admin=False,
                    is_active=True,
                    granted_by=PROVISIONED_BY,
                )
                print(f"USER CREATED: {email}")

            membership = db.query(EmailTeamMember).filter(
                EmailTeamMember.team_id == team_id,
                EmailTeamMember.user_email == email,
            ).one_or_none()

            if membership is not None and membership.role != "member":
                raise RuntimeError(
                    f"{email}: existing COS membership has role={membership.role!r}; do not change it implicitly"
                )

            if membership is not None and membership.is_active:
                print(f"COS MEMBERSHIP EXISTS: {email} (member)")
            elif DRY_RUN:
                print(f"WOULD ADD TO COS Multi-Account: {email} (member)")
            else:
                await team_service.add_member_to_team(
                    team_id=team_id,
                    user_email=email,
                    role="member",
                    invited_by=PROVISIONED_BY,
                    grant_source="manual",
                )
                print(f"COS MEMBERSHIP ADDED: {email} (member)")

asyncio.run(main())
PY
```

Script an toàn khi chạy lại với Auth0 user đã active và đã là `member`: script bỏ qua cả hai thao tác. Nếu tạo user thành công nhưng thêm team membership thất bại, chạy lại sau khi xử lý lỗi; script nhận diện user đã tồn tại và chỉ hoàn tất membership còn thiếu. Script dừng thay vì âm thầm thay provider, active/admin state hoặc team role khác `member` của account có sẵn.

## Xác minh

Với từng địa chỉ, xác nhận tất cả mục sau trong ContextForge admin UI hoặc database:

- user tồn tại đúng một lần;
- `auth_provider=auth0`, `is_active=true`, `is_admin=false`;
- account không password (`password_hash` là null);
- personal team tồn tại (khi bật automatic personal team);
- membership active trong `COS Multi-Account` với role `member`;
- không có admin/global RBAC grant bất thường.

Sau đó yêu cầu người dùng tự hoàn tất Auth0/Google sign-in và ChatGPT MCP OAuth flow dự kiến. Xác nhận request kết quả được resolve về đúng ContextForge user và team permission. Chỉ tạo account và team membership không chứng minh login hoặc MCP authorization end-to-end.

## REST endpoint không phải path mặc định ở đây

ContextForge admin provisioning router expose `POST /v1/admin/users/sso` chỉ khi admin API và SSO feature được bật; endpoint yêu cầu quyền `admin.user_management`. Live deployment hiện có `sso_enabled=false`; dùng quy trình service-level ở trên. Không thay đổi global SSO setting chỉ để expose endpoint này.
