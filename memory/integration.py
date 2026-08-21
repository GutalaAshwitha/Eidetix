"""Integration layer: Member 2 (HydraDB retrieval) + Person 3 (reasoning).

Member 2's retrieve() returns memories as:
    {"id", "content", "ts", "valid"}
    content is a normalized string like "User uses VS Code as their editor".

Person 3's ReasoningEngine expects:
    {"subject", "predicate", "object", "text",
     "timestamp", "session_id", "is_superseded", "similarity_score"}

This module bridges the two: parses content back into structured
subject/predicate/object, joins the session_id from the evidence block,
maps valid -> is_superseded, and feeds the result straight into the engine.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .reasoning import ReasoningEngine

try:
    from member2.retrieve import retrieve, MemoryRetriever
except ImportError:
    from ..member2.retrieve import retrieve, MemoryRetriever


# ---------------------------------------------------------------------------
# Content parsing: "User uses VS Code as their editor" -> (subject, pred, obj)
# ---------------------------------------------------------------------------

_PATTERNS = [
    (re.compile(r"^user\s+uses\s+(.+?)\s+as\s+their\s+\w+\s*$", re.I), "uses"),
    (re.compile(r"^user\s+is\s+using\s+(.+?)\s*$", re.I), "currently_using"),
    (re.compile(r"^user\s+(?:currently )?uses?\s+(.+?)\s*$", re.I), "uses"),
    (re.compile(r"^user\s+owns?\s+(?:a )?(.+?)\s*$", re.I), "owns"),
    (re.compile(r"^user\s+(?:currently )?has\s+(?:a|an)\s+(.+?)\s*$", re.I), "owns"),
    (re.compile(r"^user\s+lives in\s+(.+?)\s*$", re.I), "lives_in"),
    (re.compile(r"^user\s+works at\s+(.+?)\s*$", re.I), "works_at"),
    (re.compile(r"^user\s+is\s+working at\s+(.+?)\s*$", re.I), "works_at"),
    (re.compile(r"^user\s+works on\s+(.+?)\s*$", re.I), "works_on"),
    (re.compile(r"^user\s+is\s+working on\s+(.+?)\s*$", re.I), "works_on"),
    (re.compile(r"^user\s+bought\s+(?:a )?(.+?)\s*$", re.I), "acquired"),
    (re.compile(r"^user\s+got\s+(?:a )?(.+?)\s*$", re.I), "acquired"),
    (re.compile(r"^user\s+(?:has|recently )?read\s+(.+?)\s*$", re.I), "read"),
    (re.compile(r"^user\s+(?:recently )?finished\s+(.+?)\s*$", re.I), "read"),
    (re.compile(r"^user\s+started\s+(.+?)\s*$", re.I), "started"),
    (re.compile(r"^user\s+made\s+(?:a )?(.+?)\s*$", re.I), "made"),
    (re.compile(r"^user\s+attended\s+(?:the )?(.+?)\s*$", re.I), "attended"),
    (re.compile(r"^user\s+listens? to\s+(.+?)\s*$", re.I), "listens_to"),
    (re.compile(r"^user\s+(?:is )?interested in\s+(.+?)\s*$", re.I), "interested_in"),
    (re.compile(r"^user\s+(?:is )?researching\s+(.+?)\s*$", re.I), "researches"),
    (re.compile(r"^user\s+(?:wants|plans|intends|is thinking|is planning|aims)\s+to\s+(.+?)\s*$", re.I), "wants"),
    (re.compile(r"^user\s+(?:prefers?|loves|likes)\s+(?:a )?(.+?)\s*$", re.I), "likes"),
    (re.compile(r"^user\s+is\s+considering\s+(?:getting )?(.+?)\s*$", re.I), "considering"),
    (re.compile(r"^user\s+tracks\s+(.+?)\s*$", re.I), "tracks"),
    (re.compile(r"^user\s+(?:is )?in\s+the\s+(\d+)(?:th|st|nd|rd)?\s+year\s+of\s+study\s*$", re.I), "year_of_study"),
]

_FAVORITE = re.compile(r"^user's\s+favorite\s+(\w[\w ]*?)\s+is\s+(.+?)\s*$", re.I)


def parse_memory_content(content: str) -> Dict[str, str]:
    """Turn Member 2's normalized content string into a structured memory.

    Returns {"subject", "predicate", "object"}. Unknown forms fall back to a
    generic "related_to" predicate with the full content as the object, so
    nothing is ever dropped from the timeline.
    """
    c = (content or "").strip().rstrip(".")
    m = _FAVORITE.match(c)
    if m:
        category = m.group(1).strip().replace(" ", "_")
        return {
            "subject": "user",
            "predicate": f"favorite_{category}",
            "object": m.group(2).strip(),
        }
    for pattern, pred in _PATTERNS:
        m = pattern.match(c)
        if m:
            return {
                "subject": "user",
                "predicate": pred,
                "object": m.group(1).strip(),
            }
    return {"subject": "user", "predicate": "related_to", "object": c}


# ---------------------------------------------------------------------------
# Adapter: retrieve() output -> ReasoningEngine input
# ---------------------------------------------------------------------------


def _m_key(row: Dict[str, Any], name: str, default: Any = None) -> Any:
    """Member 2's fake/real client returns projection keys ("m.content").
    Accept both that and plain keys for robustness."""
    if name in row:
        return row[name]
    return row.get(f"m.{name}", default)


def to_reasoning_memories(
    retrieve_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Convert Member 2's {memories, evidence, timeline} into the schema
    ReasoningEngine.answer() expects. Keeps ALL versions (superseded +
    current) so the engine can do temporal reasoning itself."""
    session_map = {
        e.get("memory_id"): e.get("session_id")
        for e in retrieve_result.get("evidence", [])
        if e.get("memory_id")
    }
    memories = []
    for m in retrieve_result.get("memories", []):
        content = _m_key(m, "content") or ""
        parsed = parse_memory_content(content)
        memories.append(
            {
                "subject": parsed["subject"],
                "predicate": parsed["predicate"],
                "object": parsed["object"],
                "text": content,
                "timestamp": float(_m_key(m, "ts") or 0.0),
                "session_id": session_map.get(_m_key(m, "id")),
                "is_superseded": not bool(_m_key(m, "valid", True)),
            }
        )
    memories.sort(key=lambda f: f["timestamp"])
    return memories


