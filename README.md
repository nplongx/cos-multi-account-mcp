# COS Multi-Account MCP

Operational documentation for the COS Multi-Account ContextForge MCP gateway.

> **Deployment status:** development / trial. This repository documents a live deployment and its configuration contract. It is not a turnkey production deployment. Do not use the current Auth0 tenant or Google development keys for production.

## Architecture

```text
ChatGPT custom MCP connector
  └─ OAuth 2.0 Authorization Code + PKCE
       └─ Auth0 (Google social login)
            └─ RS256 access token (RFC 9068)
                 └─ ContextForge MCP gateway
                      └─ user email claim + active local user
                           └─ team membership / viewer RBAC
                                ├─ COS Core
                                ├─ COS Desktop
                                └─ COS Plugins
```

One MCP Virtual Server exposes three upstreams. Each ChatGPT account authorizes independently; do not share bearer tokens or upstream capability credentials between accounts.

## Deployed endpoint identifiers

| Setting | Value |
| --- | --- |
| MCP endpoint / resource | `https://cos.bougainvillea.dpdns.org/servers/3ebe2c8df4b64304917f4ae0efcf6c803939f3b/mcp` |
| Auth0 issuer | `https://dev-tyh0v4lmnge5xwa4.us.auth0.com/` |
| OAuth API | `COS Multi-Account MCP` |
| OAuth scope | `mcp:connect` plus `openid profile email` |
| Token profile | RFC 9068, RS256 |
| Email claim | `https://bougainvillea.dpdns.org/email` |
| ContextForge Virtual Server | `COS Multi-Account` |
| Visibility | `team` |

**Resource identifier note:** always copy the exact resource URI from the live ContextForge Virtual Server and its protected-resource metadata. The identifier is byte-for-byte significant. Do not copy a URI from an old note if it differs from the live server.

## Repository contents

- `docs/architecture.md` — request flow, trust boundaries and identity mapping.
- `docs/deployment.md` — deployment contract and safe setup procedure.
- `docs/oauth-setup.md` — Auth0, Google and ChatGPT connector configuration.
- `docs/operations.md` — health, discovery, logs and recovery checks.
- `docs/verification.md` — observed evidence and remaining acceptance tests.
- `SECURITY.md` — secret handling and disclosure policy.
- `.env.example` — placeholder-only environment template.

The deployment's Python overlay files are intentionally not copied into this documentation repository. Keep application source in its own reviewed source repository; do not mistake this runbook for a complete build context.

## Quick checks

The current host deployment uses Docker Compose and binds ContextForge to loopback. Run commands from the deployment directory:

```bash
docker compose ps
docker compose logs --tail=100 contextforge
curl -fsS http://127.0.0.1:4444/health
```

The protected-resource metadata endpoint is public by design. An unauthenticated MCP POST should be rejected with HTTP 401 and a `WWW-Authenticate` metadata reference. A successful metadata response does **not** prove that an authenticated MCP call works.

See the [detailed setup guide](GIST_LINK_PENDING) for step-by-step configuration and validation.

## Current acceptance status

| Check | Evidence / status |
| --- | --- |
| Health endpoint | HTTP 200 observed |
| RFC 9728 protected-resource metadata | HTTP 200 observed |
| Unauthenticated MCP request | HTTP 401 observed |
| ChatGPT OAuth authorization-code exchange | Auth0 recorded successful login and code exchange for one test account |
| ChatGPT plugin creation | Created in ChatGPT UI |
| MCP tool metadata | ChatGPT UI listed 19 tools in one inspection |
| Server-side email claim and RBAC | **Not yet proven end-to-end** |
| Refresh-token continuity | Not configured; `offline_access` not enabled |

Tool counts can differ between upstream inventory and a particular ChatGPT UI snapshot. Recheck live `tools/list` before treating a count as acceptance evidence.

## Security and deployment caveats

- This Auth0 tenant is a development/trial tenant.
- Google social login currently uses Auth0 development keys. Replace them with an owned Google OAuth client before production.
- The Google social connection was promoted at tenant/domain level for third-party OAuth. Review the wider application exposure before production.
- The current OAuth setup does not request `offline_access`; long-lived refresh-token behavior is not established.
- Auth0's post-login action requires a verified Google email and emits the namespaced email claim only for the exact MCP audience.
- ContextForge must resolve that verified identity to an active local user and enforce team membership and RBAC on each request.
- Cloudflare Access protects the Admin UI/API. Keep that boundary enabled.
- Never put `.env`, database files, bootstrap passwords, API keys, client secrets, private keys, bearer tokens or refresh tokens in Git, Gists, issues or screenshots.

## Documentation

See [docs/](docs/) and the linked step-by-step Gist. Review [SECURITY.md](SECURITY.md) before sharing this repository.

## License and attribution

The deployment overlay is adapted from IBM ContextForge, which is distributed under Apache-2.0. Any separately published derived source must retain required upstream copyright and license notices. This documentation bundle currently does not redistribute those overlay source files.
