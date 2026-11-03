# OAuth setup: Auth0, Google, and ChatGPT

This guide describes the configuration contract. Auth0 dashboard labels and ChatGPT connector capabilities can change; verify current provider behavior before production rollout.

## 1. Create the Auth0 API

Create an API whose Identifier is exactly the `resource` returned by the live ContextForge protected-resource metadata endpoint:

```text
https://<your-hostname>/servers/<server-id>/mcp
```

Use the exact value, byte-for-byte. Do not add or remove a trailing slash.

Configure:

- token signing algorithm: RS256;
- access-token profile: RFC 9068, when available for the tenant/client combination;
- required scope: `mcp:connect`;
- OIDC scopes for identity: `openid profile email`;
- Resource Parameter Compatibility Profile: enabled when required by the ChatGPT client;
- no client-credentials grant for ordinary user connections.

Do not request `offline_access` unless refresh-token policy has been explicitly designed, reviewed, and tested.

## 2. Configure Google login

Configure a Google social connection in Auth0 using an OAuth client owned by the deployment operator.

The initial environment used Auth0 development keys. Those keys are for testing only. Before production:

1. Create an owned Google OAuth client.
2. Configure the correct authorized redirect URI from Auth0.
3. Replace the development keys in Auth0.
4. Review whether the social connection is enabled for all third-party applications or only intended clients.
5. Confirm the provider returns `email` and `email_verified`.

Avoid collecting broader Google scopes unless required.

## 3. Add a Post-Login Action

The Action must:

- apply only to the exact MCP API audience;
- deny login when email is absent or `email_verified` is not true;
- emit the verified email under the exact custom claim URI configured in ContextForge;
- avoid adding tokens or secrets to logs.

Illustrative Action logic (adapt the event/secret names to the Auth0 tenant):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const expectedAudience = event.secrets.MCP_RESOURCE_IDENTIFIER;
  const claimName = event.secrets.MCP_EMAIL_CLAIM;

  if (event.resource_server?.identifier !== expectedAudience) {
    return;
  }

  const email = event.user?.email;
  if (!email || event.user?.email_verified !== true) {
    api.access.deny("A verified email address is required.");
    return;
  }

  api.accessToken.setCustomClaim(claimName, email.toLowerCase());
};
```

Store `MCP_RESOURCE_IDENTIFIER` and `MCP_EMAIL_CLAIM` as Action secrets. Set ContextForge's `MCP_OAUTH_EMAIL_CLAIM` to the same claim URI.

## 4. Provision ContextForge users

For every permitted person:

1. Create or invite a local ContextForge user with the same verified email.
2. Mark the account active.
3. Add the user to the owning team.
4. Assign the minimum required role/RBAC.
5. Confirm that the Virtual Server is visible to that team.

An Auth0 social login must not silently create an unrestricted ContextForge account. The gateway must resolve the verified token identity to an already authorized local user.

## 5. Configure ChatGPT

1. Use a ChatGPT workspace/account that supports the required custom MCP connector capability.
2. Add the HTTPS MCP endpoint for the team Virtual Server.
3. Select OAuth authentication.
4. Complete the Auth0 authorization flow and sign in with the intended Google account.
5. Repeat independently for each account. Never share a token between accounts.
6. Confirm the connection lists the expected tools.

Use ChatGPT's generated OAuth client metadata and redirect URI. Do not hard-code a callback URL from a prior setup.

## 6. Required token claims

Validate the access token server-side without copying it into tickets, Gists, source files, or shell history. Expected claims include:

- `iss`: configured Auth0 issuer;
- `aud`: exact ContextForge resource identifier;
- `exp`: valid expiration;
- `scope`: includes `mcp:connect`;
- custom email claim: verified email matching an active local ContextForge user.

A successful Google login or Auth0 code exchange alone does not prove that ContextForge accepted the token or enforced RBAC.
