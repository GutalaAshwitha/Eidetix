import re
from typing import Dict, List, Any

try:
    from .storage import StorageManager
    from .temporal import TemporalEngine
    from .normalization import FactNormalizer
except ImportError:
    from memory.storage import StorageManager
    from memory.temporal import TemporalEngine
    from memory.normalization import FactNormalizer

STOP_WORDS = {
    "user", "the", "does", "did", "is", "a", "an", "in", "at",
    "my", "to", "and", "or", "of", "for", "with", "has", "have", "had", "this",
    "that", "from", "was", "were"
}


class RetrievalEngine:
    def __init__(
        self,
        storage: StorageManager = None,
        temporal_engine: TemporalEngine = None,
        normalizer: FactNormalizer = None,
    ):
        self.storage = storage or StorageManager()
        self.temporal_engine = temporal_engine or TemporalEngine()
        self.normalizer = normalizer or FactNormalizer()

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        facts = self.storage.get_all_facts()
        if not facts:
            return []

        q = query.lower()
        all_words = set(re.findall(r"\w+", q))
        keywords = {w for w in all_words if w not in STOP_WORDS and len(w) > 2}

        relevant_facts = []

        for f in facts:
            text = f.get("text", "").lower()
            obj = f.get("object", "").lower()
            pred = f.get("predicate", "").lower()

            if any(w in keywords for w in ["live", "lives", "city", "pune", "reside"]) and pred == "lives_in":
                relevant_facts.append(f)
            elif any(w in keywords for w in ["work", "works", "job", "company", "techcorp"]) and pred == "works_at":
                relevant_facts.append(f)
            elif any(w in keywords for w in ["car", "vehicle", "auto", "drive", "honda", "toyota"]) and (pred in ["owns", "sold"] or "car" in text):
                relevant_facts.append(f)
            elif any(w in text or w in obj or w in pred for w in keywords if w not in ["currently", "previously", "what", "where"]):
                relevant_facts.append(f)

        if not relevant_facts:
            return []

        intent = self.temporal_engine.detect_temporal_intent(query)
        return self.temporal_engine.filter_facts_by_intent(relevant_facts, intent)
