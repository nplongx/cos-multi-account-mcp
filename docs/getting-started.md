# COS Multi-Account MCP — setup guide

**Repository:** https://github.com/nplongx/cos-multi-account-mcp
**Existing operator runbook:** https://gist.github.com/nplongx/1f17336a782a99fb4d0d15181532a5b9

This guide covers host preparation, deployment, OAuth setup, ChatGPT connection, and security checks. The repository's docs directory remains the version-controlled source of truth. This Gist is a navigable walkthrough.

> **Status: development / trial.** Initial deployment checks passed, but the complete ChatGPT token → verified email claim → ContextForge team/RBAC path has not been accepted end to end. Do not treat this configuration as production-ready.

## 1. Architecture

~~~text
ChatGPT user account
        | OAuth 2.0 Authorization Code + PKCE
        v
Auth0 tenant + Google social login
        | RS256 access token for exact MCP resource
        v
Cloudflare Named Tunnel (HTTPS)
        v
ContextForge gateway (127.0.0.1:4444)
        | verified email -> active local user -> team membership/RBAC
        v
Team Virtual Server -> COS Core / COS Desktop / COS Plugins
~~~

Each person authorizes their own ChatGPT connection. Never share access tokens, refresh tokens, OAuth client secrets, tunnel credentials, or upstream capability credentials.

## 2. Prerequisites

Prepare a Linux host with Docker Engine and Docker Compose v2, a Cloudflare account with a Named Tunnel and a hostname you control, an Auth0 tenant, a Google OAuth client you own, and admin access to ContextForge.

Check Docker:

~~~bash
docker version
docker compose version
~~~

## 3. Clone and configure

~~~bash
git clone https://github.com/nplongx/cos-multi-account-mcp.git
cd cos-multi-account-mcp
cp .env.example .env
chmod 600 .env
~~~

Generate two independent secrets:

~~~bash
openssl rand -hex 32
openssl rand -hex 32
~~~

Edit .env, replacing every placeholder:

| Variable | Required value |
| --- | --- |
| **APP_DOMAIN** | Public HTTPS origin, e.g. https://mcp.example.com |
| **MCP_OAUTH_EMAIL_CLAIM** | Exact namespaced claim URI emitted by Auth0 |
| **JWT_SECRET_KEY** | First random secret |
| **AUTH_ENCRYPTION_SECRET** | Second, different random secret |
| **PLATFORM_ADMIN_EMAIL** | Operator's bootstrap admin email |
| **PLATFORM_ADMIN_PASSWORD** | Unique, strong bootstrap admin password |
| **PLATFORM_ADMIN_FULL_NAME** | Bootstrap admin display name |
| **DEFAULT_USER_PASSWORD** | Separate strong default-user password |
| **BASIC_AUTH_PASSWORD** | Separate strong Basic Auth password |

Do not reuse passwords or secrets. Keep .env local; it is ignored by Git. Never put real values in .env.example, source code, GitHub issues, Gists, screenshots, or shell history.

## 4. Build and start

Create the persistent volume once:

~~~bash
docker volume create cos-contextforge-data
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 contextforge
~~~

Verify local health:

~~~bash
curl -fsS http://127.0.0.1:4444/health
~~~

Compose binds ContextForge to 127.0.0.1:4444 using host networking. Keep this loopback-only origin; do not expose port 4444 directly to the Internet. The external cos-contextforge-data volume stores gateway state.

## 5. Configure Cloudflare Tunnel

Create a Cloudflare Tunnel public-hostname route:

| Setting | Value |
| --- | --- |
| Hostname | Your MCP hostname |
| Service | HTTP |
| Origin URL | http://127.0.0.1:4444 |

Set APP_DOMAIN to the matching HTTPS origin and restart:

~~~bash
docker compose up -d
~~~

Protect the ContextForge Admin UI and administrative APIs with Cloudflare Access. Verify actual route patterns and policies against the deployed ContextForge version. Do not assume the MCP hostname automatically protects administrative routes. Keep Tunnel and Access credentials on the host only.

## 6. Bootstrap ContextForge

Through the protected Admin UI:

