# COS Multi-Account MCP

Deployment project for a multi-user ContextForge MCP gateway that fronts COS Core, Desktop, and Plugins with per-user OAuth authentication and team-scoped RBAC.

> **Status: development / trial.** The deployment and OAuth path have partial live evidence, but the complete ChatGPT-issued token -> email-claim -> ContextForge RBAC path is not yet accepted end to end. Do not treat the current Auth0/Google configuration as production-ready.

## What this repository contains

- A pinned ContextForge image and Docker build overlay.
- RFC 9728 protected-resource metadata routing for OAuth-enabled team Virtual Servers.
- Configurable JWT email-claim mapping for MCP access tokens.
- A loopback-only Docker Compose deployment template.
- A loopback-only COS Control API broker with per-ContextForge-user conversation ownership.
- A durable, owner-authenticated A2A mailbox with endpoint allowlists, idempotent delivery, TTL, ACK, and reply.
- Auth0 / Google OAuth, Cloudflare Tunnel and RBAC runbooks.
- A placeholder-only environment template. It contains no deployment credentials.

The Python files are adapted from IBM ContextForge and retain their Apache-2.0 SPDX notices. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Architecture

```text
ChatGPT connection (one per user)
        |
        | OAuth 2.0 Authorization Code + PKCE
        v
Auth0 tenant (Google social login)
        |
        | RS256 access token; resource audience + verified email claim
        v
Cloudflare Named Tunnel
        |
        v
ContextForge MCP gateway (127.0.0.1:4444)
        |
        | active local user -> team membership -> RBAC
        v
Team Virtual Server
   |          |          |                    |
 COS Core  COS Desktop  COS Plugins   COS Control Broker
                                           (127.0.0.1:4445)
                                                 |
                              +------------------+------------------+
                              |                                     |
                     owner-scoped agent registry           shared A2A mailbox
                              |                           (SQLite + recipient ACL)
                              v                                     |
                    COS Local Control API                 Account A <-> Account B
                    (127.0.0.1:37121)                    via signed ContextForge identities
```

Each ChatGPT account authorizes independently and receives its own user token. Do not share bearer tokens, refresh tokens, Auth0 client secrets, or upstream capability credentials between users.

## Repository map

| Path | Purpose |
| --- | --- |
| `Dockerfile`, `compose.yaml` | Reproducible local image build and loopback deployment |
| `config.py` | ContextForge configuration overlay, including configurable MCP email claim |
| `streamablehttp_transport.py` | MCP OAuth challenge and access-token identity mapping |
| `routers/well_known.py` | RFC 9728 protected-resource metadata endpoints |
| `services/server_service.py` | Team/OAuth-aware protected-resource metadata lookup |
| `cos_control_broker.py` | Signed-identity, per-user broker for COS Local Control API |
| `.env.example` | Placeholder-only secret/configuration template |
| `docs/architecture.md` | Trust boundaries and request flow |
| `docs/deployment.md` | Docker and Cloudflare deployment |
| `docs/oauth-setup.md` | Auth0, Google and ChatGPT setup |
| `docs/sso-user-provisioning.md` | Admin-approved, passwordless Gmail provisioning and COS team membership |
| `docs/operations.md` | Health, access, backup and recovery |
| `docs/verification.md` | Acceptance checks and current evidence |
| `docs/deployment-guide.md` | Step-by-step operator runbook |
| `docs/getting-started.md` | End-to-end setup guide and production gates |
| `SECURITY.md` | Secret-handling and security reporting rules |

## Quick start

1. Review [SECURITY.md](SECURITY.md), [docs/deployment.md](docs/deployment.md), and [docs/oauth-setup.md](docs/oauth-setup.md).
2. Copy `.env.example` to `.env`, replace every placeholder, and set file permissions to `0600`.
3. Create the persistent volume, build, and start the gateway:

   ```bash
   cp .env.example .env
   chmod 600 .env
   # Edit .env before starting.
   docker volume create cos-contextforge-data
   docker compose build
   docker compose up -d
   ```

4. Confirm `curl -fsS http://127.0.0.1:4444/health` succeeds.
5. Publish the loopback origin through a Cloudflare Named Tunnel. Keep the Admin UI/API behind Cloudflare Access.
6. Configure Auth0 and Google using the exact resource URI exposed by the live ContextForge Virtual Server metadata. Never guess or reuse a stale resource identifier.
7. Run the full checks in [docs/verification.md](docs/verification.md).

This repository does not contain a live `.env`, database, tunnel credential, Auth0 secret, or ChatGPT token.

## Deployment contract

