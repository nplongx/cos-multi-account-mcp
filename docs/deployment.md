# Deployment

> Language: English | [Tiếng Việt](deployment.vi.md)

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

Generate one more independent value for `COS_IDENTITY_HMAC_SECRET` (at least 32 random bytes). Create a broker-readable copy of the COS Control API token at `/home/<user>/.config/chat-on-steroids/control-api/broker-token`, owned by the host operator and group `10001`, mode `0640`. Keep the original `token` at mode `0600`. Set `COS_CONTROL_API_TOKEN_HOST_PATH` to the absolute path of `broker-token`. Do not copy the token into `.env`.

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
docker compose logs --tail=100 cos-control-broker
curl -fsS http://127.0.0.1:4444/health
curl -fsS http://127.0.0.1:4445/healthz
```

The Compose file uses host networking and binds the service to `127.0.0.1:4444`. Do not change this to `0.0.0.0` unless you have deliberately designed and reviewed a different network boundary.

The broker runs as UID/GID `10001:10001`, binds to `127.0.0.1:4445`, mounts the dedicated broker token copy read-only, and verifies signed ContextForge identity headers. The Control API itself must be enabled with `controlApi.enabled=true` and `controlApi.allowActions=true` in COS. The compose broker fails closed when token, HMAC secret, or Control API health is unavailable. After rotating the COS token, recreate the `broker-token` copy and restart `cos-control-broker`.

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
5. Create a Gateway named `cos-control-broker` with URL `http://127.0.0.1:4445/mcp` and Gateway mode `direct_proxy`. Global identity propagation is enabled by Compose; do not disable signed identity claims for this Gateway.
6. Attach that Gateway to the intended team Virtual Server, then grant only the intended team members the required `tools.read` and `tools.execute` permissions.
7. Create one team-visible Virtual Server with OAuth enabled.
8. Record the live server ID and retrieve its RFC 9728 protected-resource metadata.

Do not export upstream capability credentials into this repository or provide them to ChatGPT directly.

The broker exposes owner-scoped `agent_*` tools plus `a2a_*` mailbox tools. Agent registration creates isolated conversations under the ChatGPT account currently active in COS; it does not log in to or borrow the separate ChatGPT account credentials of each ContextForge user. A2A endpoints are separate mailbox identities bound to authenticated ContextForge users. Their messages are pulled by the recipient and do not automatically wake a ChatGPT tab.

## Refresh the Gateway catalog after broker tool changes

This deployment keeps ContextForge's global `auto_refresh_servers` setting disabled. Do not enable it just to refresh this broker: it applies to every configured Gateway. After adding or changing broker MCP tools, refresh only `cos-control-broker`:

1. Open ContextForge Admin -> Gateways -> `cos-control-broker` -> Refresh tools.
2. Open the `COS Multi-Account` Virtual Server and attach the newly imported broker tools to its tool associations. A Gateway refresh alone does not prove that the Virtual Server exposes those tools.
3. In each ChatGPT account profile, open Settings -> Plugins -> `COS Multi-Account` -> Refresh tools.
4. Start a new conversation in each profile and verify the expected broker tool names are present before running cross-account A2A tests.

For the A2A mailbox implementation, the ten tool names are `a2a_endpoint_register`, `a2a_endpoint_delete` (owner-scoped soft retirement with exact-label confirmation and message-history retention), `a2a_endpoint_set_acl` (legacy fingerprint or endpoint-token compatibility), `a2a_endpoint_set_peer_acl` (exact sender endpoint ACL), `a2a_endpoint_list` (owned endpoints plus deployment-wide `peer_directory`), `a2a_directory_list` (authenticated deployment-wide directory), `a2a_send_message`, `a2a_inbox_read`, `a2a_message_ack`, and `a2a_message_reply`. The broker active-endpoint quota counts only `state='active'` rows; retired `disabled` rows remain available to owner history views but are omitted from active routing directories. Existing ChatGPT sessions can use `peer_directory` through the unchanged `a2a_endpoint_list` schema and configure exact endpoint ACLs through the unchanged `a2a_endpoint_set_acl` schema. New sessions can use the more explicit directory and endpoint ACL tools.

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
