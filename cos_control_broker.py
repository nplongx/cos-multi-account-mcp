# -*- coding: utf-8 -*-
"""Per-user MCP broker for the COS Local Control API.

The broker is intentionally a separate, loopback-only MCP server. ContextForge
connects to it using direct-proxy mode and forwards a signed end-user identity.
The COS Control API token never leaves this process.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
import mcp_types as types
from mcp.server.lowlevel import Server
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route


LOGGER = logging.getLogger("cos_control_broker")
BROKER_VERSION = "0.4.1"
CONTROL_API_URL = os.getenv("COS_CONTROL_API_URL", "http://127.0.0.1:37121").rstrip("/")
TOKEN_FILE = Path(os.getenv("COS_CONTROL_API_TOKEN_FILE", "/run/secrets/cos-control-api-token"))
DB_PATH = Path(os.getenv("COS_AGENT_BROKER_DB_PATH", "/data/cos-agent-broker.sqlite3"))
IDENTITY_SECRET = os.getenv("COS_IDENTITY_HMAC_SECRET", "")
IDENTITY_PREFIX = os.getenv("COS_IDENTITY_HEADER_PREFIX", "X-Forwarded-User").strip()
MAX_AGENTS_PER_USER = int(os.getenv("COS_AGENT_MAX_PER_USER", "10"))
CONTROL_TIMEOUT = float(os.getenv("COS_CONTROL_API_TIMEOUT_SECONDS", "20"))
A2A_MAX_ENDPOINTS_PER_USER = int(os.getenv("COS_A2A_MAX_ENDPOINTS_PER_USER", "20"))
A2A_MAX_PENDING_PER_ENDPOINT = int(os.getenv("COS_A2A_MAX_PENDING_PER_ENDPOINT", "100"))
A2A_DEFAULT_TTL_SECONDS = int(os.getenv("COS_A2A_DEFAULT_TTL_SECONDS", "86400"))
A2A_MAX_TTL_SECONDS = int(os.getenv("COS_A2A_MAX_TTL_SECONDS", "604800"))


def _validate_runtime_config() -> None:
    parsed = urlparse(CONTROL_API_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("COS_CONTROL_API_URL must be an HTTP loopback URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError("COS_CONTROL_API_URL must not contain a path, query, or fragment")
    if not IDENTITY_SECRET or len(IDENTITY_SECRET.encode("utf-8")) < 32:
        raise RuntimeError("COS_IDENTITY_HMAC_SECRET must contain at least 32 bytes")
    if not IDENTITY_PREFIX or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", IDENTITY_PREFIX):
        raise RuntimeError("COS_IDENTITY_HEADER_PREFIX is invalid")
    if MAX_AGENTS_PER_USER < 1 or MAX_AGENTS_PER_USER > 100:
        raise RuntimeError("COS_AGENT_MAX_PER_USER must be between 1 and 100")
    if CONTROL_TIMEOUT < 1 or CONTROL_TIMEOUT > 120:
        raise RuntimeError("COS_CONTROL_API_TIMEOUT_SECONDS must be between 1 and 120")
    if not 1 <= A2A_MAX_ENDPOINTS_PER_USER <= 100:
        raise RuntimeError("COS_A2A_MAX_ENDPOINTS_PER_USER must be between 1 and 100")
    if not 1 <= A2A_MAX_PENDING_PER_ENDPOINT <= 1000:
        raise RuntimeError("COS_A2A_MAX_PENDING_PER_ENDPOINT must be between 1 and 1000")
    if not 60 <= A2A_DEFAULT_TTL_SECONDS <= A2A_MAX_TTL_SECONDS <= 604800:
        raise RuntimeError("COS A2A message TTL settings are invalid")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        DB_PATH.parent.chmod(0o700)
    except OSError:
        pass
    db = sqlite3.connect(DB_PATH, timeout=10)
    try:
        DB_PATH.chmod(0o600)
    except OSError:
        pass
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _init_db() -> None:
    with _connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                owner_email TEXT NOT NULL,
                label TEXT NOT NULL,
                input_id TEXT NOT NULL,
                cos_session_id TEXT,
                cos_conversation_id TEXT,
                state TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_id, created_at)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_input ON agents(input_id)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_endpoints (
                endpoint_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                owner_fingerprint TEXT NOT NULL,
                label TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('active', 'disabled')),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_endpoints_owner ON a2a_endpoints(owner_id, state, created_at)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_endpoint_acl (
                endpoint_id TEXT NOT NULL REFERENCES a2a_endpoints(endpoint_id),
                sender_fingerprint TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY(endpoint_id, sender_fingerprint)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_endpoint_peer_acl_mode (
                endpoint_id TEXT PRIMARY KEY REFERENCES a2a_endpoints(endpoint_id),
                configured_at INTEGER NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_endpoint_peer_acl (
                endpoint_id TEXT NOT NULL REFERENCES a2a_endpoints(endpoint_id),
                sender_endpoint_id TEXT NOT NULL REFERENCES a2a_endpoints(endpoint_id),
                created_at INTEGER NOT NULL,
                PRIMARY KEY(endpoint_id, sender_endpoint_id)
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_peer_acl_sender ON a2a_endpoint_peer_acl(sender_endpoint_id)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_messages (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                correlation_id TEXT NOT NULL,
                sender_endpoint_id TEXT NOT NULL REFERENCES a2a_endpoints(endpoint_id),
                sender_owner_id TEXT NOT NULL,
                sender_fingerprint TEXT NOT NULL,
                recipient_endpoint_id TEXT NOT NULL REFERENCES a2a_endpoints(endpoint_id),
                body TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('queued', 'received', 'acked', 'expired')),
                idempotency_key TEXT NOT NULL,
                reply_to_message_id TEXT REFERENCES a2a_messages(message_id),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                received_at INTEGER,
                acked_at INTEGER,
                UNIQUE(sender_endpoint_id, idempotency_key)
            )
            """
        )
        message_columns = {row["name"] for row in db.execute("PRAGMA table_info(a2a_messages)").fetchall()}
        if "reply_to_message_id" not in message_columns:
            db.execute("ALTER TABLE a2a_messages ADD COLUMN reply_to_message_id TEXT REFERENCES a2a_messages(message_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_messages_inbox ON a2a_messages(recipient_endpoint_id, state, seq)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_messages_expiry ON a2a_messages(expires_at, state)")


