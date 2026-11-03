"""Security tests for the COS Control API broker."""

import asyncio
import hashlib
import hmac
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from starlette.requests import Request

import cos_control_broker as broker


class IdentityVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_secret = broker.IDENTITY_SECRET
        self.original_prefix = broker.IDENTITY_PREFIX
        broker.IDENTITY_SECRET = "test-secret-value-that-is-at-least-32-bytes"
        broker.IDENTITY_PREFIX = "X-Forwarded-User"

    def tearDown(self) -> None:
        broker.IDENTITY_SECRET = self.original_secret
        broker.IDENTITY_PREFIX = self.original_prefix

    def _request(self, *, signature: str | None = None, admin: str = "true") -> Request:
        user_id = "alice@example.test"
        email = "alice@example.test"
        if signature is None:
            signature = hmac.new(
                broker.IDENTITY_SECRET.encode(),
                f"{user_id}:{email}".encode(),
                hashlib.sha256,
            ).hexdigest()
        headers = [
            (b"x-forwarded-user-id", user_id.encode()),
            (b"x-forwarded-user-email", email.encode()),
            (b"x-forwarded-user-claims-signature", signature.encode()),
            (b"x-forwarded-user-admin", admin.encode()),
            (b"x-forwarded-user-teams", b"attacker-controlled-team"),
        ]
        return Request({"type": "http", "method": "POST", "path": "/mcp", "headers": headers})

    def test_accepts_valid_signed_identity(self) -> None:
        identity = broker._identity_from_request(self._request())
        self.assertEqual(identity, {"owner_id": "alice@example.test", "email": "alice@example.test"})

    def test_rejects_invalid_signature(self) -> None:
        with self.assertRaises(PermissionError):
            broker._identity_from_request(self._request(signature="0" * 64))

    def test_rejects_missing_request_context(self) -> None:
        with self.assertRaises(PermissionError):
            broker._identity_from_request(None)

    def test_rejects_user_id_email_mismatch(self) -> None:
        request = self._request()
        request.scope["headers"] = [
            (b"x-forwarded-user-id", b"other-user"),
            (b"x-forwarded-user-email", b"alice@example.test"),
            (b"x-forwarded-user-claims-signature", hmac.new(
                broker.IDENTITY_SECRET.encode(), b"other-user:alice@example.test", hashlib.sha256
            ).hexdigest().encode()),
        ]
        with self.assertRaises(PermissionError):
            broker._identity_from_request(request)


class ToolDiscoveryTests(unittest.TestCase):
    def test_static_schemas_are_discoverable_without_identity(self) -> None:
        class AnonymousContext:
            request = None

        result = asyncio.run(broker._list_tools(AnonymousContext(), None))
        self.assertEqual(
            {tool.name for tool in result.tools},
            {
                "get_identity",
                "agent_register",
                "agent_list",
                "agent_send_message",
                "agent_read_messages",
                "agent_get_status",
                "a2a_endpoint_register",
                "a2a_endpoint_set_acl",
                "a2a_endpoint_set_peer_acl",
                "a2a_endpoint_list",
                "a2a_directory_list",
                "a2a_send_message",
                "a2a_inbox_read",
                "a2a_message_ack",
                "a2a_message_reply",
            },
        )


class IdentityFingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = broker.DB_PATH
        self.original_secret = broker.IDENTITY_SECRET
        broker.DB_PATH = Path(self.tmp.name) / "broker.sqlite3"
        broker.IDENTITY_SECRET = "test-secret-value-that-is-at-least-32-bytes"
        broker._init_db()

    def tearDown(self) -> None:
        broker.DB_PATH = self.original_db_path
        broker.IDENTITY_SECRET = self.original_secret
        self.tmp.cleanup()

    def test_fingerprint_is_stable_for_same_contextforge_identity(self) -> None:
        first = broker._identity_fingerprint({"owner_id": "alice@example.test"})
        second = broker._identity_fingerprint({"owner_id": "ALICE@example.test"})
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_fingerprint_differs_between_contextforge_users(self) -> None:
        alice = broker._identity_fingerprint({"owner_id": "alice@example.test"})
        bob = broker._identity_fingerprint({"owner_id": "bob@example.test"})
        self.assertNotEqual(alice, bob)

    def test_identity_info_returns_only_fingerprint_metadata_and_owned_count(self) -> None:
        now = int(time.time())
        with sqlite3.connect(broker.DB_PATH) as db:
            db.executemany(
                "INSERT INTO agents (agent_id, owner_id, owner_email, label, input_id, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("alice-1", "alice@example.test", "alice@example.test", "A1", "i1", "pending", now, now),
                    ("alice-2", "alice@example.test", "alice@example.test", "A2", "i2", "closed", now, now),
                    ("bob-1", "bob@example.test", "bob@example.test", "B1", "i3", "active", now, now),
                ],
            )

        result = broker._get_identity_info({"owner_id": "alice@example.test"})
        self.assertEqual(result["identity_type"], "contextforge_user")
        self.assertEqual(result["fingerprint_algorithm"], "HMAC-SHA256")
        self.assertEqual(result["fingerprint_version"], "v1")
        self.assertEqual(result["owned_agent_count"], 2)
        self.assertNotIn("email", result)
        self.assertNotIn("owner_id", result)
        self.assertNotIn("alice@example.test", str(result))
        self.assertNotIn(broker.IDENTITY_SECRET, str(result))

        bob_result = broker._get_identity_info({"owner_id": "bob@example.test"})
        self.assertEqual(bob_result["owned_agent_count"], 1)
        self.assertNotEqual(result["identity_fingerprint"], bob_result["identity_fingerprint"])

    def test_missing_owner_id_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            broker._identity_fingerprint({})

    def test_get_identity_tool_dispatch_requires_signed_request_identity(self) -> None:
        user_id = "alice@example.test"
        signature = hmac.new(
            broker.IDENTITY_SECRET.encode("utf-8"),
            f"{user_id}:{user_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [
                    (b"x-forwarded-user-id", user_id.encode()),
                    (b"x-forwarded-user-email", user_id.encode()),
                    (b"x-forwarded-user-claims-signature", signature.encode()),
                ],
            }
        )

        class AuthenticatedContext:
            pass

        context = AuthenticatedContext()
        context.request = request
        params = broker.types.CallToolRequestParams(name="get_identity", arguments={})
        result = asyncio.run(broker._call_tool(context, params))

        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["identity_type"], "contextforge_user")
        self.assertEqual(result.structured_content["owned_agent_count"], 0)


class AgentOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = broker.DB_PATH
        broker.DB_PATH = Path(self.tmp.name) / "broker.sqlite3"
        broker._init_db()
        now = int(time.time())
        with sqlite3.connect(broker.DB_PATH) as db:
            db.execute(
                "INSERT INTO agents (agent_id, owner_id, owner_email, label, input_id, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("agent-owned-by-alice", "alice@example.test", "alice@example.test", "Alice agent", "input-1", "pending", now, now),
            )

    def tearDown(self) -> None:
        broker.DB_PATH = self.original_db_path
        self.tmp.cleanup()

    def test_owner_can_resolve_agent(self) -> None:
        row = broker._owned_agent("agent-owned-by-alice", {"owner_id": "alice@example.test"})
        self.assertEqual(row["label"], "Alice agent")

    def test_other_user_cannot_resolve_agent(self) -> None:
        with self.assertRaises(PermissionError):
            broker._owned_agent("agent-owned-by-alice", {"owner_id": "bob@example.test"})


