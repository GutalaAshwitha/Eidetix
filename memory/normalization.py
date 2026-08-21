from typing import Dict, Any


class FactNormalizer:
    @staticmethod
    def normalize_entity(entity_str: str) -> str:
        s = entity_str.lower().strip()
        if any(w in s for w in ["car", "honda", "toyota", "vehicle", "auto", "sedan", "suv"]):
            return "car"
        if any(w in s for w in ["city", "town", "home", "pune", "mumbai", "delhi", "tokyo"]):
            return "location"
        if any(w in s for w in ["dog", "cat", "pet"]):
            return "pet"
        if any(w in s for w in ["job", "work", "company", "office"]):
            return "workplace"
        return s

    @staticmethod
    def normalize_predicate(pred_str: str) -> str:
        p = pred_str.lower().strip()
        if p in ["bought", "purchased", "owns", "got", "drives", "has"]:
            return "owns"
        if p in ["sold", "got_rid_of", "traded_in"]:
            return "sold"
        if p in ["lives_in", "moved_to", "resides_in"]:
            return "lives_in"
        if p in ["works_at", "employed_at", "joined"]:
            return "works_at"
        return p

    def normalize_fact(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        norm_fact = dict(fact)
        norm_fact["normalized_entity"] = self.normalize_entity(fact.get("object", "") or fact.get("subject", ""))
        norm_fact["normalized_predicate"] = self.normalize_predicate(fact.get("predicate", ""))
        return norm_fact
