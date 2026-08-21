from typing import Dict, List, Any


class TemporalEngine:
    """Detect what point in time a question refers to and slice facts accordingly."""

    # Intent signals ordered by specificity so "first ... currently" style phrasing
    # still resolves to the most precise intent.
    SIGNALS = {
        "FIRST": [
            "first", "earliest", "initial", "originally", "at first",
            "when did you start", "when was your first", "the very first",
        ],
        "EVER": [
            "ever", "have i ever", "did i ever", "has the user ever",
            "did the user ever", "at any point", "at any time",
        ],
        "CHANGE": [
            "change", "changed", "changes", "history", "timeline",
            "over time", "how has", "evolution", "evolve", "evolved",
            "sequence", "transition", "switched", "switch", "switching",
            "increase", "decrease", "increased", "decreased", "increase or decrease",
            "higher", "lower", "more restrictive", "less restrictive",
        ],
        "PREVIOUS": [
            "previously", "previous", "before", "earlier", "former",
            "formerly", "used to", "prior", "before that", "back then",
            "past", "last one before", "before this", "then",
        ],
        "STILL": [
            "still", "do you still", "does the user still",
        ],
        "CURRENT": [
            "currently", "current", "now", "today", "present",
            "right now", "at present", "at the moment", "latest",
            "these days", "these days",
        ],
    }

    @staticmethod
    def detect_temporal_intent(query: str) -> str:
        q = " " + query.lower() + " "
        for intent, signals in TemporalEngine.SIGNALS.items():
            for sig in signals:
                if sig in q:
                    # Backward-compatible name: PREVIOUS == HISTORICAL
                    return "HISTORICAL" if intent == "PREVIOUS" else intent
        return "CURRENT"

    def filter_facts_by_intent(
        self, facts: List[Dict[str, Any]], intent: str
    ) -> List[Dict[str, Any]]:
        sorted_facts = self._chronological(facts)

        if intent == "CURRENT":
            active = [f for f in sorted_facts if not f.get("is_superseded")]
            return active[-1:] if active else sorted_facts[-1:] if sorted_facts else []

        if intent in ("PREVIOUS", "HISTORICAL"):
            superseded = [f for f in sorted_facts if f.get("is_superseded")]
            if superseded:
                return [superseded[-1]]
            if len(sorted_facts) > 1:
                return [sorted_facts[-2]]
            return []

        if intent == "FIRST":
            return sorted_facts[:1] if sorted_facts else []

        if intent == "EVER":
            return sorted_facts

        if intent == "CHANGE":
            return sorted_facts

        if intent == "STILL":
            active = [f for f in sorted_facts if not f.get("is_superseded")]
            return active[-1:] if active else sorted_facts[-1:] if sorted_facts else []

        return sorted_facts

    @staticmethod
    def _chronological(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # At equal timestamps, positive state facts (owns/lives_in/uses...) beat
        # transition events (sold/left/quit...), so "sold my Honda" never wins
        # against "owns Toyota" recorded in the same session.
        NEGATIVE_PREDS = {
            "sold", "left", "quit", "moved_from", "stopped", "no_longer",
            "abandoned", "switched_from", "moved_out", "resigned", "gave_up",
            "returned_from", "sold_to", "ended", "deleted", "removed",
            "donated", "lost",
        }
        return sorted(
            facts,
            key=lambda f: (
                int(f.get("timestamp", 0) or 0),
                0 if str(f.get("predicate", "")).lower() in NEGATIVE_PREDS else 1,
                int(f.get("id", 0) or 0),
            ),
        )