1. Sign in with the bootstrap administrator from .env; change bootstrap/default credentials immediately.
2. Create a team.
3. Provision each explicitly approved person as an active local ContextForge user. For this deployment, use the administrator-driven passwordless Auth0 procedure below; a Google/Auth0 signup by itself does not create a local ContextForge user.
4. Add each provisioned user to the team with the least-privilege membership role (`member` for ordinary COS Multi-Account access).
6. Configure COS Core, COS Desktop, and COS Plugins as upstream MCP servers. Store upstream credentials only in ContextForge.
7. Create a team-visible Virtual Server and enable OAuth.
8. Record its live server ID.

Fetch its protected-resource metadata:

~~~bash
curl -fsS \
  "https://<hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp"
~~~

The metadata resource value is the canonical OAuth audience. Copy it exactly, including path and trailing-slash behavior. Never guess the server ID or reuse a stale resource URL.

### Provision Gmail users for the current COS deployment

Keep these identities separate:

- **Auth0 + Google login** authenticates the Google identity.
- **ContextForge local user** stores the active account and authorization state.
- **COS Multi-Account membership** grants access to the team Virtual Server.

For the current deployment, provision an explicitly approved Gmail address with `EmailAuthService.create_sso_user(email=..., auth_provider="auth0", is_admin=False, is_active=True, granted_by=...)`, then add it to `COS Multi-Account` with `TeamManagementService.add_member_to_team(..., role="member", grant_source="manual")`.

Important: the enabled `auth0` provider record is required. Its `auto_create_users` setting is `false`, and global `sso_enabled` is currently `false`. The administrator service method is the intended path and deliberately bypasses JIT auto-create, trusted-domain, and approval checks, so use it only after explicit access approval. It creates a passwordless, non-admin account (`password_hash=NULL`, initially `email_verified=false`) and normal onboarding creates the personal team/default roles. Do not manually mark email verified, create another personal team, or use `viewer` as the COS membership role; the service accepts `owner` or `member`.

