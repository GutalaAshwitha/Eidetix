import unittest
from memory.reasoning import ReasoningEngine


def mem(session, pred, obj, ts, text=None, superseded=False, sim=0.8):
    return {
        "subject": "user",
        "predicate": pred,
        "object": obj,
        "text": text or f"User {pred} {obj}",
        "timestamp": ts,
        "session_id": session,
        "is_superseded": superseded,
        "similarity_score": sim,
    }


class TestReasoningEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ReasoningEngine()

    # ---------------------------------------------------------------- #
    # Spec Example 1 — current fact
    # ---------------------------------------------------------------- #
    def test_current_fact(self):
        memories = [
            mem("session_1", "uses", "React", 1700000000),
            mem("session_20", "uses", "Vue", 1705000000, superseded=True),
            mem("session_35", "uses", "React", 1710000000),
        ]
        res = self.engine.answer("What framework am I currently using?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("React", res["answer"])
        self.assertIn("session_35", res["evidence"])
        self.assertGreaterEqual(res["confidence"], 0.5)

    # ---------------------------------------------------------------- #
    # Spec Example 2 — historical fact / ever
    # ---------------------------------------------------------------- #
    def test_historical_ever(self):
        memories = [
            mem("session_1", "uses", "React", 1700000000),
            mem("session_20", "uses", "Vue", 1705000000, superseded=True),
            mem("session_35", "uses", "React", 1710000000),
        ]
        res = self.engine.answer("Did I ever use Vue?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("Yes", res["answer"])
        self.assertIn("session_20", res["evidence"])

    def test_previous_value(self):
        memories = [
            mem("session_1", "uses", "React", 1700000000),
            mem("session_20", "uses", "Vue", 1705000000, superseded=True),
            mem("session_35", "uses", "React", 1710000000),
        ]
        res = self.engine.answer("What framework did I previously use?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("Vue", res["answer"])
        self.assertIn("session_20", res["evidence"])

    def test_first_value(self):
        memories = [
            mem("session_1", "uses", "React", 1700000000),
            mem("session_20", "uses", "Vue", 1705000000, superseded=True),
        ]
        res = self.engine.answer("What was the first framework I used?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("React", res["answer"])

    def test_change_timeline(self):
        memories = [
            mem("session_1", "uses", "React", 1700000000),
            mem("session_20", "uses", "Vue", 1705000000, superseded=True),
            mem("session_35", "uses", "React", 1710000000),
        ]
        res = self.engine.answer("How has my framework changed over time?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("React", res["answer"])
        self.assertIn("Vue", res["answer"])

    # ---------------------------------------------------------------- #
    # Spec Example 3 — abstention
    # ---------------------------------------------------------------- #
    def test_abstention_favorite_movie(self):
        # Unrelated facts, realistic low embedding similarity.
        memories = [
            mem("session_1", "lives_in", "Pune", 1700000000, sim=0.12),
            mem("session_2", "uses", "Python", 1701000000, sim=0.18),
        ]
        res = self.engine.answer("What is my favorite movie?", memories)
        self.assertTrue(res["abstained"])
        self.assertIn("enough evidence", res["answer"].lower())
        self.assertEqual(res["evidence"], [])
        self.assertLess(res["confidence"], 0.28)

    def test_abstention_empty_memories(self):
        res = self.engine.answer("Where does the user live?", [])
        self.assertTrue(res["abstained"])
        self.assertEqual(res["confidence"], 0.0)

    def test_abstention_low_similarity(self):
        memories = [
            mem("s1", "lives_in", "Pune", 1700000000, sim=0.05),
        ]
        res = self.engine.answer("What is the user's favorite football team?", memories)
        self.assertTrue(res["abstained"])

    def test_abstention_property_question_high_sim_unrelated(self):
        # Even with a HIGH embedding score, a property question ("favorite
        # movie") must abstain if the property is never stated in any fact.
        memories = [
            mem("session_1", "uses", "React", 1700000000, sim=0.85),
            mem("session_2", "uses", "Vue", 1701000000, sim=0.85),
        ]
        res = self.engine.answer("What is my favorite movie?", memories)
        self.assertTrue(res["abstained"])
        self.assertIn("enough evidence", res["answer"].lower())
        self.assertEqual(res["evidence"], [])

    # ---------------------------------------------------------------- #
    # Overwrites + conflicts
    # ---------------------------------------------------------------- #
    def test_overwritten_is_handled(self):
        # No supersession flag, but chronological order shows an overwrite.
        memories = [
            mem("s_old", "works_at", "TechCorp", 1700000000),
            mem("s_new", "works_at", "DataWorks", 1710000000),
        ]
        res = self.engine.answer("Where does the user currently work?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("DataWorks", res["answer"])
        self.assertIn("s_new", res["evidence"])

    def test_conflicting_active_facts(self):
        # Same session, two contradictory statements -> real conflict.
        memories = [
            mem("s1", "lives_in", "Pune", 1700000000),
            mem("s1", "lives_in", "Mumbai", 1700000000),
        ]
        res = self.engine.answer("Where does the user currently live?", memories)
        self.assertTrue(res["abstained"])
        self.assertIn("Conflicting", res["answer"])
        self.assertEqual(len(res["evidence"]), 1)

    # ---------------------------------------------------------------- #
    # Multi-session synthesis (two-hop style)
    # ---------------------------------------------------------------- #
    def test_two_hop_synthesis(self):
        memories = [
            mem("s1", "lives_in", "Pune", 1700000000),
            mem("s2", "works_at", "TechCorp", 1701000000, sim=0.5),
        ]
        res = self.engine.answer("Where does the user live and work?", memories)
        self.assertFalse(res["abstained"])
        self.assertIn("Pune", res["answer"])
        self.assertGreaterEqual(len(res["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()