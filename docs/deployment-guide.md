# COS Multi-Account MCP — operator runbook

Repository: https://github.com/nplongx/cos-multi-account-mcp

This runbook deploys one ContextForge MCP Virtual Server for a team. Each ChatGPT account authenticates independently using OAuth Authorization Code + PKCE. ContextForge validates the user's token, maps its verified email claim to an active local user, and enforces team membership/RBAC.

> Development/trial status: the original test used Auth0 development keys. Replace those before production. Complete the server-side token/email/RBAC acceptance checks before production use.

## 1. Understand the request path

```text
ChatGPT user A / user B / user C
           |
           | independent OAuth authorization + PKCE
           v
      Auth0 + Google
           |
           | RS256 access token for exact MCP resource
           v
    Cloudflare Named Tunnel
           |
           v
 ContextForge (loopback origin)
           |
           | verified email -> active local user -> team/RBAC
           v
 Team Virtual Server -> COS Core / Desktop / Plugins
```

Do not share an access token, refresh token, OAuth client secret, or upstream capability credential between people.

## 2. Prepare the host

Requirements:

- Docker Engine and Docker Compose v2.
- A Linux host.
- A Cloudflare Named Tunnel and hostname under your control.
- An Auth0 tenant and a Google OAuth client you own.
- A persistent database volume.

Clone the repository:

```bash
git clone https://github.com/nplongx/cos-multi-account-mcp.git
cd cos-multi-account-mcp
```

Create a private environment file:

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
openssl rand -hex 32
```

Set separate generated values for `JWT_SECRET_KEY` and `AUTH_ENCRYPTION_SECRET`. Set unique admin and default-user passwords. Never put real values into GitHub or this Gist.

Set `APP_DOMAIN` to the external HTTPS hostname and `MCP_OAUTH_EMAIL_CLAIM` to the claim URI that Auth0 will issue.

## 3. Build and start ContextForge

```bash
docker volume create cos-contextforge-data
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 contextforge
curl -fsS http://127.0.0.1:4444/health
```

The service must bind to `127.0.0.1:4444`. Do not expose port 4444 directly to the Internet.

## 4. Configure Cloudflare

Create a Named Tunnel route from your chosen hostname to:

```text
http://127.0.0.1:4444
```

Protect `/admin/*` and administrative APIs with Cloudflare Access. Keep Tunnel tokens, Access service tokens, and tunnel credentials on the host only.

The intended public surface includes health and protected-resource discovery plus the OAuth-protected MCP endpoint. Admin interfaces must stay behind Access.

## 5. Create the ContextForge team and Virtual Server

In the ContextForge admin interface:

1. Create the team.
2. Add each allowed person as an active local user with a verified email matching their Google identity.
3. Add each user to the team and assign least-privilege RBAC.
4. Configure the COS Core, Desktop, and Plugins upstream MCP servers.
5. Create one team-visible Virtual Server with OAuth enabled.
6. Retrieve its RFC 9728 protected-resource metadata.

The live metadata `resource` is the canonical OAuth audience. Copy it exactly. Do not use an old URL or guess the Server ID.

## 6. Configure Auth0

Create an Auth0 API:

- Identifier: exact metadata `resource`;
- signing algorithm: RS256;
- access-token profile: RFC 9068, where supported;
- required scope: `mcp:connect`;
- user identity scopes: `openid profile email`.

Enable the Resource Parameter Compatibility Profile when required by the client integration.

Configure Google social login with an OAuth client you own. Do not use Auth0 development keys for production. Review whether the Google connection is available to every third-party application in the tenant.

Add a Post-Login Action that:

1. runs only for the exact MCP audience;
2. rejects missing or unverified email;
3. emits the verified email under a namespaced custom claim;
4. does not log or disclose tokens.

Use the same claim URI in the Action and ContextForge's `MCP_OAUTH_EMAIL_CLAIM` setting.

Example:

```javascript
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
```

Set Action secrets `MCP_RESOURCE_IDENTIFIER` and `MCP_EMAIL_CLAIM` in Auth0. Adapt this sample to the actual event schema and test it in a non-production tenant first.

Do not enable `offline_access` until refresh-token storage, rotation, revocation, and recovery are designed and verified.

## 7. Connect ChatGPT

For each user separately:

1. Use a ChatGPT plan/workspace that permits the required custom MCP connection.
2. Add the HTTPS endpoint: `https://<hostname>/servers/<server-id>/mcp`.
3. Select OAuth.
4. Complete the Auth0 redirect and choose the correct Google account.
5. Verify the expected tools are listed.

Use the dynamic client metadata and redirect URI generated by ChatGPT. Do not hard-code a callback URL. Never export a token from one user's connection to another.

## 8. Verify the security contract

Health:

```bash
curl -i http://127.0.0.1:4444/health
```

Protected-resource discovery:

```text
https://<hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

Negative unauthenticated test: POST to the MCP endpoint without a bearer token. Expected result: HTTP 401 with a `WWW-Authenticate` resource-metadata challenge.

For an authenticated test, verify server-side that the token has:

- the expected Auth0 issuer;
- the exact ContextForge resource audience;
- valid expiry and required `mcp:connect` scope;
- a verified custom email claim.

Then verify ContextForge resolves that email to the intended active user and applies team RBAC. Verify a disabled user and a non-member are denied.

Never paste a real token into a shell command, issue, Gist, screenshot, or chat log.

## 9. Operations and recovery

Inspect:

```bash
docker compose ps
docker compose logs --tail=200 contextforge
```

Back up the database volume before upgrades. Keep backups encrypted and outside the repository. Do not use `docker compose down -v` for routine restarts; the volume contains identity and server configuration state.

If any credential leaks, revoke/rotate it at the issuer, review audit logs, and re-authorize affected users. Deleting the file from the latest commit does not remove it from Git history.

## 10. Acceptance status

The initial setup observed health HTTP 200, RFC 9728 metadata HTTP 200, and unauthenticated MCP HTTP 401. One Google/Auth0 login and authorization-code exchange was observed. A complete server-side proof of ChatGPT token -> custom email claim -> ContextForge team/RBAC remains an acceptance gate.

Production gates:

- replace Auth0 trial tenant and Google development keys;
- review third-party OAuth exposure;
- verify real ChatGPT token audience, scope, and email claim;
- verify member, non-member, and disabled-user authorization;
- test backup/restore and credential rotation.

Version-controlled docs and source: https://github.com/nplongx/cos-multi-account-mcp
