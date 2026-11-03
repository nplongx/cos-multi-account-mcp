# Security Policy

## Scope

This repository contains a ContextForge deployment overlay and operator documentation. It is not a credential repository.

## Never publish

Do not commit or paste into GitHub, Gists, issues, or logs:

- `.env`, database files, backups, or production configuration dumps;
- JWT signing secrets, encryption keys, bootstrap passwords, or Basic Auth passwords;
- Auth0 client secrets, Google OAuth client secrets, Cloudflare Tunnel tokens, or Cloudflare Access service tokens;
- access tokens, refresh tokens, authorization codes, cookies, browser profile data, or upstream COS capability credentials;
- personal identity records or user lists that are not required for a public runbook.

Use `.env.example` only as a placeholder template. Keep the real `.env` file readable only by the deployment operator (`chmod 600 .env`).

## Deployment protections

- Bind ContextForge to `127.0.0.1`; do not expose port 4444 directly.
- Publish the MCP route only through the intended Cloudflare Tunnel.
- Protect Admin UI/API paths with Cloudflare Access.
- Keep the MCP endpoint protected by OAuth. An unauthenticated MCP request must fail closed.
- Validate token signature, issuer, exact resource audience, expiry, scope, and verified email identity.
- Resolve the email claim to an active local user and enforce team membership/RBAC on every request.
- Do not share OAuth credentials between ChatGPT accounts.

## Reporting

For a suspected vulnerability, avoid posting exploit details or credentials in a public issue. Contact the repository owner privately and include affected commit, impact, and safe reproduction steps. Revoke and rotate any credential that may have been exposed.
