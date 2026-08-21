"""Live HydraDB round-trip tests. Skip automatically when the dev node
(:18443) is not running (start it with hydradb/start_dev_node.sh)."""

import sys
import unittest

sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\gutalaashwitha\hackhydra")

from member2.hydra_client import live_storage
from member2.retrieve import retrieve
from memory.reasoning import ReasoningEngine
from memory.integration import answer_from_storage

ENGINE = ReasoningEngine()


def _live_available():
    try:
        storage = live_storage()
        storage.client.execute("MATCH (root {id: 0}) RETURN root.id")
        return True
    except Exception:
        return False


@unittest.skipUnless(_live_available(), "HydraDB dev node not running on :18443")
class TestLiveHydra(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = live_storage()
        cls.user = cls.storage.create_user("LiveTestUser")

    def test_write_and_roundtrip(self):
        st = self.storage
        sess = st.create_session(self.user.id)
        msg = st.create_message(sess.id, "user", "I've been using React lately")
        mem = st.create_memory("User uses React as their editor")
        ent = st.create_entity("React", "editor")
        st.link_has_memory(self.user.id, mem.id)
        st.link_occurred_in(mem.id, sess.id)
        st.link_mentions(mem.id, ent.id)

        result = retrieve(st, "What editor am I currently using?")
        contents = [m["m.content"] for m in result["memories"]]
        self.assertTrue(any("React" in c for c in contents), f"no React memory: {contents}")

    def test_supersede_flag_persists(self):
        st = self.storage
        sess = st.create_session(self.user.id)
        old = st.create_memory("User owns Honda car")
        new = st.create_memory("User owns Toyota")
        st.link_occurred_in(old.id, sess.id)
        st.link_occurred_in(new.id, sess.id)
        st.link_supersedes(new.id, old.id)

        rows = st.client.execute(
            "MATCH (old:Memory {id: $old_id}) RETURN old.valid",
            {"old_id": old.id},
        )
        self.assertFalse(bool(rows[0]["old.valid"]), "superseded memory should be invalid")

    def test_reasoning_over_live(self):
        st = self.storage
        res = answer_from_storage(
            ENGINE, st, "What editor am I currently using?", user_id=self.user.id
        )
        self.assertIsInstance(res["answer"], str)
        self.assertIn("abstained", res)
        self.assertIn("confidence", res)
        self.assertIn("evidence", res)


if __name__ == "__main__":
    unittest.main()