# Provision Gmail users in ContextForge (Auth0)

Runbook for the current COS Multi-Account deployment. This documents explicit, administrator-approved, passwordless local-user provisioning. It is not an Auth0 application setup guide.

## Do not mix up the two authentication layers

- **ContextForge local user** is the account and authorization record. It must exist and be active before the user's email can resolve to ContextForge permissions.
- **Auth0 + Google** authenticates the person. A Google signup/login event in the ChatGPT Auth0 application does not create a ContextForge user or add team membership.
- **ChatGPT MCP OAuth** is a separate authorization-code flow. Each ChatGPT account completes its own authorization; never copy tokens between accounts.

For an explicitly approved Gmail address, use **EmailAuthService.create_sso_user()** from `mcpgateway.services.email_auth_service`, then add the user to the COS team with **TeamManagementService.add_member_to_team()**.

Do not use **SSOService.authenticate_or_create_user()** as the manual provisioning method. That method handles an inbound SSO callback and its JIT path. It requires a verified provider email claim; creating a new user through that path also depends on the provider's auto-create policy. The current deployment intentionally has `auto_create_users=false`.

Important behavior of the administrator method:

- It requires an SSO provider record whose ID resolves to `auth0` and whose `is_enabled` field is true.
- It deliberately bypasses JIT controls such as auto-create, trusted-domain checks, and pending-approval policy. Only pass addresses that an administrator has explicitly approved.
- It creates an active, non-admin, passwordless account with `auth_provider=auth0` and no local password hash.
- It explicitly starts with `email_verified=false`. Do not manually mark an address verified. A later successful SSO callback can update verification from the provider's verified-email claim.
- Normal onboarding creates a personal team and assigns configured default user/personal-team roles when those features are enabled. Do not create a second personal team manually.

The COS Multi-Account team membership is a separate grant. For ordinary access, use membership role `member`. The service accepts only `owner` or `member`; `viewer` is not a valid EmailTeamMember role. Global RBAC roles and team membership roles are separate concepts.

## Current deployment contract

State checked against the live `cos-contextforge` runtime on 2026-11-05:

| Setting | Current value / meaning |
| --- | --- |
| SSO provider ID | `auth0` |
| Provider state | Enabled; display name identifies it as admin-provisioning-only |
| Provider auto-create | `false` — do not expect JIT user creation |
| Global `sso_enabled` | `false` |
| COS team | `COS Multi-Account`, active, non-personal |
| Default COS membership role for a new Gmail user | `member` |

The explicit service method works with the enabled provider record even while global browser SSO is disabled. The REST provisioning router is conditional and is not the current path with `sso_enabled=false`. Do not turn on global SSO merely to add one user.

If the `auth0` provider row is missing or disabled, **stop**. Inspect and restore the known provider configuration through the approved change process. Do not create a new Auth0 application, rotate credentials, insert a guessed provider record, or enable JIT as a workaround. The provider row is a prerequisite for the service method; its presence alone does not prove that browser SSO is configured.

## Provision one or more approved addresses

1. Confirm each address is the intended person's Google account and has explicit access approval. Normalize to lowercase; remove duplicates.
2. Follow the database backup guidance in [operations.md](operations.md) before a batch change.
3. Run the script below from the host. It resolves the COS team by name instead of relying on a remembered team UUID.
4. Review the dry-run output. Change `DRY_RUN` to `False` only after confirming every address and target team.

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

The script is safe to rerun for an already-created active Auth0 user who is already a `member`: it skips both operations. If user creation succeeded but team membership failed, rerun after resolving the failure; it detects the existing user and completes only the missing membership. It stops rather than silently changing an existing account's provider, active/admin state, or a non-member team role.

## Verify

For every address, confirm all of the following in the ContextForge admin UI or database:

- user exists exactly once;
- `auth_provider=auth0`, `is_active=true`, `is_admin=false`;
- passwordless account (`password_hash` is null);
- personal team exists (when automatic personal teams are enabled);
- active membership in `COS Multi-Account` with role `member`;
- no unexpected admin/global RBAC grants.

Then have the person independently complete the intended Auth0/Google sign-in and ChatGPT MCP OAuth flow. Confirm the resulting request resolves to the expected ContextForge user and team permissions. Account creation and team membership alone do not prove login or end-to-end MCP authorization.

## REST endpoint is not the default path here

The ContextForge admin provisioning router exposes `POST /v1/admin/users/sso` only when the admin API and SSO feature are enabled, and it requires `admin.user_management` permission. The live deployment currently has `sso_enabled=false`; use the service-level procedure above. Do not change global SSO settings just to expose the endpoint.
