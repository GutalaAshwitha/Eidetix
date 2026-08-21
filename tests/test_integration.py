"""Integration tests: Member 2 retrieval -> Person 3 reasoning."""

import sys
import unittest

sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\gutalaashwitha\hackhydra")

from member2.fake_client import FakeConn
from member2.storage import HydraDBClient, HydraStorage
from member2.retrieve import retrieve
from memory.reasoning import ReasoningEngine
from memory.integration import (
    parse_memory_content,
    to_reasoning_memories,
    ask_with_retrieval,
)

ENGINE = ReasoningEngine()


def build_storage():
    conn = FakeConn()
    storage = HydraStorage(HydraDBClient(conn))
    user = storage.create_user("Dheeraj")

    def add_entity_memory(session, entity, ent_type, content, ts, valid=True):
        msg = storage.create_message(session.id, "user", f"Using {entity} lately")
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

    def supersede(new_id, old_id):
        storage.link_supersedes(new_id, old_id)
        conn.nodes["Memory"][old_id]["valid"] = False

    s5 = storage.create_session(user.id)
    add_entity_memory(s5, "VS Code", "editor", "User uses VS Code as their editor", 1000)
    s20 = storage.create_session(user.id)
    m_cursor = add_entity_memory(s20, "Cursor", "editor", "User uses Cursor as their editor", 1010)
    supersede(m_cursor.id, [m for m in conn.nodes["Memory"].values() if "VS Code" in m["content"]][0]["id"])
    s35 = storage.create_session(user.id)
    m_vscode2 = add_entity_memory(s35, "VS Code", "editor", "User uses VS Code as their editor", 1020)
    supersede(m_vscode2.id, m_cursor.id)

    s1 = storage.create_session(user.id)
    m_honda = add_entity_memory(s1, "Honda", "car", "User owns Honda car", 2000)
    s2 = storage.create_session(user.id)
    m_toyota = add_entity_memory(s2, "Toyota", "car", "User owns Toyota", 2010)
    supersede(m_toyota.id, m_honda.id)

    return conn, storage


class TestParseContent(unittest.TestCase):
    def test_uses_with_role(self):
        p = parse_memory_content("User uses VS Code as their editor")
        self.assertEqual(p, {"subject": "user", "predicate": "uses", "object": "VS Code"})

    def test_owns(self):
        p = parse_memory_content("User owns Toyota")
        self.assertEqual(p["predicate"], "owns")
        self.assertEqual(p["object"], "Toyota")

    def test_lives_in(self):
        p = parse_memory_content("User lives in Pune")
        self.assertEqual(p["predicate"], "lives_in")

    def test_favorite(self):
        p = parse_memory_content("User's favorite movie is Inception")
        self.assertEqual(p["predicate"], "favorite_movie")
        self.assertEqual(p["object"], "Inception")

    def test_unknown_falls_back(self):
        p = parse_memory_content("User reflects on the meaning of life")
        self.assertEqual(p["predicate"], "related_to")

    def test_preference_is_parsed(self):
        p = parse_memory_content("User likes hiking on weekends")
        self.assertEqual(p["predicate"], "likes")
        self.assertEqual(p["object"], "hiking on weekends")


class TestAdapter(unittest.TestCase):
    def test_fields_mapped(self):
        conn, storage = build_storage()
        result = retrieve(storage, "What editor am I currently using?")
        mems = to_reasoning_memories(result)
        self.assertTrue(len(mems) >= 3)
        fields = {"subject", "predicate", "object", "text", "timestamp", "session_id", "is_superseded"}
        for m in mems:
            self.assertTrue(fields.issubset(m.keys()))
            self.assertEqual(m["subject"], "user")
        # chronological
        ts = [m["timestamp"] for m in mems]
        self.assertEqual(ts, sorted(ts))


class TestIntegratedPipeline(unittest.TestCase):
    def test_current_editor(self):
        conn, storage = build_storage()
        result = retrieve(storage, "What editor am I currently using?")
        res = ask_with_retrieval(ENGINE, result, "What editor am I currently using?")
        self.assertFalse(res["abstained"])
        self.assertIn("VS Code", res["answer"])
        self.assertEqual(len(res["evidence"]), 1)
        self.assertTrue(any(e["session_id"] is not None for e in result["evidence"]))

    def test_previous_editor(self):
        conn, storage = build_storage()
        result = retrieve(storage, "What editor did I previously use?")
        res = ask_with_retrieval(ENGINE, result, "What editor did I previously use?")
        self.assertFalse(res["abstained"])
        self.assertIn("Cursor", res["answer"])

    def test_ever_cursor(self):
        conn, storage = build_storage()
        result = retrieve(storage, "Did I ever use Cursor?")
        res = ask_with_retrieval(ENGINE, result, "Did I ever use Cursor?")
        self.assertFalse(res["abstained"])
        self.assertIn("Cursor", res["answer"])

    def test_current_car(self):
        conn, storage = build_storage()
        result = retrieve(storage, "What car do I currently own?")
        res = ask_with_retrieval(ENGINE, result, "What car do I currently own?")
        self.assertFalse(res["abstained"])
        self.assertIn("Toyota", res["answer"])

    def test_property_abstention(self):
        conn, storage = build_storage()
        result = retrieve(storage, "What is my favorite editor?")
        res = ask_with_retrieval(ENGINE, result, "What is my favorite editor?")
        self.assertTrue(res["abstained"])

    def test_evidence_sessions_present(self):
        conn, storage = build_storage()
        result = retrieve(storage, "What editor am I currently using?")
        res = ask_with_retrieval(ENGINE, result, "What editor am I currently using?")
        self.assertTrue(res["evidence"])


if __name__ == "__main__":
    unittest.main()