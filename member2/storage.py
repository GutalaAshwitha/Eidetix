"""
storage.py — HydraDB storage layer

Built against the confirmed grammar of src/query/opencypher.rs
commit 6a2fbb192f37f51a93690a2ae2d2f5e27e6e4219 (branch: main)

CONFIRMED ENGINE CONSTRAINTS THIS FILE RESPECTS:
  - CREATE patterns are one-hop only (node-rel-node). No multi-hop CREATE
    in a single statement -> every edge write is its own MATCH...CREATE call.
  - Each relationship pattern must have exactly one type.
  - A single Cypher statement per call (no ';' chaining).
  - RETURN * is rejected -> every query lists explicit projections.
  - RETURN projections are limited to: count(*), an aggregate function,
    a bare node id, or <binding>.<property> (this applies to edge bindings
    too, e.g. r.ts on a MATCH (a)-[r:SUPERSEDES]->(b) pattern).
  - Multiple MATCH clauses chain as a pipeline (AND-combined predicates) ->
    this is how multi-hop traversal is done for reads.
  - OPTIONAL MATCH is supported.
  - WITH is pass-through only: no DISTINCT/WHERE/ORDER BY/SKIP/LIMIT inside
    WITH, and every in-scope binding must be forwarded unchanged.
  - ORDER BY, SKIP, LIMIT, DISTINCT are supported on RETURN. SKIP/LIMIT can
    be parameterized. DISTINCT + ORDER BY requires the sort key to also be
    a projected column.

UNVERIFIED AGAINST THE LIVE ENGINE (flagged inline as LIVE-TEST TODO):
  1. Whether an EXISTS{}-style anti-join / OPTIONAL MATCH + "IS NULL" idiom
     works for excluding superseded memories in a single query.
     -> This file uses the CONFIRMED-SAFE fallback instead: fetch all
        SUPERSEDES edges separately and exclude those ids client-side.
  2. Whether variable-length relationship paths (-[:MENTIONS*1..3]->) are
     legal in MATCH the same way lower_hop_range suggests they are in
     CREATE. Not used here; only single-hop MATCH patterns are issued.

Once these are confirmed live, the TWO marked call sites
(`get_current_memories_for_user` and `get_related_entities`) can be
collapsed into single queries — see the TODO comments there.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Adapter layer — ASSUMPTION: replace this with your real HydraDB client.
# Every query in this file is issued through HydraDBClient.execute(), so if
# your actual driver has a different call shape, this is the only class that
# needs to change.
# ---------------------------------------------------------------------------


class HydraDBClient:
    """Thin adapter around the real HydraDB client.

    ASSUMPTION (unverified): the underlying driver exposes
        execute(cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]
    where each returned dict maps RETURN column names (e.g. "m.id",
    "m.content") to values, mirroring QueryColumn naming seen in
    lower_match_return_rows (projection_column_name).

    Replace `self._conn` and `execute()` with your actual driver calls.
    """

    def __init__(self, conn: Any):
        self._conn = conn

    def execute(self, cypher: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        params = params or {}
        # REPLACE with actual driver call, e.g.:
        #   return self._conn.run(cypher, params).to_list()
        return self._conn.execute(cypher, params)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> float:
    return time.time()


@dataclass
class User:
    id: str
    name: str
    created_at: float = field(default_factory=_now)


@dataclass
class Session:
    id: str
    user_id: str
    started_at: float = field(default_factory=_now)


@dataclass
class Message:
    id: str
    session_id: str
    role: str
    text: str
    ts: float = field(default_factory=_now)


@dataclass
class Memory:
    id: str
    content: str
    ts: float = field(default_factory=_now)
    valid: bool = True


@dataclass
class Entity:
    id: str
    name: str
    type: str


# ---------------------------------------------------------------------------
# Storage layer
# ---------------------------------------------------------------------------


class HydraStorage:
    """Node/edge writes and retrieval queries for the HydraDB memory schema."""

    def __init__(self, client: HydraDBClient):
        self.client = client

    # -- Node creation (Phase 2) -------------------------------------------
    # All single-node CREATE with parameterized properties — confirmed
    # supported (relationship_properties / node properties both go through
    # the same parameterized-map path in the engine).

    def create_user(self, name: str) -> User:
        user = User(id=_new_id(), name=name)
        self.client.execute(
            "CREATE (u:User {id: $id, name: $name, created_at: $created_at})",
            {"id": user.id, "name": user.name, "created_at": user.created_at},
        )
        return user

    def create_session(self, user_id: str, started_at: float = None) -> Session:
        session = Session(id=_new_id(), user_id=user_id,
                          started_at=_now() if started_at is None else started_at)
        self.client.execute(
            "CREATE (s:Session {id: $id, user_id: $user_id, started_at: $started_at})",
            {"id": session.id, "user_id": session.user_id, "started_at": session.started_at},
        )
        return session

    def create_message(self, session_id: str, role: str, text: str, ts: float = None) -> Message:
        message = Message(id=_new_id(), session_id=session_id, role=role, text=text,
                          ts=_now() if ts is None else ts)
        self.client.execute(
            "CREATE (m:Message {id: $id, session_id: $session_id, role: $role, "
            "text: $text, ts: $ts})",
            {
                "id": message.id,
                "session_id": message.session_id,
                "role": message.role,
                "text": message.text,
                "ts": message.ts,
            },
        )
        return message

    def create_memory(self, content: str, ts: float = None) -> Memory:
        memory = Memory(id=_new_id(), content=content,
                        ts=_now() if ts is None else ts)
        self.client.execute(
            "CREATE (m:Memory {id: $id, content: $content, ts: $ts, valid: $valid})",
            {"id": memory.id, "content": memory.content, "ts": memory.ts, "valid": memory.valid},
        )
        return memory

    def create_entity(self, name: str, entity_type: str) -> Entity:
        entity = Entity(id=_new_id(), name=name, type=entity_type)
        self.client.execute(
            "CREATE (e:Entity {id: $id, name: $name, type: $type})",
            {"id": entity.id, "name": entity.name, "type": entity.type},
        )
        return entity

    # -- Relationship creation (Phase 3) ------------------------------------
    # Each is its own MATCH ... CREATE, one-hop only, exactly one rel type —
    # both confirmed hard requirements of lower_create_edge_path.

    def link_has_memory(self, user_id: str, memory_id: str) -> None:
        self.client.execute(
            "MATCH (u:User {id: $user_id}), (m:Memory {id: $memory_id}) "
            "CREATE (u)-[:HAS_MEMORY {ts: $ts}]->(m)",
            {"user_id": user_id, "memory_id": memory_id, "ts": _now()},
        )

    def link_mentions(self, memory_id: str, entity_id: str, confidence: float = 1.0) -> None:
        self.client.execute(
            "MATCH (m:Memory {id: $memory_id}), (e:Entity {id: $entity_id}) "
            "CREATE (m)-[:MENTIONS {confidence: $confidence}]->(e)",
            {"memory_id": memory_id, "entity_id": entity_id, "confidence": confidence},
        )

    def link_supersedes(self, new_memory_id: str, old_memory_id: str) -> None:
        """Direction convention: newer -[:SUPERSEDES]-> older.

        This lets "current" be defined as "no incoming SUPERSEDES edge" and
        lets a chain be walked forward from any memory to its full
        replacement history with single-hop MATCHes.
        """
        self.client.execute(
            "MATCH (new:Memory {id: $new_id}), (old:Memory {id: $old_id}) "
            "CREATE (new)-[:SUPERSEDES {ts: $ts}]->(old)",
            {"new_id": new_memory_id, "old_id": old_memory_id, "ts": _now()},
        )
        # Keep the superseded node's own `valid` flag in sync so simple
        # property-only queries can also filter without a graph walk.
        self.client.execute(
            "MATCH (old:Memory {id: $old_id}) SET old.valid = false",
            {"old_id": old_memory_id},
        )

    def link_occurred_in(self, memory_id: str, session_id: str) -> None:
        self.client.execute(
            "MATCH (m:Memory {id: $memory_id}), (s:Session {id: $session_id}) "
            "CREATE (m)-[:OCCURRED_IN]->(s)",
            {"memory_id": memory_id, "session_id": session_id},
        )

    def link_related_to(self, entity_a_id: str, entity_b_id: str, weight: float = 1.0) -> None:
        self.client.execute(
            "MATCH (a:Entity {id: $a_id}), (b:Entity {id: $b_id}) "
            "CREATE (a)-[:RELATED_TO {weight: $weight}]->(b)",
            {"a_id": entity_a_id, "b_id": entity_b_id, "weight": weight},
        )

    # -- Retrieval (Phase 4/5) ------------------------------------------------

    def get_memories_for_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """All memories for a user, newest first. Does NOT exclude
        superseded memories — see get_current_memories_for_user for that."""
        return self.client.execute(
            "MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:Memory) "
            "RETURN m.id, m.content, m.ts, m.valid "
            "ORDER BY m.ts DESC "
            "LIMIT $limit",
            {"user_id": user_id, "limit": limit},
        )

    def get_current_memories_for_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Memories for a user with superseded versions excluded.

        LIVE-TEST TODO: if EXISTS{}/anti-join predicates turn out to be
        supported, this can become a single query:

            MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:Memory)
            WHERE NOT EXISTS { MATCH (:Memory)-[:SUPERSEDES]->(m) }
            RETURN m.id, m.content, m.ts
            ORDER BY m.ts DESC LIMIT $limit

        Until that's confirmed, use the two-query client-side exclusion
        below, which only relies on confirmed grammar (property returns,
        no subqueries).
        """
        all_memories = self.get_memories_for_user(user_id, limit=limit * 4)

        superseded_rows = self.client.execute(
            "MATCH (:Memory)-[:SUPERSEDES]->(old:Memory) RETURN old.id",
            {},
        )
        superseded_ids = {row["old.id"] for row in superseded_rows}

        current = [m for m in all_memories if m["m.id"] not in superseded_ids]
        return current[:limit]

    def get_supersedes_chain(self, memory_id: str) -> list[dict[str, Any]]:
        """Walk the full replacement history for a memory, oldest last.

        Single-hop MATCH per step since multi-hop variable-length MATCH
        traversal is unconfirmed (see module docstring, item 2). Walks the
        chain from the client side, one hop per round trip.
        """
        chain = []
        current_id = memory_id
        seen = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            rows = self.client.execute(
                "MATCH (m:Memory {id: $id}) RETURN m.id, m.content, m.ts",
                {"id": current_id},
            )
            if not rows:
                break
            chain.append(rows[0])

            next_rows = self.client.execute(
                "MATCH (m:Memory {id: $id})-[:SUPERSEDES]->(old:Memory) "
                "RETURN old.id",
                {"id": current_id},
            )
            current_id = next_rows[0]["old.id"] if next_rows else None
        return chain

    def get_entities_for_memory(self, memory_id: str) -> list[dict[str, Any]]:
        return self.client.execute(
            "MATCH (m:Memory {id: $memory_id})-[:MENTIONS]->(e:Entity) "
            "RETURN e.id, e.name, e.type",
            {"memory_id": memory_id},
        )

    def get_related_entities(self, entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """One-hop RELATED_TO expansion.

        LIVE-TEST TODO: if the engine's MATCH supports undirected patterns
        or *1..N variable-length paths in row queries (unconfirmed — see
        module docstring item 2), this can expand to multi-hop relatedness
        in one query, e.g.:

            MATCH (a:Entity {id: $entity_id})-[:RELATED_TO*1..2]-(b:Entity)
            RETURN DISTINCT b.id, b.name, b.type LIMIT $limit

        Until confirmed, only single-hop directed expansion is issued here.
        """
        return self.client.execute(
            "MATCH (a:Entity {id: $entity_id})-[r:RELATED_TO]->(b:Entity) "
            "RETURN b.id, b.name, b.type, r.weight "
            "ORDER BY r.weight DESC "
            "LIMIT $limit",
            {"entity_id": entity_id, "limit": limit},
        )

    # -- Evidence retrieval (Phase 6) ----------------------------------------

    def get_evidence_for_memory(self, memory_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Original Messages that back a Memory, via OCCURRED_IN -> Session,
        filtered to messages at or before the memory's timestamp, most
        recent first.

        Pipelined MATCH (confirmed supported: lowers_multi_match_row_query_
        as_pattern_pipeline) plus a WHERE predicate combining bindings from
        two separate MATCH clauses (confirmed: predicates AND-combine
        across match_clauses in lower_match_return_rows).
        """
        # Fetch the memory's own timestamp and session first, since WITH is
        # pass-through only (no filtering) and RETURN only projects
        # <binding>.<property> — a single-shot join needs both bindings
        # in-scope at once, so this is a straightforward two-MATCH pipeline.
        session_rows = self.client.execute(
            "MATCH (m:Memory {id: $memory_id})-[:OCCURRED_IN]->(s:Session) "
            "RETURN s.id, m.ts",
            {"memory_id": memory_id},
        )
        if not session_rows:
            return []
        session_id = session_rows[0]["s.id"]
        memory_ts = session_rows[0]["m.ts"]

        return self.client.execute(
            "MATCH (msg:Message {session_id: $session_id}) "
            "WHERE msg.ts <= $memory_ts "
            "RETURN msg.id, msg.text, msg.role, msg.ts "
            "ORDER BY msg.ts DESC "
            "LIMIT $limit",
            {"session_id": session_id, "memory_ts": memory_ts, "limit": limit},
        )

    def get_session_messages(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        return self.client.execute(
            "MATCH (msg:Message {session_id: $session_id}) "
            "RETURN msg.id, msg.role, msg.text, msg.ts "
            "ORDER BY msg.ts ASC "
            "LIMIT $limit",
            {"session_id": session_id, "limit": limit},
        )
