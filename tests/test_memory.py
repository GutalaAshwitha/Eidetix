import unittest
from memory.pipeline import MemoryPipeline


class TestMemory(unittest.TestCase):
    def test_end_to_end_memory_ingestion_and_retrieval(self):
        pipeline = MemoryPipeline()

        turns = [
            {"role": "user", "content": "I live in Pune and work at TechCorp."}
        ]
        pipeline.ingest_session("test_s1", turns, "2024/02/01 12:00", 1706788800)

        res_loc = pipeline.answer_question("Where does the user live?")
        self.assertFalse(res_loc["should_abstain"])
        self.assertIn("pune", res_loc["answer"].lower())

        res_work = pipeline.answer_question("Where does the user work?")
        self.assertFalse(res_work["should_abstain"])
        self.assertIn("techcorp", res_work["answer"].lower())


if __name__ == "__main__":
    unittest.main()
