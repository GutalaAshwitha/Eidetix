import json
from .storage import HydraStorage, HydraDBClient
from .retrieve import retrieve
from .fake_client import FakeConn

conn = FakeConn()
client = HydraDBClient(conn)
storage = HydraStorage(client)

# Set up: one user, three sessions across time, each mentioning an editor
user = storage.create_user("Dheeraj")

def make_session_with_editor(editor_name, ts_offset):
    session = storage.create_session(user.id)
    msg = storage.create_message(session.id, "user", f"I've been using {editor_name} lately")
    msg.ts = 1000 + ts_offset
    conn.nodes["Message"][msg.id]["ts"] = msg.ts

    memory = storage.create_memory(f"User uses {editor_name} as their editor")
    memory.ts = 1000 + ts_offset
    conn.nodes["Memory"][memory.id]["ts"] = memory.ts

    storage.link_has_memory(user.id, memory.id)
    storage.link_occurred_in(memory.id, session.id)

    # entity: reuse if already created
    existing = [e for e in conn.nodes.get("Entity", {}).values() if e["name"] == editor_name]
    if existing:
        entity_id = existing[0]["id"]
    else:
        entity = storage.create_entity(editor_name, "editor")
        entity_id = entity.id
    storage.link_mentions(memory.id, entity_id)
    return session.id

s5 = make_session_with_editor("VS Code", 0)
s20 = make_session_with_editor("Cursor", 10)
s35 = make_session_with_editor("VS Code", 20)

result = retrieve(storage, "What editor am I currently using?")
print(json.dumps(result, indent=2))
