"""Tests for memory/evaluator.py — benchmark runner, normalization, metrics."""

import os
import sys
import unittest

sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\gutalaashwitha\hackhydra")

_REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

from memory.evaluator import (
    answers_match,
    compute_metrics,
    evaluate_instances,
    load_dataset,
    normalize_text,
    select_subset,
)

# Synthetic oracle-shaped instances. Sessions use sentences the rule-based
# FactExtractor recognises (owns / lives_in / favorite...).
CAR_HISTORY = [
    {"role": "user", "content": "I own a Honda car"},
    {"role": "assistant", "content": "Nice car!"},
]
TOYOTA_HISTORY = [
    {"role": "user", "content": "I bought a Toyota car"},
    {"role": "assistant", "content": "Great choice!"},
]
PUNE_HISTORY = [
    {"role": "user", "content": "I live in Pune"},
    {"role": "assistant", "content": "Lovely city!"},
]
NO_INFO = [
    {"role": "user", "content": "I like hiking on weekends"},
    {"role": "assistant", "content": "Fun!"},
]

INSTANCES = [
    {
        "question_id": "syn_1",
        "question_type": "knowledge-update",
        "question": "What car do I currently own?",
        "answer": "Toyota",
        "question_date": "2023/03/10 (Fri) 10:00",
        "haystack_dates": ["2023/01/05 (Thu) 09:00", "2023/03/10 (Fri) 10:00"],
        "haystack_session_ids": ["s1", "s2"],
        "haystack_sessions": [CAR_HISTORY, TOYOTA_HISTORY],
        "answer_session_ids": ["s2"],
    },
    {
        "question_id": "syn_2",
        "question_type": "single-session-user",
        "question": "Where do I live?",
        "answer": "Pune",
        "question_date": "2023/02/01 (Wed) 12:00",
        "haystack_dates": ["2023/02/01 (Wed) 12:00"],
        "haystack_session_ids": ["s3"],
        "haystack_sessions": [PUNE_HISTORY],
        "answer_session_ids": ["s3"],
    },
    {
        "question_id": "syn_3",
        "question_type": "single-session-preference",
        "question": "What is my favorite movie?",
        "answer": "The Godfather",
        "question_date": "2023/04/01 (Sat) 20:00",
        "haystack_dates": ["2023/04/01 (Sat) 20:00"],
        "haystack_session_ids": ["s4"],
        "haystack_sessions": [NO_INFO],
        "answer_session_ids": ["s4"],
    },
]


class TestNormalization(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("You are currently using React!"), "you are currently using react")
        self.assertEqual(normalize_text("GPS system not functioning correctly."), "gps system not functioning correctly")

    def test_answers_match(self):
        self.assertTrue(answers_match("You currently own Toyota car.", "Toyota"))
        self.assertTrue(answers_match("You live in Pune.", "Pune"))
        self.assertTrue(answers_match("You use VS Code as your editor", "VS Code"))
        self.assertFalse(answers_match("I don't have enough evidence to answer.", "Toyota"))
        self.assertFalse(answers_match("You own Honda car.", "Toyota"))
        self.assertTrue(answers_match("You used Vue around March.", "Vue"))


class TestDatasetHelpers(unittest.TestCase):
    def test_select_subset_covers_categories(self):
        subset = select_subset(INSTANCES, 2)
        self.assertEqual(len(subset), 2)
        cats = {x["question_type"] for x in subset}
        self.assertGreaterEqual(len(cats), 2)  # round-robin picks different types


class TestEvaluation(unittest.TestCase):
    def test_end_to_end_metrics(self):
        metrics = evaluate_instances(INSTANCES, backend="fake")
        o = metrics["overall"]
        self.assertEqual(o["n"], 3)
        self.assertEqual(o["correct"], 2)      # car + location answered right
        self.assertEqual(o["abstained"], 1)    # favorite movie -> abstain
        self.assertEqual(o["answered"], 2)
        self.assertEqual(o["coverage"], round(2 / 3, 4))
        self.assertEqual(o["precision"], 1.0)

        # categories present
        self.assertIn("knowledge-update", metrics["categories"])
        self.assertIn("single-session-preference", metrics["categories"])

        # per-instance detail
        r1 = next(r for r in metrics["results"] if r["question_id"] == "syn_1")
        self.assertTrue(r1["correct"])
        self.assertFalse(r1["abstained"])
        self.assertIn("Toyota", r1["predicted"])
        self.assertGreaterEqual(r1["memories_ingested"], 2)

        r3 = next(r for r in metrics["results"] if r["question_id"] == "syn_3")
        self.assertTrue(r3["abstained"])
        self.assertFalse(r3["correct"])

    def test_compute_metrics_shape(self):
        results = [
            {"question_id": "a", "category": "c1", "abstained": False, "correct": True},
            {"question_id": "b", "category": "c1", "abstained": False, "correct": False},
            {"question_id": "c", "category": "c2", "abstained": True, "correct": False},
        ]
        m = compute_metrics(results)
        self.assertEqual(m["overall"]["accuracy"], round(1 / 3, 4))
        self.assertEqual(m["overall"]["precision"], 0.5)
        self.assertEqual(m["overall"]["coverage"], round(2 / 3, 4))
        self.assertEqual(m["categories"]["c1"]["n"], 2)
        self.assertEqual(m["categories"]["c2"]["abstained"], 1)

    def test_load_dataset_real_file(self):
        dataset = load_dataset(os.path.join(
            _REPO, "LongMemEval", "data", "longmemeval_oracle.json"))
        self.assertEqual(len(dataset), 500)
        self.assertIn("haystack_sessions", dataset[0])


if __name__ == "__main__":
    unittest.main()