- Base image is pinned by digest in [Dockerfile](Dockerfile).
- ContextForge listens only on `127.0.0.1:4444`.
- Docker uses host networking and persistent volume `cos-contextforge-data`.
- The public MCP endpoint is `https://<your-hostname>/servers/<server-id>/mcp`.
- The matching RFC 9728 metadata path is `https://<your-hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp`.
- The Auth0 API identifier, ContextForge protected resource, and metadata `resource` value must match byte-for-byte.
- Admin UI/API must not be exposed directly to the Internet; use Cloudflare Access.
- COS Control Broker binds only to `127.0.0.1:4445`; its Control API token is mounted read-only and never returned to MCP clients.
- The broker trusts only HMAC-signed ContextForge user ID/email headers. It ignores forwarded admin/team claims and authorizes agent operations through its own owner registry.
- A2A endpoints and messages are stored in the broker's persistent SQLite volume. Endpoint ACLs are private by default and keyed by the sender's verified ContextForge identity fingerprint.
- A2A mailbox delivery is durable pull-based delivery. It does not auto-wake another ChatGPT tab, read another account's conversations, or delegate ChatGPT credentials.

## Cross-account A2A mailbox

Each Workstream registers its own `a2a_endpoint_register` endpoint under its authenticated ContextForge identity. Call `a2a_directory_list`, or read `peer_directory` from the existing `a2a_endpoint_list` tool, to discover active endpoints across the broker deployment. Endpoint owners configure `a2a_endpoint_set_peer_acl` with exact sender endpoint IDs, or use the backwards-compatible `a2a_endpoint_set_acl` schema with `sender_acl_token` values from `peer_directory`. This keeps Workstreams isolated even when two Workstreams share one ContextForge identity. Passing real owner fingerprints to the old setter retains legacy account-level ACL behavior only for endpoints not yet migrated. Senders use `a2a_send_message`; receivers use `a2a_inbox_read`, then `a2a_message_ack` or `a2a_message_reply`. Replies preserve the original correlation ID and acknowledge the original message atomically. `idempotency_key` prevents duplicate enqueue on retry. Mailbox delivery remains pull-based; a queued message does not wake another ChatGPT tab.

Messages are durable across broker restarts, expire after the requested TTL (default 24 hours, maximum 7 days), and are bounded by endpoint and pending-inbox limits. A queued message is not proof the receiving agent has read or acted on it. `a2a_inbox_read` marks it received; ACK or reply is the explicit completion signal. This first implementation is a mailbox/router, not an automatic worker wake transport.

## Current acceptance status

Evidence recorded during initial setup:

| Check | Status |
| --- | --- |
| ContextForge health endpoint | HTTP 200 observed |
| RFC 9728 protected-resource metadata | HTTP 200 observed |
| Unauthenticated MCP POST | HTTP 401 observed |
| Auth0 Google login and authorization-code exchange | Observed for one test identity |
| ChatGPT custom MCP connector creation | Completed in ChatGPT UI |
| ContextForge-issued tool inventory | 22 tools across three upstreams observed |
| ChatGPT UI tool inventory | 19 tools observed in one UI inspection; counts can differ |
| Server-side custom email claim and team RBAC for a ChatGPT-issued token | **Not yet proven end to end** |
| Production IdP / Google OAuth client | **Not ready**; development/trial credentials were used |

Do not mark OAuth/RBAC acceptance complete until a real ChatGPT-issued token is validated by ContextForge and the expected user identity and team permission are verified server-side. See [docs/verification.md](docs/verification.md).

## Detailed guide

The setup walkthrough is also published as a public GitHub Gist:

**[COS Multi-Account MCP — setup guide](https://gist.github.com/nplongx/4ef72aa285ee4887e5b9ac2959c182f7)**

The detailed operator runbook remains available here:

**[COS Multi-Account MCP — operator runbook](https://gist.github.com/nplongx/1f17336a782a99fb4d0d15181532a5b9)**

Use the repository's `docs/` directory as the version-controlled source of truth. Gists are convenience copies, not secret stores.

## Security caveats

- Current test setup used an Auth0 development/trial tenant and Google development keys. Replace them with an owned Google OAuth client and production-grade IdP configuration before production.
- Review the tenant-wide exposure created when a Google social connection is promoted for third-party applications.
- `offline_access` / refresh-token continuity was not part of the initial accepted test.
- The Auth0 action must reject unverified email and emit the namespaced email claim only for the exact MCP audience.
- ContextForge must resolve the verified email to an active local user and enforce team membership and RBAC on every request.
- Never commit `.env`, database files, backups, bootstrap passwords, API keys, client secrets, private keys, bearer tokens, refresh tokens, Cloudflare credentials, or browser session data.
- Broker-created conversations run under the ChatGPT account/profile currently signed in to the local COS runtime. They are not independent ChatGPT account credentials and do not provide separate account quotas.

## License

The ContextForge-derived overlay is marked Apache-2.0 in its source headers. This repository includes the Apache-2.0 license text and attribution in [NOTICE](NOTICE).
