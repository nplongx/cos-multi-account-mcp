# Eight-Workstream A2A bootstrap — 2026-11-03

> Language: English | [Tiếng Việt](a2a-workstream-bootstrap-2026-11-03.vi.md)

## Broker changes

The broker now exposes two additional tools:

- `a2a_directory_list`: active endpoint directory for the authenticated COS broker deployment.
- `a2a_endpoint_set_peer_acl`: recipient-owned allowlist of exact sender endpoint IDs.

`a2a_endpoint_list` remains owner-scoped for `endpoints`, and now also returns deployment-wide `peer_directory` for compatibility with already-open ChatGPT sessions. Directory entries contain endpoint IDs, owner-asserted labels, active state, HMAC owner fingerprints, and broker-scoped `sender_acl_token` values. They never publish ContextForge owner IDs, email addresses, credentials, or COS sessions. Labels are self-asserted; the broker does not independently prove that a label is a particular Workstream.

Exact endpoint ACLs solve the four-profile/two-Workstream identity collision. A recipient configured in endpoint mode accepts only listed sender endpoint IDs, even when an unlisted sender endpoint has the same ContextForge fingerprint. An explicitly empty endpoint allowlist denies all senders and overrides any legacy fingerprint allowlist. Legacy endpoints without endpoint-mode configuration retain old fingerprint ACL behavior until their owners migrate them.

The existing `a2a_endpoint_set_acl` input schema remains usable: pass `sender_acl_token` values from `peer_directory` in its existing `allowed_sender_fingerprints` array to activate exact endpoint mode. Passing true owner fingerprints retains legacy identity-level behavior only before an endpoint is migrated. Empty array activates exact deny-all mode. New tool catalogs can instead use `a2a_directory_list` and `a2a_endpoint_set_peer_acl` directly.

## Existing endpoint inventory

The production broker SQLite database contained eight active endpoints before the broker upgrade:

| Workstream | Endpoint ID | ContextForge owner fingerprint |
|---|---|---|
| WS1 | `fe692d74-c735-417f-8252-359e17453b22` | `491c059becfa27835614189cef1e11c575a6ec06ef5fc2a73943b1cde6f500ad` |
| WS2 | `437be3a9-103a-4a76-b214-a5925207df30` | `491c059becfa27835614189cef1e11c575a6ec06ef5fc2a73943b1cde6f500ad` |
| WS3 | `ea54914b-66e9-41ed-b051-ad315bacd6fd` | `334d233225177519736248d47f55d3d7dc0d7a188fc706cddf32c79756205957` |
| WS4 | `05ac6126-0e9a-4e95-9808-95172af91f2b` | `334d233225177519736248d47f55d3d7dc0d7a188fc706cddf32c79756205957` |
| WS5 | `7860fbee-58d9-483e-a0d5-df34785fbec1` | `9cfc18e6f5568b88d5806d33dd612d8442b68c77f024f033d005be05755527fa` |
| WS6 | `be6f2ea2-e6af-4758-a2c8-d72701d60a85` | `9cfc18e6f5568b88d5806d33dd612d8442b68c77f024f033d005be05755527fa` |
| WS7 | `37d75f7c-7873-4e33-955a-ac49f308eed6` | `0a4feaec030c4cff03d3681b35a089d1ca86f6cda9de0c6435f3fa6f49833171` |
| WS8 | `3ca5589a-b386-4e3c-9e17-c1fc25979e6d` | `0a4feaec030c4cff03d3681b35a089d1ca86f6cda9de0c6435f3fa6f49833171` |

This is an inventory snapshot, not a claim that all eight endpoint owners have configured peer ACLs or completed live round trips. WS1/WS2 share one authenticated identity; WS3/WS4 share another; WS5/WS6 share another; WS7/WS8 share another. Endpoint-specific ACLs are therefore mandatory for Workstream isolation.

## Dependency routing derived from `EIGHT_PART_PARALLEL_PLAN.md`

The plan's contract graph is:

