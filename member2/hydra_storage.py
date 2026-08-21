"""HydraStorage subclass that writes through the REAL HydraDB HTTP API.

The live engine (confirmed on the dev node) is stricter than the fake client:

  - node id must be an INTEGER (string ids are rejected)
  - CREATE must be a one-hop edge pattern with inline endpoints:
        CREATE (a:Label {id: 1, ...})-[:TYPE {props}]->(b:Label {id: 2, ...})
  - MATCH-then-CREATE is rejected ("write query is not executable by the
    mutation engine") -> links are written as pure inline CREATE edges
    using the ids we generated.
  - SET on a matched node is supported (used to mark superseded memories).

Every create_*/link_* override below emits exactly that shape. Retrieval
queries from storage.py / retrieve.py already match this grammar (label or
id predicates, WHERE, ORDER BY, LIMIT), so they run unchanged.
"""

from __future__ import annotations

import random
import time
from typing import Any, Optional

from .storage import (
    HydraStorage,
    User,
    Session,
    Message,
    Memory,
    Entity,
)

ROOT_ID = 0
BOOT_ID = 2**31 - 1  # anchor partner for the very first CREATE


class HydraHttpStorage(HydraStorage):
    def __init__(self, client: Any):
        super().__init__(client)
        # Random base so ids are unique across process runs (the store
        # persists in /tmp; reusing ids would collide with old nodes).
        self._seq = random.randint(1_000_000_000, 2**31 - 2)

    def _next_id(self) -> int:
        self._seq += 1
        return self._seq

    def _ensure_root(self) -> None:
        rows = self.client.execute("MATCH (root {id: 0}) RETURN root.id")
        if not rows:
            self.client.execute(
                f"CREATE (root {{id: {ROOT_ID}}})-[:ROOT]->(boot {{id: {BOOT_ID}}})"
            )

    # -- Node creation: anchor every node to the root via a one-hop edge ----

    def create_user(self, name: str) -> User:
        self._ensure_root()
        uid = self._next_id()
        self.client.execute(
            "CREATE (root {id: $root_id})-[:HAS_USER]->(u:User {id: $id, name: $name, created_at: $created_at})",
            {"root_id": ROOT_ID, "id": uid, "name": name, "created_at": time.time()},
        )
        return User(id=uid, name=name)

    def create_session(self, user_id: int, started_at: float = None) -> Session:
        self._ensure_root()
        sid = self._next_id()
        ts = time.time() if started_at is None else started_at
        self.client.execute(
            "CREATE (root {id: $root_id})-[:HAS_SESSION]->(s:Session {id: $id, user_id: $user_id, started_at: $started_at})",
            {"root_id": ROOT_ID, "id": sid, "user_id": user_id, "started_at": ts},
        )
        return Session(id=sid, user_id=user_id, started_at=ts)

    def create_message(self, session_id: int, role: str, text: str, ts: float = None) -> Message:
        self._ensure_root()
        mid = self._next_id()
        msg_ts = time.time() if ts is None else ts
        self.client.execute(
            "CREATE (root {id: $root_id})-[:HAS_MESSAGE]->(m:Message {id: $id, session_id: $session_id, role: $role, text: $text, ts: $ts})",
            {"root_id": ROOT_ID, "id": mid, "session_id": session_id,
             "role": role, "text": text, "ts": msg_ts},
        )
        return Message(id=mid, session_id=session_id, role=role, text=text, ts=msg_ts)

    def create_memory(self, content: str, ts: float = None) -> Memory:
        self._ensure_root()
        mid = self._next_id()
        mem_ts = time.time() if ts is None else ts
        self.client.execute(
            "CREATE (root {id: $root_id})-[:HAS_MEMORY]->(m:Memory {id: $id, content: $content, ts: $ts, valid: $valid})",
            {"root_id": ROOT_ID, "id": mid, "content": content, "ts": mem_ts, "valid": True},
        )
        return Memory(id=mid, content=content, ts=mem_ts, valid=True)

    def create_entity(self, name: str, entity_type: str) -> Entity:
        self._ensure_root()
        eid = self._next_id()
        self.client.execute(
            "CREATE (root {id: $root_id})-[:HAS_ENTITY]->(e:Entity {id: $id, name: $name, type: $type})",
            {"root_id": ROOT_ID, "id": eid, "name": name, "type": entity_type},
        )
        return Entity(id=eid, name=name, type=entity_type)

    # -- Links: pure inline CREATE edges between known ids ------------------

    def link_has_memory(self, user_id: int, memory_id: int) -> None:
        self.client.execute(
            "CREATE (u:User {id: $user_id})-[:HAS_MEMORY {ts: $ts}]->(m:Memory {id: $memory_id})",
            {"user_id": user_id, "memory_id": memory_id, "ts": time.time()},
        )

    def link_mentions(self, memory_id: int, entity_id: int, confidence: float = 1.0) -> None:
        self.client.execute(
            "CREATE (m:Memory {id: $memory_id})-[:MENTIONS {confidence: $confidence}]->(e:Entity {id: $entity_id})",
            {"memory_id": memory_id, "entity_id": entity_id, "confidence": confidence},
        )

    def link_supersedes(self, new_memory_id: int, old_memory_id: int) -> None:
        self.client.execute(
            "CREATE (new:Memory {id: $new_id})-[:SUPERSEDES {ts: $ts}]->(old:Memory {id: $old_id})",
            {"new_id": new_memory_id, "old_id": old_memory_id, "ts": time.time()},
        )
        self.client.execute(
            "MATCH (old:Memory {id: $old_id}) SET old.valid = false",
            {"old_id": old_memory_id},
        )

    def link_occurred_in(self, memory_id: int, session_id: int) -> None:
        self.client.execute(
            "CREATE (m:Memory {id: $memory_id})-[:OCCURRED_IN]->(s:Session {id: $session_id})",
            {"memory_id": memory_id, "session_id": session_id},
        )

    def link_related_to(self, entity_a_id: int, entity_b_id: int, weight: float = 1.0) -> None:
        self.client.execute(
            "CREATE (a:Entity {id: $a_id})-[:RELATED_TO {weight: $weight}]->(b:Entity {id: $b_id})",
            {"a_id": entity_a_id, "b_id": entity_b_id, "weight": weight},
        )

    def get_memories_for_user(self, user_id: int, limit: int = 50):
        return super().get_memories_for_user(user_id, limit=limit)

    def get_evidence_for_memory(self, memory_id: int, limit: int = 10):
        return super().get_evidence_for_memory(memory_id, limit=limit)

    def get_session_messages(self, session_id: int, limit: int = 200):
        return super().get_session_messages(session_id, limit=limit)