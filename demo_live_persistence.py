"""Person 3 x Member 2 — REAL HydraDB persistence demo.

Proves the full chain against the LIVE dev node (:18443):
  write (CREATE) -> retrieve (MATCH) -> reason (Person 3)

Run the node first (see hydradb/start_dev_node.sh), then:
    python demo_live_persistence.py
"""

import sys

from member2.hydra_client import live_storage
from member2.retrieve import retrieve
from memory.reasoning import ReasoningEngine
from memory.integration import answer_from_storage

engine = ReasoningEngine()
print("=" * 72)
print("PERSON 3 + MEMBER 2 — LIVE HydraDB round-trip")
print("=" * 72)

storage = live_storage()
print(f"backend: {type(storage.client).__name__}\n")

user = storage.create_user("Dheeraj")
print(f"created user: {user.name} ({user.id})")

# -- write one session + memory + entity + links -------------------------
sess = storage.create_session(user.id)
print(f"created session: {sess.id}")

msg = storage.create_message(sess.id, "user", "I've been using VS Code lately")
print(f"created message: {msg.text}")

mem = storage.create_memory("User uses VS Code as their editor")
print(f"created memory: {mem.content}")

entity = storage.create_entity("VS Code", "editor")
print(f"created entity: {entity.name} ({entity.type})")

storage.link_has_memory(user.id, mem.id)
storage.link_occurred_in(mem.id, sess.id)
storage.link_mentions(mem.id, entity.id)
print("linked HAS_MEMORY + OCCURRED_IN + MENTIONS")

# -- retrieve from the REAL graph ----------------------------------------
print("\n-- retrieve('What editor am I currently using?') --")
result = retrieve(storage, "What editor am I currently using?")
print(f"memories:  {[(m['m.content'], m['m.ts']) for m in result['memories']]}")
print(f"evidence:  {[(str(e['memory_id'])[:8], str(e['session_id'])[:8] if e['session_id'] else None, [m['msg.text'] for m in e['messages']]) for e in result['evidence']]}")
print(f"timeline:  {[(str(t['session_id'])[:8] if t['session_id'] else None, t['content']) for t in result['timeline']]}")

# -- reason over it -------------------------------------------------------
print("\n-- Person 3 reasoning --")
res = answer_from_storage(engine, storage, "What editor am I currently using?", user_id=user.id)
print(f"  answer:     {res['answer']}")
print(f"  confidence: {res['confidence']}")
print(f"  evidence:   {res['evidence']}")

res = answer_from_storage(engine, storage, "What is my favorite editor?", user_id=user.id)
print(f"  answer:     {res['answer']}")
print(f"  abstained:  {res['abstained']}")

# -- prove it persisted: read back in a fresh retrieve --------------------
# NOTE: the /tmp/sgk-local store persists across runs, so earlier runs'
# memories are still there (CREATE is not idempotent, per AGENTS.md).
print("\n-- read-back check (same client, fresh query) --")
fresh = retrieve(storage, "What editor am I currently using?")
assert len(fresh["memories"]) >= 1, "read-back failed"
print(f"PASS: {len(fresh['memories'])} editor memory/memories live in the HydraDB graph")
print("(To reset the graph: stop the node and rerun hydradb/start_dev_node.sh)")