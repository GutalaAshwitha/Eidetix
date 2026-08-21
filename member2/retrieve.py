"""
retrieve.py — Member 2 deliverable: retrieve(question) -> {memories, evidence, timeline}

Sits on top of storage.py (HydraStorage / HydraDBClient). Implements:
  - relevance matching: question -> candidate Entity nodes
  - connected/related expansion: Entity -[:RELATED_TO]-> Entity (1 hop)
  - memory lookup: Entity <-[:MENTIONS]- Memory
  - evidence: Memory -[:OCCURRED_IN]-> Session -> Message (original source)
  - timeline: every matched memory placed on a chronological, per-session axis

DESIGN NOTE — why entity matching happens client-side:
  We confirmed RETURN only projects <binding>.<property>, count(*), an
  aggregate, or a bare node id — and we never confirmed the predicate
  grammar (lower_row_predicate) supports substring/CONTAINS matching, only
  that WHERE clauses exist and combine via AND across MATCH clauses. Rather
  than risk an unsupported-predicate error at query time, this file fetches
  all Entity nodes (cheap for a hackathon-scale graph) and does fuzzy
  matching in Python. If your teammate confirms CONTAINS/regex predicates
  work live, `_match_entities` is the only function that needs to change.
"""

from __future__ import annotations

import re
from typing import Any

from .storage import HydraStorage


_STOPWORDS = {
    "what", "which", "who", "whom", "is", "are", "am", "was", "were", "the",
    "a", "an", "i", "my", "me", "currently", "using", "use", "do", "does",
    "did", "in", "on", "at", "to", "for", "of", "and", "or", "that", "this",
    "how", "when", "where", "why", "with", "right", "now",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9_+#.]+", text.lower()) if t not in _STOPWORDS]


class MemoryRetriever:
    def __init__(self, storage: HydraStorage):
        self.storage = storage

    # -- Step 1: question -> candidate entities -----------------------------

    def _match_entities(self, question: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fuzzy-match question tokens against Entity.name, client-side.

        Returns entities ranked by number of overlapping tokens (simple,
        deterministic, no embeddings required — swap this out for a real
        similarity/embedding lookup later without touching anything else
        in this file).
        """
        tokens = set(_tokenize(question))
        if not tokens:
            return []

        all_entities = self.storage.client.execute(
            "MATCH (e:Entity) RETURN e.id, e.name, e.type",
            {},
        )

        scored = []
        for row in all_entities:
            name_tokens = set(_tokenize(row["e.name"]))
            type_tokens = set(_tokenize(row.get("e.type", "")))
            overlap = len(tokens & name_tokens) + len(tokens & type_tokens)
            # also credit partial/substring hits (e.g. question says
            # "editor", entity name is "VS Code" with type "editor")
            if overlap == 0:
                name_lower = row["e.name"].lower()
                if any(tok in name_lower or name_lower in tok for tok in tokens):
                    overlap = 1
            if overlap > 0:
                scored.append((overlap, row))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _, row in scored[:limit]]

    # -- Step 2: connected/related expansion (1 hop, confirmed-safe) --------

    def _expand_related(self, entity_ids: list[str]) -> list[str]:
        expanded = set(entity_ids)
        for eid in entity_ids:
            related = self.storage.get_related_entities(eid, limit=10)
            for row in related:
                expanded.add(row["b.id"])
        return list(expanded)

    # -- Step 3: entities -> memories ----------------------------------------

    def _memories_for_entities(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        seen_ids: set[str] = set()
        memories: list[dict[str, Any]] = []
        for eid in entity_ids:
            rows = self.storage.client.execute(
                "MATCH (m:Memory)-[:MENTIONS]->(e:Entity {id: $entity_id}) "
                "RETURN m.id, m.content, m.ts, m.valid",
                {"entity_id": eid},
            )
            for row in rows:
                if row["m.id"] not in seen_ids:
                    seen_ids.add(row["m.id"])
                    memories.append(row)
        memories.sort(key=lambda r: r["m.ts"])
        return memories

    # -- Step 4: memory -> session + evidence messages -----------------------

    def _session_for_memory(self, memory_id: str) -> dict[str, Any] | None:
        rows = self.storage.client.execute(
            "MATCH (m:Memory {id: $memory_id})-[:OCCURRED_IN]->(s:Session) "
            "RETURN s.id, s.user_id, s.started_at",
            {"memory_id": memory_id},
        )
        return rows[0] if rows else None

    # -- Public API -----------------------------------------------------------

    def retrieve(self, question: str, evidence_limit: int = 5) -> dict[str, Any]:
        """
        Returns:
        {
          "memories": [ {id, content, ts, valid}, ... ]        # chronological
          "evidence": [ {memory_id, session_id, messages: [...]}, ... ]
          "timeline": [ {session_id, ts, content}, ... ]        # chronological
        }
        """
        matched_entities = self._match_entities(question)
        if not matched_entities:
            return {"memories": [], "evidence": [], "timeline": []}

        entity_ids = [e["e.id"] for e in matched_entities]
        expanded_entity_ids = self._expand_related(entity_ids)

        memories = self._memories_for_entities(expanded_entity_ids)

        evidence = []
        timeline = []
        for mem in memories:
            memory_id = mem["m.id"]
            session = self._session_for_memory(memory_id)
            session_id = session["s.id"] if session else None

            source_messages = self.storage.get_evidence_for_memory(
                memory_id, limit=evidence_limit
            )
            evidence.append(
                {
                    "memory_id": memory_id,
                    "session_id": session_id,
                    "messages": source_messages,
                }
            )

            timeline.append(
                {
                    "session_id": session_id,
                    "ts": mem["m.ts"],
                    "content": mem["m.content"],
                }
            )

        timeline.sort(key=lambda t: t["ts"])

        return {
            "memories": memories,
            "evidence": evidence,
            "timeline": timeline,
        }


def retrieve(storage: HydraStorage, question: str, evidence_limit: int = 5) -> dict[str, Any]:
    """Module-level convenience wrapper matching the deliverable signature
    `retrieve(question)` — pass your HydraStorage instance in once at call
    time, or partial-apply it, e.g.:

        from functools import partial
        retrieve_fn = partial(retrieve, my_storage)
        result = retrieve_fn("What editor am I currently using?")
    """
    return MemoryRetriever(storage).retrieve(question, evidence_limit=evidence_limit)
