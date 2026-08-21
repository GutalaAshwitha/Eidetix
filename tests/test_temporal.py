import unittest
from memory.temporal import TemporalEngine


class TestTemporal(unittest.TestCase):
    def test_temporal_intent_detection(self):
        engine = TemporalEngine()
        self.assertEqual(engine.detect_temporal_intent("What car does the user currently own?"), "CURRENT")
        self.assertEqual(engine.detect_temporal_intent("What car did the user previously own?"), "HISTORICAL")
        self.assertEqual(engine.detect_temporal_intent("What was the first car the user bought?"), "FIRST")
        self.assertEqual(engine.detect_temporal_intent("Did the user ever use Vue?"), "EVER")
        self.assertEqual(engine.detect_temporal_intent("How has the framework changed over time?"), "CHANGE")


if __name__ == "__main__":
    unittest.main()
