# COS Multi-Account MCP

Deployment project for a multi-user ContextForge MCP gateway that fronts COS Core, Desktop, and Plugins with per-user OAuth authentication and team-scoped RBAC.

> **Status: development / trial.** The deployment and OAuth path have partial live evidence, but the complete ChatGPT-issued token -> email-claim -> ContextForge RBAC path is not yet accepted end to end. Do not treat the current Auth0/Google configuration as production-ready.

## What this repository contains

- A pinned ContextForge image and Docker build overlay.
- RFC 9728 protected-resource metadata routing for OAuth-enabled team Virtual Servers.
- Configurable JWT email-claim mapping for MCP access tokens.
- A loopback-only Docker Compose deployment template.
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
        | resolve active local user -> team membership -> RBAC
        v
Team Virtual Server
   |          |          |
 COS Core  COS Desktop  COS Plugins
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
| `.env.example` | Placeholder-only secret/configuration template |
| `docs/architecture.md` | Trust boundaries and request flow |
| `docs/deployment.md` | Docker and Cloudflare deployment |
| `docs/oauth-setup.md` | Auth0, Google and ChatGPT setup |
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

The setup walkthrough is also available as an unlisted GitHub Gist:

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

## License

The ContextForge-derived overlay is marked Apache-2.0 in its source headers. This repository includes the Apache-2.0 license text and attribution in [NOTICE](NOTICE).
