"""Person 3 x Member 2 — integrated demo.

Member 2 stores facts in HydraDB (fake client offline), retrieves them
per question, and Person 3 reasons over them. Run:

    python demo_integration.py
"""

import sys

from member2.fake_client import FakeConn
from member2.storage import HydraDBClient, HydraStorage
from memory.reasoning import ReasoningEngine
from memory.integration import answer_from_storage

from member2.retrieve import retrieve

engine = ReasoningEngine()

print("=" * 72)
print("PERSON 3 + MEMBER 2 — INTEGRATED (HydraDB retrieval -> reasoning)")
print("=" * 72)
print("Note: this demo uses the in-memory fake client (deterministic).")
print("For REAL HydraDB persistence run: python demo_live_persistence.py")
print()

conn = FakeConn()
storage = HydraStorage(HydraDBClient(conn))
user = storage.create_user("Dheeraj")


def add_entity_memory(session, predicate_verb, entity, ent_type, content, ts, valid=True):
    """Helper: message + memory + entity + links, mirroring member2's flow."""
    msg = storage.create_message(session.id, "user", f"I {predicate_verb} {entity} lately")
    msg.ts = ts
    conn.nodes["Message"][msg.id]["ts"] = ts

    mem = storage.create_memory(content)
    mem.ts = ts
    mem.valid = valid
    conn.nodes["Memory"][mem.id]["ts"] = ts
    conn.nodes["Memory"][mem.id]["valid"] = valid

    storage.link_has_memory(user.id, mem.id)
    storage.link_occurred_in(mem.id, session.id)

    existing = [e for e in conn.nodes.get("Entity", {}).values() if e["name"] == entity]
    ent_id = existing[0]["id"] if existing else storage.create_entity(entity, ent_type).id
    storage.link_mentions(mem.id, ent_id)
    return mem


def supersede(new_mem_id, old_mem_id):
    storage.link_supersedes(new_mem_id, old_mem_id)
    conn.nodes["Memory"][old_mem_id]["valid"] = False


# ---- Editor timeline (member 2's spec example) -------------------------
s5 = storage.create_session(user.id)
add_entity_memory(s5, "been using", "VS Code", "editor", "User uses VS Code as their editor", 1000)
s20 = storage.create_session(user.id)
m_cursor = add_entity_memory(s20, "been using", "Cursor", "editor", "User uses Cursor as their editor", 1010)
m_vscode = [m for m in conn.nodes["Memory"].values() if "VS Code" in m["content"]][0]
supersede(m_cursor.id, m_vscode["id"])
s35 = storage.create_session(user.id)
m_vscode2 = add_entity_memory(s35, "been using", "VS Code", "editor", "User uses VS Code as their editor", 1020)
supersede(m_vscode2.id, m_cursor.id)

# ---- Car ownership timeline --------------------------------------------
s1 = storage.create_session(user.id)
m_honda = add_entity_memory(s1, "bought a", "Honda", "car", "User owns Honda car", 2000)
s2 = storage.create_session(user.id)
m_toyota = add_entity_memory(s2, "bought a", "Toyota", "car", "User owns Toyota", 2010)
supersede(m_toyota.id, m_honda.id)

# ---- Static profile -----------------------------------------------------
s3 = storage.create_session(user.id)
add_entity_memory(s3, "live in", "Pune", "city", "User lives in Pune", 3000)

questions = [
    "What editor am I currently using?",
    "What editor did I previously use?",
    "Did I ever use Cursor?",
    "What was my first editor?",
    "How has my editor changed over time?",
    "What car do I currently own?",
    "What car did I own before?",
    "Where do I live?",
    "What is my favorite editor?",
]

for q in questions:
    res = answer_from_storage(engine, storage, q, user_id=user.id)
    status = "ABSTAIN" if res["abstained"] else "ANSWER"
    print(f"\n[{status}] {q}")
    print(f"  answer:     {res['answer']}")
    print(f"  confidence: {res['confidence']}")
    print(f"  evidence:   {res['evidence']}")
    try:
        timeline = retrieve(storage, q)["timeline"]
    except Exception:
        timeline = []
    if timeline:
        tl = ", ".join(f"{t['session_id']}:{t['content']}" for t in timeline)
        print(f"  timeline:   {tl}")