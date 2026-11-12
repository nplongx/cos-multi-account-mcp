# Verification and acceptance

> Language: English | [Tiếng Việt](verification.vi.md)

## Safe baseline checks

Run from the deployment host:

```bash
curl -i http://127.0.0.1:4444/health
curl -i http://127.0.0.1:4445/healthz
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

## COS Control Broker checks

- [ ] `cos-control-broker` is healthy and listens only on `127.0.0.1:4445`.
- [ ] Broker can authenticate to COS `/v1/health`; action routes are enabled.
- [ ] Missing or invalid `X-Forwarded-User-Claims-Signature` causes tool listing to return no tools and tool invocation to fail.
- [ ] A valid ContextForge identity can call `agent_register` and receives an opaque broker `agent_id`.
- [ ] `agent_list`, `agent_get_status`, `agent_read_messages`, and `agent_send_message` work for the owner.
- [ ] `get_identity` returns a stable HMAC-SHA256 fingerprint and owner-scoped agent count without returning email, user ID, OAuth claims, or credentials.
- [ ] Separate OAuth sessions resolving to the same ContextForge user return the same fingerprint; distinct ContextForge users return different fingerprints.
- [ ] Interpret matching fingerprints as the same ContextForge identity only; this does not prove the same ChatGPT account when multiple accounts use the same upstream Google identity.
- [ ] A second user cannot list, read, send to, or inspect the first user's `agent_id`.
- [ ] Unsigned or caller-supplied admin/team headers do not grant access.
- [ ] The host COS token file is mounted read-only; it is absent from tool results and broker logs.
- [ ] Broker registry survives container recreation through `cos-agent-broker-data`.
- [ ] Confirm the active local COS ChatGPT profile is the intended runtime account; broker-created chats use that account and quota.

## A2A mailbox checks

- [x] Recorded WS1/WS3 live pilot completed on 2026-11-03; see [a2a-pilot-2026-11-03.md](a2a-pilot-2026-11-03.md).
- [x] `cos-control-broker` Gateway refresh imported seven A2A tools; the `COS Multi-Account` Virtual Server now has 35 tools, preserving the previous 28.
- [x] New ChatGPT conversations in all four account profiles successfully called `a2a_endpoint_list` under distinct ContextForge identities.
- [x] WS1 and WS3 endpoints were registered by their respective identities, private by default, and configured with reciprocal exact-fingerprint ACLs.
- [x] Live WS1 -> WS3 -> WS1 message flow completed with the same correlation ID; receiver read, reply, and both ACK states were verified in SQLite.
- [x] Broker container restart preserved both endpoints, both ACL entries, and both acknowledged messages; health returned HTTP 200.
- [x] Unit/security suite: 23/23 passed; `py_compile`, `git diff --check`, and `docker compose config -q` passed.
- [ ] After broker tool changes, refresh the `cos-control-broker` Gateway catalog, explicitly attach new tools to the `COS Multi-Account` Virtual Server, and refresh Settings -> Plugins separately in each ChatGPT account profile.
- [ ] Verify all seven `a2a_*` tools individually in a new conversation for each intended account; the live four-profile smoke test invoked `a2a_endpoint_list` only.
- [ ] Each Workstream endpoint is registered from its own authenticated ContextForge identity; record only endpoint IDs and public identity fingerprints in the coordination plan.
- [ ] A newly registered endpoint has an empty sender ACL and rejects all senders.
- [ ] Endpoint owner can add/remove exact sender fingerprints; another identity cannot change the ACL.
- [ ] Sender can enqueue only from its own endpoint and only to a recipient endpoint that allowlists the sender fingerprint.
- [ ] A second identity cannot read or ACK a message addressed to the first identity's endpoint.
- [ ] Message enqueue is durable across broker restart and idempotent for a repeated sender endpoint + idempotency key.
- [ ] Inbox read marks messages received; ACK marks them complete; reply routes to original sender, preserves correlation ID and ACKs original atomically.
- [ ] Expired messages are not delivered; endpoint and pending-inbox quotas reject excess work.
- [ ] Confirm no A2A operation accesses another owner's COS session or claims automatic ChatGPT tab wake. Pull-based polling is the current delivery contract.

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

## Local A2A implementation status — 2026-11-03

| Check | Result |
| --- | --- |
| Broker source compile and `git diff --check` | PASS |
| Broker unit/security tests | PASS, 21/21 |
| Docker image build | PASS |
| `cos-control-broker` runtime | PASS, version `0.3.0`, healthy on `127.0.0.1:4445` |
| Direct broker MCP `tools/list` | PASS, 13 tools including all 7 `a2a_*` tools |
| Production SQLite schema | PASS, `a2a_endpoints`, `a2a_endpoint_acl`, `a2a_messages` created |
| Existing broker agent registry | Preserved, 2 records before/after deployment |
| A2A production endpoints/messages | Not provisioned yet, 0 endpoints and 0 messages |
| ContextForge Gateway / Virtual Server catalog refresh | BLOCKED, local Admin session expired; broker tool list is current but the Gateway cache remains stale |
| Two-account live A2A round-trip | NOT PROVEN; requires catalog refresh and endpoint provisioning |

The broker's A2A mailbox is pull-based. This deployment does not claim automatic ChatGPT tab wake or cross-owner COS session access. After an administrator signs into the local ContextForge Admin UI, refresh the `cos-control-broker` Gateway tools, refresh the `COS Multi-Account` Virtual Server associations, and refresh the ChatGPT connector actions in each account before registering Workstream endpoints.
