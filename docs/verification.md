# Verification and acceptance

## Safe baseline checks

Run from the deployment host:

```bash
curl -i http://127.0.0.1:4444/health
curl -i https://<your-hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

Send an unauthenticated POST to the MCP endpoint only as a negative test. It should fail closed with HTTP 401 and an OAuth metadata challenge. Never include a real token in a command line or shell history.

## OAuth/RBAC end-to-end acceptance

Complete the following with a test account:

- [ ] ChatGPT completes Authorization Code + PKCE.
- [ ] Auth0 records a successful Google login and authorization-code exchange.
- [ ] Auth0 access token uses the configured issuer and exact MCP audience.
- [ ] Token contains the required scope and verified namespaced email claim.
- [ ] ContextForge accepts the token.
- [ ] ContextForge resolves the claim to the intended active local user.
- [ ] Team membership and RBAC permit only the expected Virtual Server/tools.
- [ ] A user outside the team is denied.
- [ ] A disabled user is denied.
- [ ] A token with wrong audience, wrong issuer, expired token, or missing scope is denied.
- [ ] The same MCP endpoint works with separately authorized ChatGPT accounts and does not reuse one user's credential for another.

Do not mark the integration production-ready until these checks pass.

## Evidence recorded during initial setup

The initial test environment recorded:

| Check | Observed result |
| --- | --- |
| Local ContextForge health | HTTP 200 |
| RFC 9728 protected-resource metadata | HTTP 200 |
| MCP request without bearer token | HTTP 401 |
| Auth0 Google login and code exchange | Successful for one test identity |
| ChatGPT custom MCP connector | Created |
| Tools in one ContextForge inventory | 22 across three upstreams |
| Tools shown in one ChatGPT UI inspection | 19 |
| Server-side email-claim and team-RBAC acceptance | Not yet proven end to end |

The tool-count difference is not necessarily a failure; re-run `tools/list` with the actual user token. Counts are snapshots, not acceptance criteria.

## Production gates still open

- Replace Auth0 development/trial tenant and Google development keys.
- Review tenant-wide third-party OAuth exposure.
- Prove real token acceptance, email claim mapping, and team RBAC.
- Define refresh-token policy before requesting `offline_access`.
- Test database backup/restore and credential rotation.
- Review Cloudflare Access policies and external exposure.
