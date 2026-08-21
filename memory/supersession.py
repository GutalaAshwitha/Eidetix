from typing import Dict, List, Tuple, Any

try:
    from .normalization import FactNormalizer
except ImportError:
    from memory.normalization import FactNormalizer


class SupersessionEngine:
    def __init__(self, normalizer: FactNormalizer = None):
        self.normalizer = normalizer or FactNormalizer()

    def find_superseded_facts(
        self, new_fact: Dict[str, Any], existing_facts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        superseded = []
        new_norm_entity = self.normalizer.normalize_entity(
            new_fact.get("object", "") or new_fact.get("subject", "")
        )
        new_pred = self.normalizer.normalize_predicate(new_fact.get("predicate", ""))
        new_ts = new_fact.get("timestamp", 0)

        for old in existing_facts:
            if old.get("is_superseded"):
                continue

            old_norm_entity = self.normalizer.normalize_entity(
                old.get("object", "") or old.get("subject", "")
            )
            old_pred = self.normalizer.normalize_predicate(old.get("predicate", ""))
            old_ts = old.get("timestamp", 0)

            # Only newer facts can supersede older facts
            if new_ts <= old_ts:
                continue

            # Same entity category (e.g. car)
            if new_norm_entity == old_norm_entity:
                # Scenario 1: Same predicate update (e.g., owns Honda -> owns Toyota)
                if new_pred == old_pred and new_pred in ["owns", "lives_in", "works_at"]:
                    if new_fact.get("object", "").lower() != old.get("object", "").lower():
                        superseded.append(old)

                # Scenario 2: Action supersedes ownership (e.g., sold Honda supersedes owns Honda)
                elif new_pred == "sold" and old_pred == "owns":
                    old_obj = old.get("object", "").lower()
                    new_text = new_fact.get("text", "").lower()
                    if old_obj in new_text or old_norm_entity == "car":
                        superseded.append(old)

        return superseded
