import re
from typing import Dict, List, Tuple, Any

try:
    from .reasoning import ReasoningEngine
except ImportError:
    from memory.reasoning import ReasoningEngine

STOP_WORDS = {
    "user", "the", "does", "did", "is", "a", "an", "in", "at",
    "my", "to", "and", "or", "of", "for", "with", "has", "have", "had", "this",
    "that", "from", "was", "were"
}


class AbstentionEngine:
    """Backward-compatible wrapper around the ReasoningEngine."""

    def __init__(self, threshold: float = 0.28, reasoning_engine: ReasoningEngine = None):
        self.reasoning = reasoning_engine or ReasoningEngine(
            abstention_threshold=threshold
        )

    def evaluate(self, query: str, facts: List[Dict[str, Any]]) -> Tuple[bool, str]:
        return self.reasoning.evaluate(query, facts)

    def answer(self, query: str, facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.reasoning.answer(query, facts)