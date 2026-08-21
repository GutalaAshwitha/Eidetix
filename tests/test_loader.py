"""Tests for member2/loader.py — Member 1 -> Member 2 handoff."""

import sys
import unittest
from datetime import datetime

sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\gutalaashwitha\hackhydra")

from member2.fake_client import FakeConn
from member2.storage import HydraDBClient, HydraStorage
from member2.loader import (
    load_memories,
    normalize_memory_record,
    parse_timestamp,
)
from member2.retrieve import retrieve
from memory.reasoning import ReasoningEngine
from memory.integration import answer_from_storage

ENGINE = ReasoningEngine()


def _fake_storage():
    return HydraStorage(HydraDBClient(FakeConn()))


class TestSchemaAdapter(unittest.TestCase):
    def test_member1_schema(self):
        rec = normalize_memory_record(
            {
                "fact": "user owns Honda car",
                "category": "owns",
                "session_id": "s1",
                "timestamp": "2023/04/10 (Mon) 17:50",
                "source_message": "I own a Honda car",
                "source_location": "answer_x_0",
                "status": "superseded",
            }
        )
        self.assertEqual(rec["subject"], "user")
        self.assertEqual(rec["predicate"], "owns")
        self.assertEqual(rec["object"], "Honda car")
        self.assertTrue(rec["is_superseded"])
        self.assertEqual(rec["session_id"], "s1")
        self.assertEqual(rec["category"], "owns")
        self.assertEqual(rec["source_message"], "I own a Honda car")
        self.assertGreater(rec["timestamp"], 0)

    def test_internal_schema(self):
        rec = normalize_memory_record(
            {
                "subject": "user",
                "predicate": "lives_in",
                "object": "Pune",
                "text": "User lives in Pune",
                "timestamp": 1000,
                "session_id": "s2",
                "is_superseded": False,
            }
        )
        self.assertEqual(rec["predicate"], "lives_in")
        self.assertEqual(rec["object"], "Pune")
        self.assertEqual(rec["timestamp"], 1000.0)
        self.assertFalse(rec["is_superseded"])

    def test_parse_timestamp_formats(self):
        self.assertEqual(parse_timestamp(1234), 1234.0)
        self.assertEqual(
            parse_timestamp("2023/04/10 (Mon) 17:50"),
            datetime(2023, 4, 10, 17, 50).timestamp(),
        )
        self.assertEqual(
            parse_timestamp("2023-04-10 17:50:00"),
            datetime(2023, 4, 10, 17, 50).timestamp(),
        )
        self.assertEqual(parse_timestamp(None), 0.0)


class TestLoadMemories(unittest.TestCase):
    def setUp(self):
        self.storage = _fake_storage()

    def test_load_builds_graph_and_supersedes(self):
        records = [
            {
                "subject": "user", "predicate": "owns", "object": "Honda car",
                "text": "User owns Honda car", "timestamp": 1000,
                "session_id": "s1", "source_message": "I own a Honda car",
            },
            {
                "subject": "user", "predicate": "owns", "object": "Toyota car",
                "text": "User owns Toyota car", "timestamp": 2000,
                "session_id": "s2", "source_message": "I bought a Toyota car",
            },
            {
                "subject": "user", "predicate": "lives_in", "object": "Pune",
                "text": "User lives in Pune", "timestamp": 1500,
                "session_id": "s1",
            },
        ]
        stats = load_memories(self.storage, records, user_name="TestUser")

        self.assertEqual(stats.n_sessions, 2)
        self.assertEqual(stats.n_memories, 3)
        self.assertEqual(stats.n_entities, 3)
        self.assertEqual(stats.n_superseded, 1)

        # honda must be invalid, toyota valid
        conn = self.storage.client._conn
        honda = next(n for n in conn.nodes["Memory"].values()
                     if n["content"] == "User owns Honda car")
        toyota = next(n for n in conn.nodes["Memory"].values()
                      if n["content"] == "User owns Toyota car")
        self.assertFalse(honda["valid"])
        self.assertTrue(toyota["valid"])

        # SUPERSEDES edge toyota -> honda exists
        superseded = [(s, d) for (t, s, d, p) in conn.edges if t == "SUPERSEDES"]
        self.assertIn((toyota["id"], honda["id"]), superseded)

        # entities got MENTIONS links and RELATED_TO (both owned objects in
        # the same session? no — different sessions; honda in s1, toyota in s2)
        mentions = [d for (t, s, d, p) in conn.edges if t == "MENTIONS"]
        self.assertEqual(len(mentions), 3)

    def test_retrieval_and_reasoning_over_loaded_graph(self):
        records = [
            {"fact": "user owns Honda car", "category": "owns",
             "session_id": "s1", "timestamp": 1000,
             "source_message": "I own a Honda car", "status": "superseded"},
            {"fact": "user owns Toyota car", "category": "owns",
             "session_id": "s2", "timestamp": 2000,
             "source_message": "I bought a Toyota car", "status": "current"},
        ]
        stats = load_memories(self.storage, records, user_name="CarUser")

        result = retrieve(self.storage, "What car do I currently own?")
        contents = [m["m.content"] for m in result["memories"]]
        self.assertEqual(len(contents), 2, contents)  # both versions on the timeline
        self.assertEqual(len(result["timeline"]), 2)
        self.assertTrue(any("Honda" in c for c in contents))
        self.assertTrue(any("Toyota" in c for c in contents))

        res = answer_from_storage(
            ENGINE, self.storage, "What car do I currently own?", user_id=stats.user_id
        )
        self.assertFalse(res["abstained"], res)
        self.assertTrue("Toyota" in res["answer"], res["answer"])

    def test_explicit_superseded_flag_without_chain(self):
        # same value restated, but Member 1 flagged the old one superseded
        records = [
            {"fact": "user works at Google", "category": "works_at",
             "session_id": "s1", "timestamp": 1000,
             "source_message": "I work at Google", "status": "superseded"},
            {"fact": "user works at Google", "category": "works_at",
             "session_id": "s2", "timestamp": 2000,
             "source_message": "I work at Google", "status": "current"},
        ]
        stats = load_memories(self.storage, records, user_name="WorkUser")
        conn = self.storage.client._conn
        old = next(n for n in conn.nodes["Memory"].values() if n["ts"] == 1000)
        self.assertFalse(old["valid"])
        self.assertEqual(stats.n_superseded, 1)


if __name__ == "__main__":
    unittest.main()