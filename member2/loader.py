"""member2/loader.py — bulk loader: memories.json -> HydraDB graph.

This closes the Member 1 -> Member 2 handoff. It accepts BOTH:

  1. Member 1's extraction schema (assignment spec):
       {"fact", "category", "session_id", "timestamp",
        "source_message", "source_location", "status"}   status in {current, superseded}

  2. The internal schema the rest of the system already consumes:
       {"subject", "predicate", "object", "text", "timestamp",
        "session_id", "is_superseded", "source_message", "category"}

and materialises it into a real HydraStorage graph:

  User -[:HAS_MEMORY]-> Memory -[:OCCURRED_IN]-> Session
                          Memory -[:MENTIONS]-> Entity
                          Memory -[:SUPERSEDES]-> Memory   (newer -> older)
                          Entity -[:RELATED_TO]-> Entity   (co-occur in a session)

`status` / `is_superseded` is honoured (no re-derivation), and the
SUPERSEDES edges + `valid=false` flags are written exactly the way
Member 2's retrieval layer expects them.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .storage import HydraStorage

try:  # pragma: no cover - mirrors integration.py's import guard
    from memory.integration import parse_memory_content
except ImportError:  # pragma: no cover
    from ..memory.integration import parse_memory_content


# ---------------------------------------------------------------------------
# Date/timestamp parsing (LongMemEval dates look like "2023/04/10 (Mon) 17:50")
# ---------------------------------------------------------------------------

_DATE_FORMATS = (
    "%Y/%m/%d (%a) %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def parse_timestamp(value: Any, default: float = 0.0) -> float:
    """Turn an int/float epoch or a human date string into an epoch float."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return default


# ---------------------------------------------------------------------------
# Schema adapter (Member 1's format -> internal format)
# ---------------------------------------------------------------------------


def _split_fact(fact: str) -> Dict[str, str]:
    """Best-effort parse of a free-text fact string into subject/predicate/object.

    Prefers the structured parser, falls back to a generic related_to form so
    nothing is dropped.
    """
    fact = (fact or "").strip()
    if not fact:
        return {"subject": "user", "predicate": "related_to", "object": ""}
    parsed = parse_memory_content(fact)
    if parsed["predicate"] != "related_to":
        return parsed
    # last resort: "user <verb> <rest>" style splitting
    m = re.match(r"^user(?:'s)?\s+(\S+)\s+(.+)$", fact, re.I)
    if m:
        return {"subject": "user", "predicate": m.group(1).lower().rstrip(":"), "object": m.group(2).strip()}
    return {"subject": "user", "predicate": "related_to", "object": fact}


