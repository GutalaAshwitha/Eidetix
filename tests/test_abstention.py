import unittest
from memory.pipeline import MemoryPipeline


class TestAbstention(unittest.TestCase):
    def test_abstention_on_unrecorded_information(self):
        pipeline = MemoryPipeline()

        turns = [
            {"role": "user", "content": "I live in Pune."}
        ]
        pipeline.ingest_session("sess_pune", turns, "2024/01/01 10:00", 1704103200)

        res = pipeline.answer_question("What is the user's favorite football team?")
        self.assertTrue(res["should_abstain"])
        self.assertIn("enough evidence", res["answer"].lower())


if __name__ == "__main__":
    unittest.main()