class A2AMailboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = broker.DB_PATH
        self.original_secret = broker.IDENTITY_SECRET
        self.original_max_pending = broker.A2A_MAX_PENDING_PER_ENDPOINT
        broker.DB_PATH = Path(self.tmp.name) / "broker.sqlite3"
        broker.IDENTITY_SECRET = "test-secret-value-that-is-at-least-32-bytes"
        broker.A2A_MAX_PENDING_PER_ENDPOINT = 100
        self.alice = {"owner_id": "alice@example.test", "email": "alice@example.test"}
        self.bob = {"owner_id": "bob@example.test", "email": "bob@example.test"}
        self.alice_fp = broker._identity_fingerprint(self.alice)
        self.bob_fp = broker._identity_fingerprint(self.bob)
        broker._init_db()
        self.alice_ep = broker._a2a_register_endpoint(self.alice, "WS1")["endpoint_id"]
        self.alice_second_ep = broker._a2a_register_endpoint(self.alice, "WS2")["endpoint_id"]
        self.bob_ep = broker._a2a_register_endpoint(self.bob, "WS3")["endpoint_id"]

    def tearDown(self) -> None:
        broker.DB_PATH = self.original_db_path
        broker.IDENTITY_SECRET = self.original_secret
        broker.A2A_MAX_PENDING_PER_ENDPOINT = self.original_max_pending
        self.tmp.cleanup()

    def _send(self, *, key: str = "pilot-001", message: str = "hello") -> dict:
        return broker._a2a_send_message(
            self.alice,
            self.alice_ep,
            self.bob_ep,
            "pilot-correlation-001",
            key,
            message,
            3600,
        )

    def test_endpoint_is_private_until_owner_adds_sender_fingerprint(self) -> None:
        with self.assertRaises(PermissionError):
            self._send()

        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        result = self._send()
        self.assertEqual(result["state"], "queued")
        self.assertTrue(result["durable"])

    def test_directory_lists_active_endpoints_across_owners_without_private_identity_data(self) -> None:
        result = broker._a2a_directory_list(self.alice)
        by_id = {entry["endpoint_id"]: entry for entry in result["endpoints"]}
        self.assertEqual(result["directory_scope"], "authenticated_cos_broker_tenant")
        self.assertEqual(result["total"], 3)
        self.assertEqual(by_id[self.alice_ep]["label"], "WS1")
        self.assertEqual(by_id[self.alice_second_ep]["identity_fingerprint"], self.alice_fp)
        self.assertEqual(by_id[self.bob_ep]["identity_fingerprint"], self.bob_fp)
        self.assertNotIn("owner_id", str(result))
        self.assertNotIn("email", str(result))
        self.assertNotIn("alice@example.test", str(result))
        self.assertNotIn("bob@example.test", str(result))
        self.assertEqual(by_id[self.alice_ep]["sender_acl_token"], broker._a2a_sender_acl_token(self.alice_ep))
        self.assertNotEqual(by_id[self.alice_ep]["sender_acl_token"], by_id[self.alice_second_ep]["sender_acl_token"])

    def test_legacy_list_exposes_peer_directory_without_changing_owned_endpoint_scope(self) -> None:
        result = broker._a2a_list_endpoints(self.alice)
        self.assertEqual({item["endpoint_id"] for item in result["endpoints"]}, {self.alice_ep, self.alice_second_ep})
        self.assertEqual(result["peer_directory_total"], 3)
        peer_ids = {item["endpoint_id"] for item in result["peer_directory"]}
        self.assertEqual(peer_ids, {self.alice_ep, self.alice_second_ep, self.bob_ep})
        self.assertTrue(all("sender_acl_token" in item for item in result["peer_directory"]))

    def test_legacy_acl_tool_accepts_peer_directory_tokens_as_exact_sender_endpoints(self) -> None:
        ws1_token = broker._a2a_sender_acl_token(self.alice_ep)
        result = broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [ws1_token])
        self.assertEqual(result["acl_mode"], "endpoint")
        self.assertEqual(result["allowed_sender_count"], 1)

        allowed = broker._a2a_send_message(
            self.alice, self.alice_ep, self.bob_ep,
            "legacy-schema-exact-1", "legacy-schema-key-1", "from WS1", 3600,
        )
        self.assertEqual(allowed["state"], "queued")
        with self.assertRaises(PermissionError):
            broker._a2a_send_message(
                self.alice, self.alice_second_ep, self.bob_ep,
                "legacy-schema-exact-2", "legacy-schema-key-2", "from WS2", 3600,
            )

        with self.assertRaises(ValueError):
            broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])

    def test_legacy_empty_acl_switches_to_exact_deny_all(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        summary = broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [])
        self.assertEqual(summary["acl_mode"], "endpoint")
        self.assertEqual(summary["allowed_sender_count"], 0)
        with self.assertRaises(PermissionError):
            self._send()

    def test_exact_endpoint_acl_distinguishes_workstreams_sharing_one_identity(self) -> None:
        broker._a2a_endpoint_peer_acl_set(self.bob, self.bob_ep, [self.alice_ep])
        allowed = broker._a2a_send_message(
            self.alice,
            self.alice_ep,
            self.bob_ep,
            "peer-correlation-1",
            "peer-key-1",
            "from WS1",
            3600,
        )
        self.assertEqual(allowed["state"], "queued")

        # WS2 has the same verified ContextForge fingerprint as WS1, but its
        # endpoint is not present in the recipient's exact peer allowlist.
        with self.assertRaises(PermissionError):
            broker._a2a_send_message(
                self.alice,
                self.alice_second_ep,
                self.bob_ep,
                "peer-correlation-2",
                "peer-key-2",
                "from WS2",
                3600,
            )

    def test_empty_exact_peer_acl_overrides_legacy_fingerprint_allowlist(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        broker._a2a_endpoint_peer_acl_set(self.bob, self.bob_ep, [])
        with self.assertRaises(PermissionError):
            self._send()
        summary = next(
            item for item in broker._a2a_list_endpoints(self.bob)["endpoints"] if item["endpoint_id"] == self.bob_ep
        )
        self.assertEqual(summary["acl_mode"], "endpoint")
        self.assertEqual(summary["allowed_sender_count"], 0)

    def test_peer_acl_requires_recipient_ownership_and_active_registered_sender_endpoints(self) -> None:
        with self.assertRaises(PermissionError):
            broker._a2a_endpoint_peer_acl_set(self.alice, self.bob_ep, [self.alice_ep])
        with self.assertRaises(ValueError):
            broker._a2a_endpoint_peer_acl_set(self.bob, self.bob_ep, ["00000000-0000-0000-0000-000000000001"])
        with self.assertRaises(ValueError):
            broker._a2a_endpoint_peer_acl_set(self.bob, self.bob_ep, [self.alice_ep, self.alice_ep])

    def test_message_delivery_read_and_ack_are_owner_scoped(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        sent = self._send()
        inbox = broker._a2a_read_inbox(self.bob, self.bob_ep)
        self.assertEqual(len(inbox["events"]), 1)
        self.assertEqual(inbox["events"][0]["message_id"], sent["message_id"])
        self.assertEqual(inbox["events"][0]["sender_fingerprint"], self.alice_fp)
        self.assertEqual(inbox["events"][0]["message"], "hello")

        ack = broker._a2a_ack_message(self.bob, self.bob_ep, sent["message_id"])
        self.assertEqual(ack["state"], "acked")
        self.assertEqual(broker._a2a_read_inbox(self.bob, self.bob_ep)["events"], [])

        with self.assertRaises(PermissionError):
            broker._a2a_read_inbox(self.bob, self.alice_ep)
        with self.assertRaises(PermissionError):
            broker._a2a_ack_message(self.alice, self.alice_ep, sent["message_id"])

    def test_reply_is_routed_to_original_sender_and_acks_original_atomically(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        broker._a2a_set_endpoint_acl(self.alice, self.alice_ep, [self.bob_fp])
        sent = self._send()
        broker._a2a_read_inbox(self.bob, self.bob_ep)

        reply = broker._a2a_reply_message(
            self.bob,
            self.bob_ep,
            sent["message_id"],
            "reply-001",
            "ack from WS3",
            3600,
        )
        self.assertTrue(reply["original_message_acked"])
        self.assertEqual(reply["reply_to_message_id"], sent["message_id"])
        self.assertEqual(reply["correlation_id"], "pilot-correlation-001")

        replay = broker._a2a_reply_message(
            self.bob,
            self.bob_ep,
            sent["message_id"],
            "reply-001",
            "ack from WS3",
            3600,
        )
        self.assertTrue(replay["duplicate"])
        with self.assertRaises(ValueError):
            broker._a2a_reply_message(
                self.bob,
                self.bob_ep,
                sent["message_id"],
                "reply-002",
                "second reply",
                3600,
            )

        alice_inbox = broker._a2a_read_inbox(self.alice, self.alice_ep)
        self.assertEqual(alice_inbox["events"][0]["message"], "ack from WS3")
        self.assertEqual(alice_inbox["events"][0]["reply_to_message_id"], sent["message_id"])
        self.assertEqual(alice_inbox["events"][0]["sender_fingerprint"], self.bob_fp)

    def test_reply_requires_reciprocal_allowlist_and_correct_recipient_endpoint(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        sent = self._send()
        with self.assertRaises(PermissionError):
            broker._a2a_reply_message(self.bob, self.bob_ep, sent["message_id"], "reply-1", "reply")
        with self.assertRaises(PermissionError):
            broker._a2a_reply_message(self.bob, self.alice_ep, sent["message_id"], "reply-2", "spoof")

    def test_idempotency_replay_returns_same_message_and_rejects_changed_payload(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        first = self._send()
        replay = self._send()
        self.assertEqual(replay["message_id"], first["message_id"])
        self.assertTrue(replay["duplicate"])
        with self.assertRaises(ValueError):
            self._send(message="different content")
        inbox = broker._a2a_read_inbox(self.bob, self.bob_ep)
        self.assertEqual(len(inbox["events"]), 1)

    def test_identity_can_only_send_from_its_own_endpoint(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        with self.assertRaises(PermissionError):
            broker._a2a_send_message(
                self.bob,
                self.alice_ep,
                self.bob_ep,
                "spoof-correlation",
                "spoof-1",
                "spoofed",
            )

    def test_read_marks_expired_messages_and_does_not_deliver_them(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        sent = self._send()
        with sqlite3.connect(broker.DB_PATH) as db:
            db.execute("UPDATE a2a_messages SET expires_at = ? WHERE message_id = ?", (int(time.time()) - 1, sent["message_id"]))
        inbox = broker._a2a_read_inbox(self.bob, self.bob_ep)
        self.assertEqual(inbox["events"], [])
        with sqlite3.connect(broker.DB_PATH) as db:
            state = db.execute("SELECT state FROM a2a_messages WHERE message_id = ?", (sent["message_id"],)).fetchone()[0]
        self.assertEqual(state, "expired")

    def test_message_survives_database_reinitialization(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        sent = self._send()
        broker._init_db()
        inbox = broker._a2a_read_inbox(self.bob, self.bob_ep)
        self.assertEqual([event["message_id"] for event in inbox["events"]], [sent["message_id"]])


    def test_adds_reply_column_without_losing_existing_messages(self) -> None:
        temp = tempfile.TemporaryDirectory()
        original_db_path = broker.DB_PATH
        broker.DB_PATH = Path(temp.name) / "legacy-broker.sqlite3"
        try:
            with sqlite3.connect(broker.DB_PATH) as db:
                db.execute(
                    """
                    CREATE TABLE a2a_messages (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT NOT NULL UNIQUE,
                        correlation_id TEXT NOT NULL,
                        sender_endpoint_id TEXT NOT NULL,
                        sender_owner_id TEXT NOT NULL,
                        sender_fingerprint TEXT NOT NULL,
                        recipient_endpoint_id TEXT NOT NULL,
                        body TEXT NOT NULL,
                        state TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        received_at INTEGER,
                        acked_at INTEGER,
                        UNIQUE(sender_endpoint_id, idempotency_key)
                    )
                    """
                )
                db.execute(
                    "INSERT INTO a2a_messages (message_id, correlation_id, sender_endpoint_id, sender_owner_id, sender_fingerprint, recipient_endpoint_id, body, state, idempotency_key, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("legacy-message", "legacy-correlation", "sender-ep", "sender", "a" * 64, "recipient-ep", "preserve me", "queued", "legacy-key", 1, 9999999999),
                )

            broker._init_db()

            with sqlite3.connect(broker.DB_PATH) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(a2a_messages)")}
                preserved = db.execute(
                    "SELECT body, state, reply_to_message_id FROM a2a_messages WHERE message_id = ?",
                    ("legacy-message",),
                ).fetchone()
            self.assertIn("reply_to_message_id", columns)
            self.assertEqual(preserved, ("preserve me", "queued", None))
        finally:
            broker.DB_PATH = original_db_path
            temp.cleanup()

    def test_acl_revocation_expires_pending_messages(self) -> None:
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        sent = self._send()
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [])
        self.assertEqual(broker._a2a_read_inbox(self.bob, self.bob_ep)["events"], [])
        with sqlite3.connect(broker.DB_PATH) as db:
            state = db.execute("SELECT state FROM a2a_messages WHERE message_id = ?", (sent["message_id"],)).fetchone()[0]
        self.assertEqual(state, "expired")

    def test_pending_inbox_quota_is_enforced(self) -> None:
        broker.A2A_MAX_PENDING_PER_ENDPOINT = 1
        broker._a2a_set_endpoint_acl(self.bob, self.bob_ep, [self.alice_fp])
        self._send(key="pilot-quota-1")
        with self.assertRaises(ValueError):
            self._send(key="pilot-quota-2")


if __name__ == "__main__":
    unittest.main()
