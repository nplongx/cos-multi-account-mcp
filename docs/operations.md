# Operations

## Health and discovery

```bash
curl -fsS http://127.0.0.1:4444/health
```

The protected-resource metadata path is:

```text
https://<your-hostname>/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

Confirm that its `resource`, `authorization_servers`, and `scopes_supported` values match the live Auth0 API configuration.

## Service lifecycle

```bash
docker compose ps
docker compose logs --tail=100 contextforge
docker compose restart contextforge
docker compose up -d
```

Avoid `docker compose down -v`; the external volume contains the ContextForge database.

## Authentication checks

- unauthenticated MCP POST should return HTTP 401 and an OAuth metadata challenge;
- valid OAuth metadata may be public;
- Admin UI/API requests must be protected by Cloudflare Access;
- successful health or metadata checks do not prove token validation, identity mapping, or RBAC.

## Database backup

Stop or quiesce the gateway before taking a filesystem-level SQLite backup. Store backups outside the repository, encrypt them, restrict access, and test restore procedures. Database files may contain users, team membership, server configuration, and encrypted upstream credentials.

## Logs and diagnostics

Inspect logs locally:

```bash
docker compose logs --tail=200 contextforge
```

Redact Authorization headers, cookies, bearer tokens, OAuth codes, passwords, client secrets, and personal identity data before sharing logs. Do not paste raw database rows or Auth0 event payloads into public issues.

## Incident response

If a credential is exposed:

1. Revoke or rotate the affected credential at its issuer.
2. Rotate related application secrets if token-signing or encryption keys may be exposed.
3. Review Auth0 and Cloudflare audit logs.
4. Re-issue affected user connections.
5. Check the Git history and revoke leaked tokens even if the file was later removed.
