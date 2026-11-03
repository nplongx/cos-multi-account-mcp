# Deployment

## Prerequisites

- Linux host with Docker Engine and Docker Compose v2.
- A Cloudflare account and a configured Named Tunnel.
- A hostname under a domain you control.
- A persistent Docker volume for the ContextForge database.
- The four ContextForge overlay files in this repository.

## 1. Configure secrets

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
```

Generate independent values for `JWT_SECRET_KEY` and `AUTH_ENCRYPTION_SECRET`; do not reuse one value for both. Set unique bootstrap and default-user passwords. Never copy production values into `.env.example`.

Set:

- `APP_DOMAIN` to the external HTTPS origin, for example `https://mcp.example.com`.
- `MCP_OAUTH_EMAIL_CLAIM` to the exact namespaced claim URI emitted by the Auth0 Action.

## 2. Build and start

```bash
docker volume create cos-contextforge-data
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 contextforge
curl -fsS http://127.0.0.1:4444/health
```

The Compose file uses host networking and binds the service to `127.0.0.1:4444`. Do not change this to `0.0.0.0` unless you have deliberately designed and reviewed a different network boundary.

## 3. Configure the Named Tunnel

Configure the Cloudflare Tunnel ingress to send the MCP hostname to:

```text
http://127.0.0.1:4444
```

Use a separate Access application/policy for the Admin UI/API. Do not publish the Admin UI without Cloudflare Access. Do not put Tunnel credentials or Access service tokens in this repository.

The intended routing is:

- public: `/health`, OAuth discovery metadata, and the OAuth-protected MCP route;
- Access protected: `/admin/*` and administrative APIs.

Review actual ContextForge routes and Cloudflare Access policy before deploying; do not assume that an ingress rule alone protects administrative endpoints.

## 4. Create or restore the team Virtual Server

In ContextForge:

1. Create a team with least-privilege membership.
2. Add each intended user as an active local ContextForge user.
3. Assign only the required team role/RBAC.
4. Configure the three upstream MCP servers and their credentials in ContextForge's protected admin interface.
5. Create one team-visible Virtual Server with OAuth enabled.
6. Record the live server ID and retrieve its RFC 9728 protected-resource metadata.

Do not export upstream capability credentials into this repository or provide them to ChatGPT directly.

## 5. Configure Auth0

Follow [oauth-setup.md](oauth-setup.md). Keep the Auth0 API identifier exactly equal to the `resource` returned by ContextForge metadata. Keep the claim URI identical in Auth0 and `MCP_OAUTH_EMAIL_CLAIM`.

## 6. Update or roll back

After changing an overlay:

```bash
docker compose build
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:4444/health
```

Before replacing the running image, preserve a database backup:

```bash
docker compose stop contextforge
docker run --rm -v cos-contextforge-data:/data -v "$PWD":/backup alpine \
  tar -czf /backup/contextforge-data-backup.tgz -C /data .
docker compose up -d
```

The backup contains identity and configuration data. Keep it outside Git and encrypt it at rest. Restore only after confirming the target volume and recovery plan.

## Operational warning

The example uses an external named Docker volume. Removing the volume destroys ContextForge state. Never run `docker compose down -v` as a routine restart command.
