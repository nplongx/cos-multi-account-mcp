# Architecture and trust boundaries

## Request flow

1. Each ChatGPT account creates its own OAuth connection to the same ContextForge Virtual Server.
2. ChatGPT performs OAuth 2.0 Authorization Code with PKCE against Auth0.
3. Auth0 authenticates the user through the configured Google social connection.
4. Auth0 issues a signed access token for the exact MCP resource. The token carries the required MCP scope and a namespaced email claim only when the Google email is verified.
5. ContextForge validates the token, extracts the configured email claim, resolves it to an active local user, and applies team membership and RBAC.
6. The team-visible Virtual Server dispatches to the configured COS Core, Desktop, and Plugins upstreams.
7. The Virtual Server may also dispatch to the loopback-only COS Control Broker through a direct-proxy Gateway. ContextForge forwards its authenticated user identity with an HMAC signature.
8. The broker verifies that signature and maps opaque broker agent IDs to COS session IDs in a private SQLite registry. Every query is filtered by the verified owner ID. COS's instance-wide token remains inside the broker.
9. Cross-account A2A messages use a second set of tables in the same persistent broker database. Endpoints are bound to the signed owner identity. The authenticated tenant-wide directory publishes only active endpoint IDs, owner-asserted labels, state, and pseudonymous owner fingerprints; it never publishes owner IDs, emails, credentials, or COS sessions. Recipient-owned peer ACLs authorize exact sender endpoint IDs, so two Workstreams sharing one ContextForge identity remain isolated. Legacy fingerprint ACLs remain supported only for endpoints that have not configured exact peer ACL mode.

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
- The broker listens only on `127.0.0.1:4445`; the COS Control API remains on `127.0.0.1:37121`.
- The broker token is mounted read-only from the host. It is never propagated to ContextForge users or returned by a tool.
- The broker trusts only the signed `X-Forwarded-User-Id` + `X-Forwarded-User-Email` pair. Unsigned team/admin headers are ignored.
- The broker maintains an explicit owner registry. Users cannot enumerate, address, or message sessions that were not registered under their verified identity.

## Broker identity and account boundary

`IDENTITY_PROPAGATION_ENABLED=true` and `IDENTITY_SIGN_CLAIMS=true` are required. `IDENTITY_CLAIMS_SECRET` must be an independent high-entropy secret shared only by ContextForge and the broker. The broker verifies the HMAC-SHA256 signature over `user_id:email` and requires the current ContextForge mapping where user ID equals verified email. Do not enable unsigned identity forwarding.

The tools `agent_register`, `agent_list`, `agent_send_message`, `agent_read_messages`, and `agent_get_status` operate only on the caller's broker-owned records. A newly registered agent opens a new chat through the active local COS runtime. All such chats therefore use the ChatGPT account signed in to that COS runtime; this is not account-per-user credential delegation.

`get_identity` returns an HMAC-SHA256 pseudonym derived from the verified ContextForge `owner_id`, plus the number of broker registry records owned by that identity. The fingerprint is stable across sessions that resolve to the same ContextForge user and share the same broker identity secret. It deliberately does not return email, `owner_id`, OAuth claims, or credentials. Equal fingerprints mean equal ContextForge owner identity in this broker identity domain; they do **not** prove that two ChatGPT tabs belong to the same ChatGPT account. Different ChatGPT accounts that authenticate as the same upstream Google/ContextForge user are indistinguishable to this tool. The count includes all owned registry records, including records whose state is `closed`.

## A2A mailbox contract

- `a2a_endpoint_register` creates an owner-bound endpoint. Endpoints are private by default.
- `a2a_directory_list` returns active routing records across the authenticated broker deployment. The existing `a2a_endpoint_list` also returns `peer_directory` for backwards compatibility with already-installed ChatGPT tool catalogs, while retaining caller-owned endpoints under `endpoints`. The directory exposes endpoint IDs, owner-asserted labels, state, pseudonymous owner fingerprints, and broker-scoped `sender_acl_token` values only. It does not reveal owner IDs, email addresses, credentials, or COS sessions. Labels are claims made by endpoint owners, not externally attested Workstream identities.
- `a2a_endpoint_set_peer_acl` can only modify an endpoint owned by the caller and allowlists exact active sender endpoint IDs. This is the required mode for Workstream-to-Workstream isolation, including multiple Workstreams under one ContextForge identity. An empty list explicitly denies all senders and overrides any legacy fingerprint allowlist. Revoked queued/received messages are expired.
- `a2a_endpoint_set_acl` remains backwards-compatible with the old 64-hex input schema. Passing `sender_acl_token` values from `peer_directory` through its existing `allowed_sender_fingerprints` field configures exact sender endpoint ACL mode. Passing real owner fingerprints retains legacy identity-level behavior only before exact mode is enabled. An empty list switches to exact deny-all mode. Once exact peer ACL mode is configured, the legacy setter refuses to downgrade the endpoint to broader identity-level permissions.
- `a2a_send_message` requires a sender endpoint owned by the caller, an active recipient endpoint, recipient ACL approval, a correlation ID, an idempotency key and a bounded TTL. Exact endpoint ACL mode checks the sender endpoint ID; legacy endpoints check the verified sender fingerprint. SQLite commits the message before the tool reports durable queue acceptance.
- `a2a_inbox_read` can only read an endpoint owned by the caller. It marks queued messages as received and provides monotonic sequence cursors. `a2a_message_ack` can only acknowledge messages addressed to that endpoint.
- `a2a_message_reply` requires that the original message was addressed to the caller's endpoint. It sends to the original sender endpoint, checks the sender endpoint's reciprocal ACL, preserves correlation ID, and atomically acknowledges the original message.
- Message bodies and internal owner IDs are not exposed outside the sender/recipient tool results. Untrusted caller-supplied sender identity fields are never accepted; sender fingerprint comes from the verified ContextForge request.
- Mailbox reads are pull-based. This version does not auto-wake ChatGPT tabs, proxy content into a different account's conversation, or make COS Control API sessions cross-owner addressable.
- Legacy endpoint ACL fingerprints are scoped to this broker's HMAC secret. Rotating that secret changes fingerprints; legacy peer ACLs must be repopulated after coordinated rotation. Exact endpoint ACLs use durable endpoint IDs and are not affected by HMAC fingerprint rotation.

Quick Tunnels are useful for temporary testing but do not provide the stable hostname and lifecycle expected for an ongoing deployment.