def _header(headers: Any, name: str) -> str | None:
    value = headers.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _identity_from_request(request: Request | None) -> dict[str, str]:
    """Verify ContextForge's signed identity header; ignore unsigned role/team data."""
    if request is None:
        raise PermissionError("Authenticated ContextForge request required")

    headers = request.headers
    user_id = _header(headers, f"{IDENTITY_PREFIX}-Id")
    email = _header(headers, f"{IDENTITY_PREFIX}-Email")
    signature = _header(headers, f"{IDENTITY_PREFIX}-Claims-Signature")
    if not user_id or not email or not signature:
        raise PermissionError("Signed user identity missing")

    expected = hmac.new(
        IDENTITY_SECRET.encode("utf-8"),
        f"{user_id}:{email}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise PermissionError("Signed user identity invalid")

    # ContextForge's current UserContext uses the verified email as user_id.
    # Requiring equality prevents ambiguous ownership keys across deployments.
    if user_id.casefold() != email.casefold():
        raise PermissionError("User identity mapping is not supported")
    return {"owner_id": user_id.casefold(), "email": email.casefold()}


class ControlApiClient:
    """Small authenticated client for the loopback-only COS Control API."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._token = ""

    async def start(self) -> None:
        if not TOKEN_FILE.is_file():
            raise RuntimeError(f"COS Control API token file not found: {TOKEN_FILE}")
        self._token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(self._token) < 16:
            raise RuntimeError("COS Control API token file is empty or invalid")
        self._client = httpx.AsyncClient(
            base_url=CONTROL_API_URL,
            timeout=httpx.Timeout(CONTROL_TIMEOUT),
            headers={"Authorization": f"Bearer {self._token}"},
            trust_env=False,
        )
        health = await self.get("/v1/health")
        if health.get("ok") is not True or health.get("actions", {}).get("enabled") is not True:
            await self.stop()
            raise RuntimeError("COS Control API is unhealthy or actions are disabled")

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._token = ""

    async def get(self, path: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("COS Control API client is not initialized")
        response = await self._client.get(path)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("COS Control API returned an invalid response")
        return payload

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("COS Control API client is not initialized")
        response = await self._client.post(path, json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("COS Control API returned an invalid response")
        return body


control_api = ControlApiClient()


def _owned_agent(agent_id: str, identity: dict[str, str]) -> sqlite3.Row:
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM agents WHERE agent_id = ? AND owner_id = ?",
            (agent_id, identity["owner_id"]),
        ).fetchone()
    if row is None:
        raise PermissionError("Agent not found")
    return row


async def _sync_agent(agent: sqlite3.Row) -> sqlite3.Row:
    if agent["cos_session_id"]:
        return agent
    inputs = (await control_api.get("/v1/inputs?limit=500")).get("inputs", [])
    item = next((entry for entry in inputs if entry.get("id") == agent["input_id"]), None)
    if not item:
        return agent
    session_id = item.get("deliveredSessionId") or item.get("sessionId")
    conversation_id = item.get("conversationId")
    if not session_id or not conversation_id or item.get("delivery") != "sent":
        return agent

    now = int(time.time())
    with _connect() as db:
        db.execute(
            "UPDATE agents SET cos_session_id = ?, cos_conversation_id = ?, state = 'active', updated_at = ? WHERE agent_id = ? AND owner_id = ?",
            (session_id, conversation_id, now, agent["agent_id"], agent["owner_id"]),
        )
        return db.execute("SELECT * FROM agents WHERE agent_id = ?", (agent["agent_id"],)).fetchone()


def _agent_summary(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "label": row["label"],
        "state": row["state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def _register_agent(identity: dict[str, str], label: str, initial_message: str) -> dict[str, Any]:
    label = label.strip()
    initial_message = initial_message.strip()
    if not label or len(label) > 60:
        raise ValueError("label must contain 1-60 characters")
    if not initial_message or len(initial_message) > 4000:
        raise ValueError("initial_message must contain 1-4000 characters")

    agent_id = str(uuid4())
    input_id = str(uuid4())
    now = int(time.time())
    with _connect() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM agents WHERE owner_id = ? AND state != 'closed'",
            (identity["owner_id"],),
        ).fetchone()[0]
        if count >= MAX_AGENTS_PER_USER:
            raise ValueError(f"Agent limit reached ({MAX_AGENTS_PER_USER})")
        db.execute(
            "INSERT INTO agents (agent_id, owner_id, owner_email, label, input_id, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'creating', ?, ?)",
            (agent_id, identity["owner_id"], identity["email"], label, input_id, now, now),
        )

    try:
        await control_api.post(
            "/v1/inputs",
            {"id": input_id, "text": initial_message},
        )
        with _connect() as db:
            db.execute("UPDATE agents SET state = 'pending', updated_at = ? WHERE agent_id = ?", (int(time.time()), agent_id))
            row = db.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        row = await _sync_agent(row)
        return _agent_summary(row)
    except Exception:
        with _connect() as db:
            db.execute("DELETE FROM agents WHERE agent_id = ? AND owner_id = ?", (agent_id, identity["owner_id"]))
        raise


async def _list_agents(identity: dict[str, str]) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM agents WHERE owner_id = ? ORDER BY created_at DESC LIMIT 100",
            (identity["owner_id"],),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        if row["state"] == "pending":
            row = await _sync_agent(row)
        result.append(_agent_summary(row))
    return result


async def _send_message(identity: dict[str, str], agent_id: str, message: str) -> dict[str, Any]:
    message = message.strip()
    if not message or len(message) > 4000:
        raise ValueError("message must contain 1-4000 characters")
    agent = await _sync_agent(_owned_agent(agent_id, identity))
    if not agent["cos_session_id"]:
        raise RuntimeError("Agent chat is still being created; retry shortly")

    input_id = str(uuid4())
    response = await control_api.post(
        "/v1/inputs",
        {"id": input_id, "sessionId": agent["cos_session_id"], "text": message},
    )
    with _connect() as db:
        db.execute("UPDATE agents SET updated_at = ? WHERE agent_id = ?", (int(time.time()), agent_id))
    return {"agent_id": agent_id, "input_id": input_id, "accepted": True, "delivery": response.get("input", {}).get("delivery", "pending")}


async def _read_messages(identity: dict[str, str], agent_id: str, after: int, limit: int) -> dict[str, Any]:
    if after < 0 or limit < 1 or limit > 100:
        raise ValueError("after must be >= 0 and limit must be 1-100")
    agent = await _sync_agent(_owned_agent(agent_id, identity))
    if not agent["cos_session_id"]:
        return {"agent_id": agent_id, "state": "pending", "events": [], "next_from": None}
    payload = await control_api.get(
        f"/v1/sessions/{agent['cos_session_id']}/events?after={after}&limit={limit}"
    )
    allowed = {"assistant_message", "progress", "turn_end", "error"}
    events: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        if event.get("kind") not in allowed:
            continue
        message = event.get("message") or {}
        text = message.get("text") if isinstance(message, dict) else None
        if not text and event.get("kind") == "turn_end":
            text = event.get("outcome")
        if text:
            events.append({"seq": event.get("seq"), "kind": event.get("kind"), "time": event.get("time"), "text": str(text)[:20000]})
    return {
        "agent_id": agent_id,
        "events": events,
        "total": payload.get("total", len(events)),
        "next_from": payload.get("nextFrom"),
    }


async def _get_status(identity: dict[str, str], agent_id: str) -> dict[str, Any]:
    agent = await _sync_agent(_owned_agent(agent_id, identity))
    summary = _agent_summary(agent)
    if not agent["cos_session_id"]:
        return summary
    payload = await control_api.get(f"/v1/sessions/{agent['cos_session_id']}")
    session = payload.get("session", payload)
    summary.update(
        {
            "last_turn_outcome": session.get("lastTurnOutcome"),
            "active_turn": bool(session.get("activeTurnId")),
            "events": session.get("events"),
            "errors": session.get("errors"),
            "last_activity_at": session.get("updatedAt"),
        }
    )
    return summary


def _identity_fingerprint(identity: dict[str, str]) -> str:
    """Return a stable, non-reversible pseudonym for the verified ContextForge user.

    The fingerprint is comparable across OAuth sessions that resolve to the
    same ContextForge owner_id and use the same broker identity secret. It is
    not a ChatGPT account identifier.
    """
    owner_id = identity.get("owner_id")
    if not isinstance(owner_id, str) or not owner_id:
        raise PermissionError("Verified ContextForge user identity required")

    fingerprint_key = hmac.new(
        IDENTITY_SECRET.encode("utf-8"),
        b"cos-control-broker/identity-fingerprint/key/v1",
        hashlib.sha256,
    ).digest()
    return hmac.new(
        fingerprint_key,
        owner_id.casefold().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _get_identity_info(identity: dict[str, str]) -> dict[str, Any]:
    """Return safe identity-comparison metadata and this owner's registry count."""
    fingerprint = _identity_fingerprint(identity)
    with _connect() as db:
        owned_agent_count = db.execute(
            "SELECT COUNT(*) FROM agents WHERE owner_id = ?",
            (identity["owner_id"].casefold(),),
        ).fetchone()[0]

    return {
        "identity_type": "contextforge_user",
        "identity_fingerprint": fingerprint,
        "fingerprint_algorithm": "HMAC-SHA256",
        "fingerprint_version": "v1",
        "fingerprint_scope": "cos_control_broker_identity_domain",
        "owned_agent_count": int(owned_agent_count),
    }


def _a2a_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a UUID")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise ValueError(f"{field} must be a UUID") from None


def _a2a_fingerprint(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("allowed sender fingerprints must be lowercase 64-character hex values")
    return value


def _a2a_fingerprint_list(values: Any) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("allowed_sender_fingerprints must be an array with at most 100 entries")
    normalized = [_a2a_fingerprint(value) for value in values]
    if len(set(normalized)) != len(normalized):
        raise ValueError("allowed_sender_fingerprints must not contain duplicates")
    return normalized


def _a2a_sender_acl_token(endpoint_id: str) -> str:
    """Return a broker-scoped, non-secret token for one sender endpoint.

    This preserves the old 64-hex ACL input schema while allowing exact
    endpoint-level authorization across Workstreams sharing one account.
    It is not an authentication credential; sender endpoint ownership is
    still verified for every send operation.
    """
    endpoint_id = _a2a_uuid(endpoint_id, "endpoint_id")
    return hmac.new(
        IDENTITY_SECRET.encode("utf-8"),
        f"a2a-sender-endpoint-v1:{endpoint_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _a2a_correlation_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise ValueError("correlation_id must be 1-128 safe ASCII characters")
    return value


def _a2a_idempotency_key(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise ValueError("idempotency_key must be 1-128 safe ASCII characters")
    return value


def _owned_a2a_endpoint(db: sqlite3.Connection, endpoint_id: str, identity: dict[str, str]) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM a2a_endpoints WHERE endpoint_id = ? AND owner_id = ?",
        (endpoint_id, identity["owner_id"].casefold()),
    ).fetchone()
    if row is None:
        raise PermissionError("A2A endpoint not found")
    return row


def _a2a_endpoint_summary(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    fingerprint_count = db.execute(
        "SELECT COUNT(*) FROM a2a_endpoint_acl WHERE endpoint_id = ?",
        (row["endpoint_id"],),
    ).fetchone()[0]
    peer_count = db.execute(
        "SELECT COUNT(*) FROM a2a_endpoint_peer_acl WHERE endpoint_id = ?",
        (row["endpoint_id"],),
    ).fetchone()[0]
    peer_mode = db.execute(
        "SELECT 1 FROM a2a_endpoint_peer_acl_mode WHERE endpoint_id = ?",
        (row["endpoint_id"],),
    ).fetchone() is not None
    return {
        "endpoint_id": row["endpoint_id"],
        "label": row["label"],
        "state": row["state"],
        "identity_fingerprint": row["owner_fingerprint"],
        "acl_mode": "endpoint" if peer_mode else "identity_fingerprint",
        "allowed_sender_count": int(peer_count if peer_mode else fingerprint_count),
        "allowed_sender_endpoint_count": int(peer_count),
        "allowed_sender_fingerprint_count": int(fingerprint_count),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _a2a_register_endpoint(
    identity: dict[str, str], label: str, allowed_sender_fingerprints: Any = None
) -> dict[str, Any]:
    label = label.strip() if isinstance(label, str) else ""
    if not label or len(label) > 60:
        raise ValueError("label must contain 1-60 characters")
    allowed = _a2a_fingerprint_list(allowed_sender_fingerprints)
    endpoint_id = str(uuid4())
    fingerprint = _identity_fingerprint(identity)
    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        count = db.execute(
            "SELECT COUNT(*) FROM a2a_endpoints WHERE owner_id = ?",
            (identity["owner_id"].casefold(),),
        ).fetchone()[0]
        if count >= A2A_MAX_ENDPOINTS_PER_USER:
            raise ValueError(f"A2A endpoint limit reached ({A2A_MAX_ENDPOINTS_PER_USER})")
        db.execute(
            "INSERT INTO a2a_endpoints (endpoint_id, owner_id, owner_fingerprint, label, state, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (endpoint_id, identity["owner_id"].casefold(), fingerprint, label, now, now),
        )
        db.executemany(
            "INSERT INTO a2a_endpoint_acl (endpoint_id, sender_fingerprint, created_at) VALUES (?, ?, ?)",
            [(endpoint_id, sender, now) for sender in allowed],
        )
        row = db.execute("SELECT * FROM a2a_endpoints WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
        return _a2a_endpoint_summary(db, row)


def _a2a_set_endpoint_acl(
    identity: dict[str, str], endpoint_id: str, allowed_sender_fingerprints: Any
) -> dict[str, Any]:
    endpoint_id = _a2a_uuid(endpoint_id, "endpoint_id")
    allowed = _a2a_fingerprint_list(allowed_sender_fingerprints)
    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = _owned_a2a_endpoint(db, endpoint_id, identity)
        if row["state"] != "active":
            raise ValueError("A2A endpoint is disabled")
        exact_mode = db.execute(
            "SELECT 1 FROM a2a_endpoint_peer_acl_mode WHERE endpoint_id = ?",
            (endpoint_id,),
        ).fetchone() is not None

        endpoint_rows = db.execute(
            "SELECT endpoint_id, state FROM a2a_endpoints"
        ).fetchall()
        token_to_endpoint = {
            _a2a_sender_acl_token(item["endpoint_id"]): item["endpoint_id"]
            for item in endpoint_rows
        }
        recognized_tokens = [value for value in allowed if value in token_to_endpoint]
        use_exact_endpoint_acl = not allowed or len(recognized_tokens) == len(allowed)

        if exact_mode and not use_exact_endpoint_acl:
            raise ValueError("Endpoint uses exact sender endpoint ACL; use tokens from a2a_endpoint_list peer_directory")

        if use_exact_endpoint_acl:
            sender_endpoint_ids = [token_to_endpoint[value] for value in allowed]
            inactive = {
                item["endpoint_id"] for item in endpoint_rows if item["state"] != "active"
            }
            if any(sender_id in inactive for sender_id in sender_endpoint_ids):
                raise ValueError("Every allowed sender endpoint must be active")
            db.execute(
                "INSERT INTO a2a_endpoint_peer_acl_mode (endpoint_id, configured_at) VALUES (?, ?) ON CONFLICT(endpoint_id) DO UPDATE SET configured_at = excluded.configured_at",
                (endpoint_id, now),
            )
            db.execute("DELETE FROM a2a_endpoint_peer_acl WHERE endpoint_id = ?", (endpoint_id,))
            db.executemany(
                "INSERT INTO a2a_endpoint_peer_acl (endpoint_id, sender_endpoint_id, created_at) VALUES (?, ?, ?)",
                [(endpoint_id, sender_id, now) for sender_id in sender_endpoint_ids],
            )
            db.execute("DELETE FROM a2a_endpoint_acl WHERE endpoint_id = ?", (endpoint_id,))
            if sender_endpoint_ids:
                placeholders = ",".join("?" for _ in sender_endpoint_ids)
                db.execute(
                    f"UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received') AND sender_endpoint_id NOT IN ({placeholders})",
                    [endpoint_id, *sender_endpoint_ids],
                )
            else:
                db.execute(
                    "UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received')",
                    (endpoint_id,),
                )
            db.execute("UPDATE a2a_endpoints SET updated_at = ? WHERE endpoint_id = ?", (now, endpoint_id))
            updated = db.execute("SELECT * FROM a2a_endpoints WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
            return _a2a_endpoint_summary(db, updated)

        db.execute("DELETE FROM a2a_endpoint_acl WHERE endpoint_id = ?", (endpoint_id,))
        db.executemany(
            "INSERT INTO a2a_endpoint_acl (endpoint_id, sender_fingerprint, created_at) VALUES (?, ?, ?)",
            [(endpoint_id, sender, now) for sender in allowed],
        )
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            db.execute(
                f"UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received') AND sender_fingerprint NOT IN ({placeholders})",
                [endpoint_id, *allowed],
            )
        else:
            db.execute(
                "UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received')",
                (endpoint_id,),
            )
        db.execute("UPDATE a2a_endpoints SET updated_at = ? WHERE endpoint_id = ?", (now, endpoint_id))
        row = db.execute("SELECT * FROM a2a_endpoints WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
        return _a2a_endpoint_summary(db, row)


def _a2a_list_endpoints(identity: dict[str, str]) -> dict[str, Any]:
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM a2a_endpoints WHERE owner_id = ? ORDER BY created_at, endpoint_id",
            (identity["owner_id"].casefold(),),
        ).fetchall()
        peer_rows = db.execute(
            "SELECT * FROM a2a_endpoints WHERE state = 'active' ORDER BY label COLLATE NOCASE, created_at, endpoint_id"
        ).fetchall()
        own_endpoints = [_a2a_endpoint_summary(db, row) for row in rows]
        peer_directory = [
            {
                **_a2a_endpoint_summary(db, row),
                "sender_acl_token": _a2a_sender_acl_token(row["endpoint_id"]),
            }
            for row in peer_rows
        ]
        return {
            "endpoints": own_endpoints,
            "peer_directory": peer_directory,
            "peer_directory_total": len(peer_directory),
        }


def _a2a_directory_list(_identity: dict[str, str]) -> dict[str, Any]:
    """List active routing records without exposing owner IDs or session data.

    The endpoint label is owner-asserted metadata. Its owner fingerprint is a
    stable pseudonym scoped to this broker, not a ChatGPT account identifier.
    """
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM a2a_endpoints WHERE state = 'active' ORDER BY label COLLATE NOCASE, created_at, endpoint_id"
        ).fetchall()
        endpoints = [
            {
                **_a2a_endpoint_summary(db, row),
                "sender_acl_token": _a2a_sender_acl_token(row["endpoint_id"]),
            }
            for row in rows
        ]
    return {
        "directory_scope": "authenticated_cos_broker_tenant",
        "directory_version": 1,
        "endpoints": endpoints,
        "total": len(endpoints),
    }


def _a2a_endpoint_peer_acl_set(
    identity: dict[str, str], endpoint_id: str, allowed_sender_endpoint_ids: Any
) -> dict[str, Any]:
    endpoint_id = _a2a_uuid(endpoint_id, "endpoint_id")
    if not isinstance(allowed_sender_endpoint_ids, list) or len(allowed_sender_endpoint_ids) > 100:
        raise ValueError("allowed_sender_endpoint_ids must be an array with at most 100 entries")
    allowed = [_a2a_uuid(value, "allowed_sender_endpoint_ids item") for value in allowed_sender_endpoint_ids]
    if len(set(allowed)) != len(allowed):
        raise ValueError("allowed_sender_endpoint_ids must not contain duplicates")

    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        recipient = _owned_a2a_endpoint(db, endpoint_id, identity)
        if recipient["state"] != "active":
            raise ValueError("A2A endpoint is disabled")
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            active_count = db.execute(
                f"SELECT COUNT(*) FROM a2a_endpoints WHERE state = 'active' AND endpoint_id IN ({placeholders})",
                allowed,
            ).fetchone()[0]
            if active_count != len(allowed):
                raise ValueError("Every allowed sender endpoint must exist and be active")

        db.execute(
            "INSERT INTO a2a_endpoint_peer_acl_mode (endpoint_id, configured_at) VALUES (?, ?) ON CONFLICT(endpoint_id) DO UPDATE SET configured_at = excluded.configured_at",
            (endpoint_id, now),
        )
        db.execute("DELETE FROM a2a_endpoint_peer_acl WHERE endpoint_id = ?", (endpoint_id,))
        db.executemany(
            "INSERT INTO a2a_endpoint_peer_acl (endpoint_id, sender_endpoint_id, created_at) VALUES (?, ?, ?)",
            [(endpoint_id, sender_id, now) for sender_id in allowed],
        )
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            db.execute(
                f"UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received') AND sender_endpoint_id NOT IN ({placeholders})",
                [endpoint_id, *allowed],
            )
        else:
            db.execute(
                "UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received')",
                (endpoint_id,),
            )
        db.execute("UPDATE a2a_endpoints SET updated_at = ? WHERE endpoint_id = ?", (now, endpoint_id))
        updated = db.execute("SELECT * FROM a2a_endpoints WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
        return _a2a_endpoint_summary(db, updated)


def _a2a_sender_is_allowed(
    db: sqlite3.Connection, recipient_endpoint_id: str, sender_endpoint_id: str, sender_fingerprint: str
) -> bool:
    """Prefer exact endpoint ACL when configured; otherwise honor legacy ACL."""
    peer_mode = db.execute(
        "SELECT 1 FROM a2a_endpoint_peer_acl_mode WHERE endpoint_id = ?",
        (recipient_endpoint_id,),
    ).fetchone()
    if peer_mode is not None:
        return db.execute(
            "SELECT 1 FROM a2a_endpoint_peer_acl WHERE endpoint_id = ? AND sender_endpoint_id = ?",
            (recipient_endpoint_id, sender_endpoint_id),
        ).fetchone() is not None
    return db.execute(
        "SELECT 1 FROM a2a_endpoint_acl WHERE endpoint_id = ? AND sender_fingerprint = ?",
        (recipient_endpoint_id, sender_fingerprint),
    ).fetchone() is not None


def _a2a_insert_message(
    db: sqlite3.Connection,
    identity: dict[str, str],
    sender_endpoint_id: str,
    recipient_endpoint_id: str,
    correlation_id: str,
    idempotency_key: str,
    message: str,
    ttl_seconds: int,
    reply_to_message_id: str | None = None,
) -> dict[str, Any]:
    sender = _owned_a2a_endpoint(db, sender_endpoint_id, identity)
    if sender["state"] != "active":
        raise ValueError("Sender endpoint is disabled")

    existing = db.execute(
        "SELECT * FROM a2a_messages WHERE sender_endpoint_id = ? AND idempotency_key = ?",
        (sender_endpoint_id, idempotency_key),
    ).fetchone()
    if existing is not None:
        same_request = (
            existing["recipient_endpoint_id"] == recipient_endpoint_id
            and existing["correlation_id"] == correlation_id
            and existing["body"] == message
            and existing["reply_to_message_id"] == reply_to_message_id
        )
        if not same_request:
            raise ValueError("idempotency_key was already used with a different message")
        return {
            "message_id": existing["message_id"],
            "correlation_id": existing["correlation_id"],
            "state": existing["state"],
            "durable": True,
            "duplicate": True,
            "created_at": existing["created_at"],
            "expires_at": existing["expires_at"],
        }

    recipient = db.execute(
        "SELECT * FROM a2a_endpoints WHERE endpoint_id = ? AND state = 'active'",
        (recipient_endpoint_id,),
    ).fetchone()
    if recipient is None:
        raise PermissionError("Recipient A2A endpoint not found")
    if not _a2a_sender_is_allowed(
        db, recipient_endpoint_id, sender_endpoint_id, sender["owner_fingerprint"]
    ):
        raise PermissionError("Sender endpoint is not authorized by recipient endpoint ACL")

    pending = db.execute(
        "SELECT COUNT(*) FROM a2a_messages WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received') AND expires_at > ?",
        (recipient_endpoint_id, int(time.time())),
    ).fetchone()[0]
    if pending >= A2A_MAX_PENDING_PER_ENDPOINT:
        raise ValueError("Recipient A2A inbox is full")

    now = int(time.time())
    message_id = str(uuid4())
    expires_at = now + ttl_seconds
    db.execute(
        "INSERT INTO a2a_messages (message_id, correlation_id, sender_endpoint_id, sender_owner_id, sender_fingerprint, recipient_endpoint_id, body, state, idempotency_key, reply_to_message_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)",
        (
            message_id,
            correlation_id,
            sender_endpoint_id,
            identity["owner_id"].casefold(),
            sender["owner_fingerprint"],
            recipient_endpoint_id,
            message,
            idempotency_key,
            reply_to_message_id,
            now,
            expires_at,
        ),
    )
    return {
        "message_id": message_id,
        "correlation_id": correlation_id,
        "state": "queued",
        "durable": True,
        "duplicate": False,
        "created_at": now,
        "expires_at": expires_at,
    }


def _a2a_send_message(
    identity: dict[str, str],
    sender_endpoint_id: str,
    recipient_endpoint_id: str,
    correlation_id: str,
    idempotency_key: str,
    message: str,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    sender_endpoint_id = _a2a_uuid(sender_endpoint_id, "sender_endpoint_id")
    recipient_endpoint_id = _a2a_uuid(recipient_endpoint_id, "recipient_endpoint_id")
    correlation_id = _a2a_correlation_id(correlation_id)
    idempotency_key = _a2a_idempotency_key(idempotency_key)
    message = message.strip() if isinstance(message, str) else ""
    if not message or len(message) > 4000:
        raise ValueError("message must contain 1-4000 characters")
    ttl = A2A_DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 60 or ttl > A2A_MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be between 60 and {A2A_MAX_TTL_SECONDS}")

    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        db.execute(
            "UPDATE a2a_messages SET state = 'expired' WHERE state IN ('queued', 'received') AND expires_at <= ?",
            (now,),
        )
        return _a2a_insert_message(
            db,
            identity,
            sender_endpoint_id,
            recipient_endpoint_id,
            correlation_id,
            idempotency_key,
            message,
            ttl,
        )


def _a2a_read_inbox(identity: dict[str, str], endpoint_id: str, after_seq: int = 0, limit: int = 50) -> dict[str, Any]:
    endpoint_id = _a2a_uuid(endpoint_id, "endpoint_id")
    if isinstance(after_seq, bool) or not isinstance(after_seq, int) or after_seq < 0:
        raise ValueError("after_seq must be an integer >= 0")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _owned_a2a_endpoint(db, endpoint_id, identity)
        now = int(time.time())
        db.execute(
            "UPDATE a2a_messages SET state = 'expired' WHERE recipient_endpoint_id = ? AND state IN ('queued', 'received') AND expires_at <= ?",
            (endpoint_id, now),
        )
        rows = db.execute(
            "SELECT * FROM a2a_messages WHERE recipient_endpoint_id = ? AND seq > ? AND state IN ('queued', 'received') ORDER BY seq LIMIT ?",
            (endpoint_id, after_seq, limit),
        ).fetchall()
        seqs = [int(row["seq"]) for row in rows if row["state"] == "queued"]
        if seqs:
            placeholders = ",".join("?" for _ in seqs)
            db.execute(
                f"UPDATE a2a_messages SET state = 'received', received_at = ? WHERE seq IN ({placeholders}) AND state = 'queued'",
                [now, *seqs],
            )
        events = [
            {
                "seq": int(row["seq"]),
                "message_id": row["message_id"],
                "correlation_id": row["correlation_id"],
                "sender_endpoint_id": row["sender_endpoint_id"],
                "sender_fingerprint": row["sender_fingerprint"],
                "message": row["body"],
                "reply_to_message_id": row["reply_to_message_id"],
                "state": "received",
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]
        return {
            "endpoint_id": endpoint_id,
            "events": events,
            "total": len(events),
            "next_after_seq": int(rows[-1]["seq"]) if rows else after_seq,
        }


def _a2a_ack_message(identity: dict[str, str], endpoint_id: str, message_id: str) -> dict[str, Any]:
    endpoint_id = _a2a_uuid(endpoint_id, "endpoint_id")
    message_id = _a2a_uuid(message_id, "message_id")
    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _owned_a2a_endpoint(db, endpoint_id, identity)
        row = db.execute(
            "SELECT * FROM a2a_messages WHERE message_id = ? AND recipient_endpoint_id = ?",
            (message_id, endpoint_id),
        ).fetchone()
        if row is None:
            raise PermissionError("A2A message not found")
        if row["state"] == "expired" or row["expires_at"] <= now:
            db.execute("UPDATE a2a_messages SET state = 'expired' WHERE message_id = ?", (message_id,))
            return {"message_id": message_id, "state": "expired", "acked_at": None}
        if row["state"] != "acked":
            db.execute(
                "UPDATE a2a_messages SET state = 'acked', acked_at = ? WHERE message_id = ?",
                (now, message_id),
            )
        return {"message_id": message_id, "state": "acked", "acked_at": row["acked_at"] or now}


def _a2a_reply_message(
    identity: dict[str, str],
    sender_endpoint_id: str,
    original_message_id: str,
    idempotency_key: str,
    message: str,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    sender_endpoint_id = _a2a_uuid(sender_endpoint_id, "sender_endpoint_id")
    original_message_id = _a2a_uuid(original_message_id, "original_message_id")
    idempotency_key = _a2a_idempotency_key(idempotency_key)
    message = message.strip() if isinstance(message, str) else ""
    if not message or len(message) > 4000:
        raise ValueError("message must contain 1-4000 characters")
    ttl = A2A_DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 60 or ttl > A2A_MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be between 60 and {A2A_MAX_TTL_SECONDS}")

    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        original = db.execute(
            "SELECT * FROM a2a_messages WHERE message_id = ?",
            (original_message_id,),
        ).fetchone()
        if original is None or original["recipient_endpoint_id"] != sender_endpoint_id:
            raise PermissionError("Original A2A message not found for this endpoint")
        now = int(time.time())
        if original["expires_at"] <= now or original["state"] == "expired":
            db.execute("UPDATE a2a_messages SET state = 'expired' WHERE message_id = ?", (original_message_id,))
            raise ValueError("Original A2A message has expired")
        existing_reply = db.execute(
            "SELECT * FROM a2a_messages WHERE sender_endpoint_id = ? AND idempotency_key = ?",
            (sender_endpoint_id, idempotency_key),
        ).fetchone()
        if existing_reply is not None:
            same_request = (
                existing_reply["recipient_endpoint_id"] == original["sender_endpoint_id"]
                and existing_reply["correlation_id"] == original["correlation_id"]
                and existing_reply["body"] == message
                and existing_reply["reply_to_message_id"] == original_message_id
            )
            if not same_request:
                raise ValueError("idempotency_key was already used with a different message")
            return {
                "message_id": existing_reply["message_id"],
                "correlation_id": existing_reply["correlation_id"],
                "state": existing_reply["state"],
                "durable": True,
                "duplicate": True,
                "created_at": existing_reply["created_at"],
                "expires_at": existing_reply["expires_at"],
                "reply_to_message_id": original_message_id,
                "original_message_acked": True,
            }
        if original["state"] == "acked":
            raise ValueError("Original A2A message has already been acknowledged")
        result = _a2a_insert_message(
            db,
            identity,
            sender_endpoint_id,
            original["sender_endpoint_id"],
            original["correlation_id"],
            idempotency_key,
            message,
            ttl,
            original_message_id,
        )
        db.execute(
            "UPDATE a2a_messages SET state = 'acked', acked_at = COALESCE(acked_at, ?) WHERE message_id = ?",
            (now, original_message_id),
        )
        result["reply_to_message_id"] = original_message_id
        result["original_message_acked"] = True
        return result


TOOL_DEFINITIONS = [
    types.Tool(
        name="get_identity",
        description="Return a privacy-preserving fingerprint for the authenticated ContextForge user and the count of broker agents owned by that user. This identifies a ContextForge identity, not a ChatGPT account.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="agent_register",
        description="Create a dedicated COS conversation owned by the authenticated ContextForge user. Does not expose another user's sessions.",
        inputSchema={"type": "object", "properties": {"label": {"type": "string", "minLength": 1, "maxLength": 60}, "initial_message": {"type": "string", "minLength": 1, "maxLength": 4000}}, "required": ["label", "initial_message"], "additionalProperties": False},
    ),
    types.Tool(
        name="agent_list",
        description="List only COS conversations owned by the authenticated ContextForge user.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="agent_send_message",
        description="Send a message to one of the caller's own registered COS conversations.",
        inputSchema={"type": "object", "properties": {"agent_id": {"type": "string", "format": "uuid"}, "message": {"type": "string", "minLength": 1, "maxLength": 4000}}, "required": ["agent_id", "message"], "additionalProperties": False},
    ),
    types.Tool(
        name="agent_read_messages",
        description="Read assistant messages and status events from one of the caller's own COS conversations.",
        inputSchema={"type": "object", "properties": {"agent_id": {"type": "string", "format": "uuid"}, "after": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["agent_id"], "additionalProperties": False},
    ),
    types.Tool(
        name="agent_get_status",
        description="Get state and turn status for one of the caller's own COS conversations.",
        inputSchema={"type": "object", "properties": {"agent_id": {"type": "string", "format": "uuid"}}, "required": ["agent_id"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_endpoint_register",
        description="Register a durable A2A inbox endpoint owned by the authenticated ContextForge identity. Private by default; only explicitly allowlisted sender fingerprints may deliver messages.",
        inputSchema={"type": "object", "properties": {"label": {"type": "string", "minLength": 1, "maxLength": 60}, "allowed_sender_fingerprints": {"type": "array", "maxItems": 100, "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}}, "required": ["label"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_endpoint_set_acl",
        description="Replace sender allowlist for an owned endpoint. For exact Workstream isolation, pass sender_acl_token values from a2a_endpoint_list.peer_directory in the existing allowed_sender_fingerprints array; those tokens authorize exact endpoint IDs, not the whole account. For legacy clients, real owner fingerprints remain supported until endpoint mode is enabled. Empty array denies all and enables exact endpoint mode.",
        inputSchema={"type": "object", "properties": {"endpoint_id": {"type": "string", "format": "uuid"}, "allowed_sender_fingerprints": {"type": "array", "maxItems": 100, "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}}, "required": ["endpoint_id", "allowed_sender_fingerprints"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_endpoint_set_peer_acl",
        description="Replace the sender allowlist for one of the caller's own A2A endpoints using exact sender endpoint IDs. This distinguishes Workstreams even when they share one ContextForge identity. An empty list denies all senders and disables legacy fingerprint fallback for this endpoint.",
        inputSchema={"type": "object", "properties": {"endpoint_id": {"type": "string", "format": "uuid"}, "allowed_sender_endpoint_ids": {"type": "array", "maxItems": 100, "items": {"type": "string", "format": "uuid"}}}, "required": ["endpoint_id", "allowed_sender_endpoint_ids"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_endpoint_list",
        description="List caller-owned endpoints plus peer_directory for all active A2A endpoints in this broker deployment. peer_directory contains endpoint IDs, owner-asserted labels, state, pseudonymous owner fingerprint, and sender_acl_token for exact sender ACL setup. It never exposes owner IDs, email, credentials, or COS sessions.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_directory_list",
        description="List active A2A routing endpoints across this authenticated COS broker deployment. Returns only endpoint IDs, owner-asserted labels, state and privacy-preserving owner fingerprints; never returns owner IDs, emails, credentials or COS sessions. Use this to bootstrap cross-account Workstream discovery.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_send_message",
        description="Durably enqueue a message from one of the caller's own A2A endpoints to a recipient endpoint. Recipient ACL is checked against the sender's verified ContextForge fingerprint. This stores a mailbox message; it does not auto-wake a ChatGPT tab.",
        inputSchema={"type": "object", "properties": {"sender_endpoint_id": {"type": "string", "format": "uuid"}, "recipient_endpoint_id": {"type": "string", "format": "uuid"}, "correlation_id": {"type": "string", "minLength": 1, "maxLength": 128}, "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128}, "message": {"type": "string", "minLength": 1, "maxLength": 4000}, "ttl_seconds": {"type": "integer", "minimum": 60, "maximum": 604800}}, "required": ["sender_endpoint_id", "recipient_endpoint_id", "correlation_id", "idempotency_key", "message"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_inbox_read",
        description="Read messages addressed to one of the caller's own A2A endpoints. Reading marks queued messages received. Use next_after_seq for pagination; messages remain until acknowledged or expired.",
        inputSchema={"type": "object", "properties": {"endpoint_id": {"type": "string", "format": "uuid"}, "after_seq": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["endpoint_id"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_message_ack",
        description="Acknowledge a message addressed to one of the caller's own A2A endpoints.",
        inputSchema={"type": "object", "properties": {"endpoint_id": {"type": "string", "format": "uuid"}, "message_id": {"type": "string", "format": "uuid"}}, "required": ["endpoint_id", "message_id"], "additionalProperties": False},
    ),
    types.Tool(
        name="a2a_message_reply",
        description="Reply to a message addressed to one of the caller's own A2A endpoints. Delivers to the original sender endpoint, preserves correlation_id, checks the original sender's ACL, and acknowledges the original message atomically.",
        inputSchema={"type": "object", "properties": {"sender_endpoint_id": {"type": "string", "format": "uuid"}, "original_message_id": {"type": "string", "format": "uuid"}, "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128}, "message": {"type": "string", "minLength": 1, "maxLength": 4000}, "ttl_seconds": {"type": "integer", "minimum": 60, "maximum": 604800}}, "required": ["sender_endpoint_id", "original_message_id", "idempotency_key", "message"], "additionalProperties": False},
    ),
]


async def _list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
    """Expose static schemas for Gateway discovery; calls remain identity-gated.

    ContextForge performs Gateway refresh without an end-user identity. These
    fixed names and JSON schemas contain no user/session data. ``_call_tool``
    independently requires a valid signed ContextForge identity for every call.
    """
    return types.ListToolsResult(tools=TOOL_DEFINITIONS)


async def _call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    try:
        request = getattr(ctx, "request", None)
        identity = _identity_from_request(request)
        arguments = params.arguments or {}

        if params.name == "get_identity":
            result = _get_identity_info(identity)
        elif params.name == "agent_register":
            result = await _register_agent(identity, str(arguments.get("label", "")), str(arguments.get("initial_message", "")))
        elif params.name == "agent_list":
            result = {"agents": await _list_agents(identity)}
        elif params.name == "agent_send_message":
            result = await _send_message(identity, str(arguments.get("agent_id", "")), str(arguments.get("message", "")))
        elif params.name == "agent_read_messages":
            result = await _read_messages(identity, str(arguments.get("agent_id", "")), int(arguments.get("after", 0)), int(arguments.get("limit", 50)))
        elif params.name == "agent_get_status":
            result = await _get_status(identity, str(arguments.get("agent_id", "")))
        elif params.name == "a2a_endpoint_register":
            result = _a2a_register_endpoint(identity, arguments.get("label", ""), arguments.get("allowed_sender_fingerprints", []))
        elif params.name == "a2a_endpoint_set_acl":
            result = _a2a_set_endpoint_acl(identity, arguments.get("endpoint_id", ""), arguments.get("allowed_sender_fingerprints", []))
        elif params.name == "a2a_endpoint_set_peer_acl":
            result = _a2a_endpoint_peer_acl_set(
                identity,
                arguments.get("endpoint_id", ""),
                arguments.get("allowed_sender_endpoint_ids", []),
            )
        elif params.name == "a2a_endpoint_list":
            result = _a2a_list_endpoints(identity)
        elif params.name == "a2a_directory_list":
            result = _a2a_directory_list(identity)
        elif params.name == "a2a_send_message":
            result = _a2a_send_message(
                identity,
                arguments.get("sender_endpoint_id", ""),
                arguments.get("recipient_endpoint_id", ""),
                arguments.get("correlation_id", ""),
                arguments.get("idempotency_key", ""),
                arguments.get("message", ""),
                arguments.get("ttl_seconds"),
            )
        elif params.name == "a2a_inbox_read":
            result = _a2a_read_inbox(
                identity,
                arguments.get("endpoint_id", ""),
                arguments.get("after_seq", 0),
                arguments.get("limit", 50),
            )
        elif params.name == "a2a_message_ack":
            result = _a2a_ack_message(identity, arguments.get("endpoint_id", ""), arguments.get("message_id", ""))
        elif params.name == "a2a_message_reply":
            result = _a2a_reply_message(
                identity,
                arguments.get("sender_endpoint_id", ""),
                arguments.get("original_message_id", ""),
                arguments.get("idempotency_key", ""),
                arguments.get("message", ""),
                arguments.get("ttl_seconds"),
            )
        else:
            raise ValueError("Unknown tool")

        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(result, ensure_ascii=False))],
            structuredContent=result,
        )
    except PermissionError as exc:
        LOGGER.warning("Denied COS broker request: %s", str(exc))
        return types.CallToolResult(content=[types.TextContent(text=str(exc))], isError=True)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        LOGGER.warning("COS broker request failed: %s", type(exc).__name__)
        return types.CallToolResult(content=[types.TextContent(text=str(exc))], isError=True)
    except Exception:
        LOGGER.exception("Unexpected COS broker failure")
        return types.CallToolResult(content=[types.TextContent(text="COS broker internal error")], isError=True)


async def _health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "cos-control-broker", "version": BROKER_VERSION})


async def _startup() -> None:
    _validate_runtime_config()
    _init_db()
    await control_api.start()
    LOGGER.info("COS Control broker started; control API loopback connection verified")


async def _shutdown() -> None:
    await control_api.stop()


async def _lifespan(app: Any):
    await _startup()
    try:
        async with _server_lifespan(app):
            yield
    finally:
        await _shutdown()


server = Server(
    "cos-control-broker",
    version=BROKER_VERSION,
    instructions="Per-user broker for the local Chat On Steroids Control API. Each caller can access only conversations registered under their signed ContextForge identity.",
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    host="127.0.0.1",
    custom_starlette_routes=[Route("/healthz", _health, methods=["GET"])],
)
_server_lifespan = app.router.lifespan_context
_lifespan = asynccontextmanager(_lifespan)
app.router.lifespan_context = _lifespan


if __name__ == "__main__":
    _validate_runtime_config()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("COS_AGENT_BROKER_PORT", "4445")), workers=1)