def normalize_memory_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either schema, emit the internal schema used by loader/storage.

    Internal output keys:
      subject, predicate, object, text, timestamp (epoch float),
      session_id (str), category (str), source_message (str),
      is_superseded (bool)
    """
    rec = dict(rec or {})
    # Member 1 ships source_message as a {role, content} turn dict; the loader
    # only needs the text content for the Message node.
    raw_source = rec.get("source_message", rec.get("source", ""))
    if isinstance(raw_source, dict):
        source_message = raw_source.get("content", "") or str(raw_source)
    else:
        source_message = str(raw_source) if raw_source else ""

    out: Dict[str, Any] = {
        "subject": rec.get("subject", "user"),
        "predicate": rec.get("predicate", ""),
        "object": rec.get("object", ""),
        "text": rec.get("text", "") or rec.get("fact", ""),
        "timestamp": parse_timestamp(rec.get("timestamp", rec.get("ts", 0))),
        "session_id": str(rec.get("session_id") or rec.get("sid") or ""),
        "category": rec.get("topic_key") or rec.get("category") or "",
        "source_message": source_message,
        "is_superseded": bool(rec.get("is_superseded", False)),
    }
    if not out["predicate"] or not out["object"]:
        parsed = _split_fact(out["text"])
        out["subject"] = parsed["subject"]
        out["predicate"] = parsed["predicate"]
        out["object"] = parsed["object"]
    # Member 1's status field
    status = str(rec.get("status", "") or "").lower()
    if status in ("superseded", "old", "overwritten", "replaced"):
        out["is_superseded"] = True
    elif status in ("current", "active", "live"):
        out["is_superseded"] = False
    return out


# ---------------------------------------------------------------------------
# Bulk loader
# ---------------------------------------------------------------------------


class LoadStats:
    def __init__(self) -> None:
        self.user_id: Any = None
        self.user_name: str = ""
        self.n_sessions = 0
        self.n_messages = 0
        self.n_memories = 0
        self.n_entities = 0
        self.n_links = 0
        self.n_superseded = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "sessions": self.n_sessions,
            "messages": self.n_messages,
            "memories": self.n_memories,
            "entities": self.n_entities,
            "links": self.n_links,
            "superseded": self.n_superseded,
        }


def load_memories(
    storage: HydraStorage,
    records: List[Dict[str, Any]],
    user_name: str = "User",
    category_entity_type: bool = True,
) -> LoadStats:
    """Load normalized records into the storage graph.

    `records` may be in either Member 1 or internal schema (normalized via
    normalize_memory_record). Returns LoadStats.

    Entity strategy: one Entity per distinct memory OBJECT, typed by the
    memory's category (or "entity" if uncategorised). Memories MENTIONS their
    object entity; entities that co-occur within the same session get
    RELATED_TO edges so retrieval can expand between them.
    """
    stats = LoadStats()
    records = [normalize_memory_record(r) for r in records]
    records = [r for r in records if r["text"] or r["object"]]

    user = storage.create_user(user_name)
    stats.user_id = user.id
    stats.user_name = user_name

    session_map: Dict[str, Any] = {}   # session_id string -> Session node id
    entity_map: Dict[str, Any] = {}    # lower(object) -> entity id
    memory_ids: Dict[Any, int] = {}    # index in records -> memory node id
    memory_by_category: Dict[str, List[tuple]] = {}  # category -> [(ts, idx, obj, mid)]

    # -- pass 1: sessions, messages, memories, entities ---------------------
    seen_msgs: set = set()
    for idx, rec in enumerate(records):
        sid_str = rec["session_id"]
        if sid_str and sid_str not in session_map:
            session = storage.create_session(user.id, started_at=rec["timestamp"])
            session_map[sid_str] = session.id
            stats.n_sessions += 1
        if sid_str and rec["source_message"]:
            msg_key = (sid_str, rec["source_message"])
            if msg_key not in seen_msgs:
                seen_msgs.add(msg_key)
                storage.create_message(session_map[sid_str], "user", rec["source_message"], ts=rec["timestamp"])
                stats.n_messages += 1

        obj = (rec["object"] or "").strip()
        if obj:
            ekey = obj.lower()
            if ekey not in entity_map:
                etype = rec["category"] or "entity"
                ent = storage.create_entity(obj, etype)
                entity_map[ekey] = ent.id
                stats.n_entities += 1

        memory = storage.create_memory(rec["text"] or obj, ts=rec["timestamp"])
        memory_ids[idx] = memory.id
        stats.n_memories += 1

    # -- pass 2: links -------------------------------------------------------
    for idx, rec in enumerate(records):
        mid = memory_ids[idx]

        storage.link_has_memory(user.id, mid)
        stats.n_links += 1

        sid_str = rec["session_id"]
        if sid_str:
            storage.link_occurred_in(mid, session_map[sid_str])
            stats.n_links += 1

        obj = (rec["object"] or "").strip()
        if obj:
            storage.link_mentions(mid, entity_map[obj.lower()])
            stats.n_links += 1

    # -- pass 3: SUPERSEDES chains per category -------------------------------
    # Newest -> older within the same category whenever the value changed.
    by_cat: Dict[str, List[tuple]] = {}
    invalidated: set = set()
    for idx, rec in enumerate(records):
        cat = rec["category"] or rec["predicate"] or "related_to"
        by_cat.setdefault(cat, []).append(
            (rec["timestamp"], idx, (rec["object"] or "").lower(), memory_ids[idx])
        )
    for cat, items in by_cat.items():
        items.sort(key=lambda t: t[0])
        current_obj: Optional[str] = None
        current_mid: Any = None
        for ts, idx, obj, mid in items:
            if current_mid is not None and obj != current_obj:
                storage.link_supersedes(mid, current_mid)
                stats.n_links += 1
                stats.n_superseded += 1
                invalidated.add(current_mid)
            current_obj = obj
            current_mid = mid

    # Honour explicit superseded flags that no chain captured (e.g. same-value
    # re-statements Member 1 marked stale): mark them invalid directly.
    for idx, rec in enumerate(records):
        if rec["is_superseded"] and memory_ids[idx] not in invalidated:
            storage.client.execute(
                "MATCH (m:Memory {id: $old_id}) SET m.valid = false",
                {"old_id": memory_ids[idx]},
            )
            invalidated.add(memory_ids[idx])
            stats.n_superseded += 1

    # -- pass 4: RELATED_TO for entities co-occurring in a session ------------
    session_objects: Dict[Any, set] = {}
    for idx, rec in enumerate(records):
        sid_str = rec["session_id"]
        if not sid_str:
            continue
        obj = (rec["object"] or "").strip().lower()
        if obj:
            session_objects.setdefault(sid_str, set()).add(obj)
    linked: set = set()
    for objs in session_objects.values():
        objs = sorted(objs)
        for i in range(len(objs)):
            for j in range(i + 1, len(objs)):
                a, b = objs[i], objs[j]
                if (a, b) in linked:
                    continue
                storage.link_related_to(entity_map[a], entity_map[b])
                linked.add((a, b))
                linked.add((b, a))
                stats.n_links += 1

    return stats


def memories_from_oracle_instance(
    instance: Dict[str, Any],
    max_sessions: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extract memories from one LongMemEval oracle instance (Member 1 stand-in).

    Uses the local FactExtractor (rule-based, offline). Each fact becomes an
    internal-schema record with session_id / timestamp / source_message so the
    loader can build the full graph. Returns [] when nothing was extracted.
    """
    from memory.extraction import FactExtractor

    extractor = FactExtractor()
    sessions = instance.get("haystack_sessions", []) or []
    dates = instance.get("haystack_dates", []) or []
    ids = instance.get("haystack_session_ids", []) or []

    records: List[Dict[str, Any]] = []
    for i, turns in enumerate(sessions):
        if max_sessions is not None and i >= max_sessions:
            break
        sid = ids[i] if i < len(ids) else f"{instance.get('question_id', 'q')}_s{i}"
        ts = parse_timestamp(dates[i] if i < len(dates) else None)
        facts = extractor.extract_facts(turns, int(ts))
        # source message = the user turn(s) that produced the facts
        source = " | ".join(
            t.get("content", "")
            for t in turns
            if t.get("role", "").lower() == "user" and t.get("content")
        )
        for f in facts:
            records.append(
                {
                    "subject": f.get("subject", "user"),
                    "predicate": f.get("predicate", ""),
                    "object": f.get("object", ""),
                    "text": f.get("text", ""),
                    "timestamp": float(f.get("timestamp") or ts or 0),
                    "session_id": sid,
                    "source_message": source,
                    "category": f.get("category", "") or f.get("predicate", ""),
                }
            )
    return records