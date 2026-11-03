# Architecture and trust boundaries

## Request flow

1. Each ChatGPT account creates its own OAuth connection to the same ContextForge Virtual Server.
2. ChatGPT performs OAuth 2.0 Authorization Code with PKCE against Auth0.
3. Auth0 authenticates the user through the configured Google social connection.
4. Auth0 issues a signed access token for the exact MCP resource. The token carries the required MCP scope and a namespaced email claim only when the Google email is verified.
5. ContextForge validates the token, extracts the configured email claim, resolves it to an active local user, and applies team membership and RBAC.
6. The team-visible Virtual Server dispatches to the configured COS Core, Desktop, and Plugins upstreams.

## Identity model

There are three separate identities:

- **ChatGPT account:** owns one connector authorization and its OAuth credential set.
- **Auth0 social identity:** identifies the user authenticated by Google. A social identity may be created on first successful authorization.
- **ContextForge local user:** must already exist, be active, and belong to the team that owns the Virtual Server.

Matching email alone must not bypass the active-user, team-membership, visibility, or RBAC checks.

## Token contract

The implementation expects:

- a valid signature from the configured issuer;
- the exact resource audience advertised by protected-resource metadata;
- a non-expired token;
- the required `mcp:connect` scope;
- a verified email emitted under the configured `MCP_OAUTH_EMAIL_CLAIM` claim name.

The Auth0 Post-Login Action and the ContextForge setting must use the same claim URI. Use a URI under a domain controlled by the deployment owner; the example value in `.env.example` is not a production value.

## Protected-resource discovery

The overlay exposes RFC 9728 metadata for OAuth-enabled team Virtual Servers at:

```text
/.well-known/oauth-protected-resource/servers/<server-id>/mcp
```

The returned `resource` value is the canonical OAuth audience. Copy it exactly into the Auth0 API identifier and ChatGPT connection configuration. Do not reconstruct it from memory or reuse an identifier from an older deployment.

Public metadata discovery does not make the MCP endpoint public. Unauthenticated MCP requests must still receive an OAuth challenge.

## Network boundary

- ContextForge binds to loopback only.
- Cloudflare Named Tunnel publishes the intended MCP hostname to the loopback origin.
- Cloudflare Access protects the Admin UI/API.
- The Docker database volume and all upstream credentials remain on the host.

Quick Tunnels are useful for temporary testing but do not provide the stable hostname and lifecycle expected for an ongoing deployment.