- WS6 -> WS1, WS2, WS7
- WS1 -> WS2, WS7
- WS2 <-> WS3; WS2 -> WS7
- WS3 -> WS4, WS5
- WS4 -> WS5
- WS5 -> WS7
- WS8 develops gateway clients/mocks against WS1–WS7 public contracts; this is not by itself an instruction to allow every pair of endpoints to message.

For a directed producer/consumer edge A -> B, configure B's recipient ACL to allow A's endpoint. Configure the reverse edge only where the owners need independent messages in that direction; replies are returned to the original sender and must also be authorized by that sender endpoint's ACL. Do not use broad fingerprint ACLs as a substitute for this mapping.

## Required operational sequence after deployment

1. Refresh the `cos-control-broker` Gateway and attach the two new tools to the `COS Multi-Account` Virtual Server.
2. In each of the four account profiles, call `a2a_endpoint_list` and read `peer_directory` (or call `a2a_directory_list` in refreshed sessions); compare IDs/labels/fingerprints with this inventory.
3. Each endpoint owner configures `a2a_endpoint_set_acl` with exact `sender_acl_token` values, or uses `a2a_endpoint_set_peer_acl` with exact sender endpoint IDs, based on the dependency graph.
4. Re-read `a2a_endpoint_list` and each owner's own endpoints to verify `acl_mode=endpoint` and exact allowlist counts.
5. Execute live message -> inbox read -> reply -> reply inbox read -> ACK for each required cross-profile edge. Use a unique correlation ID and idempotency key per test.
6. Report directory, ACL setup, and live round-trip as separate acceptance results. A successful directory read or endpoint registration is never connectivity PASS.

Mailbox delivery remains pull-based. This change does not wake a different ChatGPT tab automatically.

## Deployment and acceptance result

Broker `0.4.1` is deployed and healthy. The `COS Multi-Account` Virtual Server has 37 associated tools; the two new explicit directory/peer-ACL tools are attached. Already-open ChatGPT sessions continue to work through the backwards-compatible `a2a_endpoint_list` and `a2a_endpoint_set_acl` schemas.

The live directory contains eight active endpoints. Final ACL readback showed exact endpoint mode on all eight and zero legacy fingerprint entries:

| Workstream endpoint | Allowed sender endpoints | Legacy fingerprint entries |
|---|---:|---:|
| WS1 | 3 | 0 |
| WS2 | 4 | 0 |
| WS3 | 4 | 0 |
| WS4 | 3 | 0 |
| WS5 | 4 | 0 |
| `workstream-6-governance-authority` | 4 | 0 |
| WS7 | 5 | 0 |
| WS8 | 7 | 0 |

Live A2A message round-trips were verified:

- WS1 <-> WS2, same authenticated profile but distinct endpoint ACLs. Request `1b81d218-bb0e-423c-b2e9-239ede2a4ff3`; reply `8de3f4e0-183f-4d86-b105-8f056826bfcb`; reply ACK verified.
- WS3 <-> WS2, cross-profile. Correlation `COS-A2A-WS3-WS2-RECOVERY-20261103-01`; request `12628258-dc4f-4c82-884e-9301c5070968`; reply `ed5d9457-6cac-4295-aeb0-ed93d7b310e3`; reply ACK verified.
- WS4 <-> WS5, cross-profile. Correlation `COS-A2A-WS4-WS5-ROUNDTRIP-20261103-01`; request `86a16ec6-5db8-41ce-bfa3-934868194c74`; reply `9d1b2b99-5842-45b7-bb21-8b46b6080cca`; reply ACK verified. Broker message state for the reply is `acked`.

The A2A broker test suite passed `30/30` in the runtime container. `py_compile`, `git diff --check`, and `docker compose config -q` passed. Runtime reports broker version `0.4.1`, healthy container, and both new tool definitions present. Existing SQLite endpoint and message records were retained across deployment; a pre-deployment DB backup is stored under `/home/long/backups/cos-a2a-20261103-160228/`.

Acceptance distinction: peer discovery, endpoint-specific ACL isolation, and the tested round-trips are VERIFIED. Automatic wake-up of idle ChatGPT tabs is NOT IMPLEMENTED; agents must poll their inbox or rely on an external scheduler/worker to wake them. Do not mark untested dependency edges as live-tested merely because their ACL entries exist.
