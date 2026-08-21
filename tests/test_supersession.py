import unittest
from memory.pipeline import MemoryPipeline


class TestSupersession(unittest.TestCase):
    def test_fact_supersession_honda_to_toyota(self):
        pipeline = MemoryPipeline()

        s1 = [{"role": "user", "content": "I bought a Honda car."}]
        pipeline.ingest_session("sess_car_1", s1, "2024/01/01 10:00", 1704103200)

        s8 = [{"role": "user", "content": "I sold my Honda and bought a Toyota."}]
        pipeline.ingest_session("sess_car_8", s8, "2024/05/01 10:00", 1714557600)

        res_current = pipeline.answer_question("What car does the user currently own?")
        self.assertFalse(res_current["should_abstain"])
        self.assertIn("toyota", res_current["answer"].lower())

        res_prev = pipeline.answer_question("What car did the user previously own?")
        self.assertFalse(res_prev["should_abstain"])
        self.assertIn("honda", res_prev["answer"].lower())


if __name__ == "__main__":
    unittest.main()