Do not use `SSOService.authenticate_or_create_user()` for manual provisioning, do not enable global SSO just to add a user, and do not create a replacement Auth0 application. The REST endpoint `POST /v1/admin/users/sso` is conditional on SSO being enabled and is not the current route. Follow the [complete Gmail provisioning runbook](https://github.com/nplongx/cos-multi-account-mcp/blob/main/docs/sso-user-provisioning.md), including its dry-run script and verification checklist.

## 7. Configure Auth0 and Google

### Auth0 API

Create an Auth0 API with:

- Identifier: exactly the metadata resource from the previous step;
- signing algorithm: RS256;
- required scope: mcp:connect;
- identity scopes: openid profile email;
- RFC 9068 access-token profile where supported;
- Resource Parameter Compatibility Profile enabled when required by the MCP client.

Do not configure client-credentials flow for ordinary user connections. Do not enable offline_access until refresh-token storage, rotation, revocation, and recovery have been designed and tested.

### Google login

Use a Google OAuth client owned by the operator. Configure its authorized redirect URI exactly as shown by Auth0. Replace Auth0 development keys before production. Review which third-party applications can use the Google social connection.

### Post-Login Action

The Action must run only for the intended MCP API, reject missing or unverified email, and emit a namespaced custom claim.

Illustrative logic:

~~~javascript
exports.onExecutePostLogin = async (event, api) => {
  const expectedAudience = event.secrets.MCP_RESOURCE_IDENTIFIER;
  const claimName = event.secrets.MCP_EMAIL_CLAIM;

  if (event.resource_server?.identifier !== expectedAudience) return;

  const email = event.user?.email;
  if (!email || event.user?.email_verified !== true) {
    api.access.deny("A verified email address is required.");
    return;
  }

  api.accessToken.setCustomClaim(claimName, email.toLowerCase());
};
~~~

In Auth0, create Action secrets MCP_RESOURCE_IDENTIFIER and MCP_EMAIL_CLAIM, set them to the exact API identifier and claim URI, adapt the sample to the tenant's event schema, test in non-production, deploy, and attach it to the Login flow.

Set ContextForge's MCP_OAUTH_EMAIL_CLAIM to the same claim URI. The token email must resolve to an already-active ContextForge user. Do not silently provision unrestricted accounts from social login.

## 8. Connect each ChatGPT account

For each person separately:

1. Use an account/workspace that supports the required custom MCP connection.
2. Add https://<hostname>/servers/<server-id>/mcp.
3. Select OAuth authentication.
4. Complete the Auth0 redirect and sign in with the intended Google account.
5. Verify expected team tools appear.
6. Repeat independently for each authorized person.

Use OAuth client metadata and redirect URI generated by ChatGPT. Do not hard-code a callback URL from an old setup. Never export one user's token for another user.

## 9. Verify authentication and RBAC

- Local health: curl -i http://127.0.0.1:4444/health — expect HTTP 200.
- Public metadata: https://<hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp — expect HTTP 200 and the exact resource identifier configured in Auth0.
- Unauthenticated MCP POST: send a request without an Authorization header — expect HTTP 401 with a WWW-Authenticate resource-metadata challenge.

For an authenticated test, verify server-side (without copying the bearer token into logs or terminals) that the token has the expected issuer, exact resource audience, valid expiry, mcp:connect scope, and verified namespaced email claim. Then verify ContextForge resolves the email to the intended active local user and enforces team RBAC.

Test an authorized member, a non-member, a disabled user, and an expired/invalid token. A successful Google login or authorization-code exchange alone does not prove gateway authentication or RBAC.

## 10. Operations and backup

~~~bash
docker compose ps
docker compose logs --tail=200 contextforge
~~~

Before upgrades, stop the service and back up the named volume to encrypted storage outside the repository:

~~~bash
docker compose stop contextforge
docker run --rm \
  -v cos-contextforge-data:/data \
  -v "$PWD":/backup \
  alpine tar -czf /backup/contextforge-data-backup.tgz -C /data .
docker compose up -d
~~~

The backup contains identity and server configuration data. Encrypt it, restrict access, and never commit it. Do not use docker compose down -v for routine restarts; it can remove persistent state.

## 11. Troubleshooting

| Symptom | Checks |
| --- | --- |
| Container fails | docker compose logs --tail=200 contextforge; verify required .env values |
| Health check fails | Check container state and listener on 127.0.0.1:4444 |
| Public hostname unavailable | Check Tunnel route, DNS, origin URL, and Cloudflare |
| OAuth audience mismatch | Compare Auth0 API Identifier and metadata resource byte-for-byte |
| Email claim missing | Check Action trigger/secrets, verified email, and exact claim URI |
| User authenticated but denied | Check local account status, team membership, role, and Virtual Server visibility |
| Tools missing | Check team Virtual Server and upstream server health |

If a credential leaks, revoke/rotate it at the issuer, review logs, and re-authorize affected users. Deleting a secret from the latest commit does not remove it from Git history.

## 12. Security and production gates

Before production:

- replace development/trial OAuth credentials with owned production credentials;
- review Cloudflare Access coverage for Admin UI and administrative APIs;
- verify issuer, audience, scope, email claim, and expiry server-side;
- verify active-member, non-member, disabled-user, and invalid-token behavior;
- test backup restoration and credential rotation;
- review ContextForge updates and rebuild the pinned image deliberately;
- keep secrets, database files, backups, and tunnel credentials outside Git.

Initial setup evidence included health HTTP 200, protected-resource metadata HTTP 200, unauthenticated MCP HTTP 401, and one observed Google/Auth0 authorization-code exchange. Full ChatGPT-issued token → custom email claim → ContextForge RBAC acceptance remains **unproven**. This project is not yet production-ready.

## Related documentation

- [Repository and source files](https://github.com/nplongx/cos-multi-account-mcp)
- [Deployment documentation](https://github.com/nplongx/cos-multi-account-mcp/blob/main/docs/deployment.md)
- [OAuth setup reference](https://github.com/nplongx/cos-multi-account-mcp/blob/main/docs/oauth-setup.md)
- [Acceptance and verification checklist](https://github.com/nplongx/cos-multi-account-mcp/blob/main/docs/verification.md)
- [Existing detailed operator runbook Gist](https://gist.github.com/nplongx/1f17336a782a99fb4d0d15181532a5b9)