def ask_with_retrieval(
    engine: ReasoningEngine,
    retrieve_result: Dict[str, Any],
    question: str,
) -> Dict[str, Any]:
    """Full pipeline: Member 2 retrieve() output -> Person 3 answer."""
    memories = to_reasoning_memories(retrieve_result)
    return engine.answer(question, memories)


def answer_from_storage(
    engine: ReasoningEngine,
    storage: Any,
    question: str,
    user_id: str = None,
    evidence_limit: int = 5,
) -> Dict[str, Any]:
    """End-to-end convenience: storage -> retrieve -> reason.

    `storage` is any Member 2 HydraStorage instance (real or fake client).
    When entity matching finds no memories (e.g. "Where do I live?" names
    no entity), falls back to the user's full memory set and lets the
    reasoning engine score relevance itself.
    """
    result = retrieve(storage, question, evidence_limit=evidence_limit)
    if not result.get("memories") and user_id:
        retriever = MemoryRetriever(storage)
        rows = storage.get_memories_for_user(user_id, limit=500)
        memories = [
            {"id": r["m.id"], "content": r["m.content"], "ts": r["m.ts"], "valid": r["m.valid"]}
            for r in rows
        ]
        result["memories"] = memories
        result["timeline"] = [
            {"session_id": None, "ts": r["m.ts"], "content": r["m.content"]}
            for r in rows
        ]
        result["evidence"] = []
        for mem in memories:
            session = retriever._session_for_memory(mem["id"])
            result["evidence"].append(
                {
                    "memory_id": mem["id"],
                    "session_id": session["s.id"] if session else None,
                    "messages": [],
                }
            )
    return ask_with_retrieval(engine, result, question)


def build_retrieval_demo(storage: Any, engine: ReasoningEngine) -> Dict[str, Any]:
    """Populate storage with the classic editor scenario and run the
    integrated pipeline across every temporal intent."""
    from .storage import HydraStorage
    from .fake_client import FakeConn

    if not isinstance(storage, HydraStorage):
        raise TypeError("storage must be a member2.HydraStorage instance")

    user = storage.create_user("Dheeraj")

    def add_memory(session, editor_name, ts, valid=True):
        msg = storage.create_message(session.id, "user", f"I've been using {editor_name} lately")
        msg.ts = ts
        conn = storage.client._conn
        conn.nodes["Message"][msg.id]["ts"] = ts
        mem = storage.create_memory(f"User uses {editor_name} as their editor")
        mem.ts = ts
        mem.valid = valid
        conn.nodes["Memory"][mem.id]["ts"] = ts
        conn.nodes["Memory"][mem.id]["valid"] = valid
        storage.link_has_memory(user.id, mem.id)
        storage.link_occurred_in(mem.id, session.id)
        existing = [e for e in conn.nodes.get("Entity", {}).values() if e["name"] == editor_name]
        entity_id = existing[0]["id"] if existing else storage.create_entity(editor_name, "editor").id
        storage.link_mentions(mem.id, entity_id)
        if not valid:
            # mark older versions superseded by the newest
            older = [m for m in conn.nodes["Memory"].values()
                     if m["content"].endswith(f"{editor_name} as their editor") and m["id"] != mem.id]
            for o in older:
                storage.link_supersedes(mem.id, o["id"])

    s5 = storage.create_session(user.id)
    add_memory(s5, "VS Code", 1000)
    s20 = storage.create_session(user.id)
    add_memory(s20, "Cursor", 1010)
    s35 = storage.create_session(user.id)
    add_memory(s35, "VS Code", 1020)

    questions = [
        "What editor am I currently using?",
        "What editor did I previously use?",
        "Did I ever use Cursor?",
        "What was my first editor?",
        "How has my editor changed over time?",
        "What is my favorite editor?",
    ]
    return {q: ask_with_retrieval(engine, retrieve(storage, q), q) for q in questions}