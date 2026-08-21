"""Temporal reasoning + answer/abstention.

This is the reasoning layer. It takes a question and a set of retrieved
candidate memories and decides:

- what the current fact is (vs. historical / overwritten facts),
- whether a fact was overwritten, and by what,
- whether there are conflicts that make the answer ambiguous,
- whether the evidence is strong enough to answer or whether the system
  should abstain instead of hallucinating.

The module is deliberately dependency-free so it can run anywhere (and be
benchmarked on LongMemEval / BEAM without a model call in the loop).
"""

import re
from typing import Dict, List, Any, Tuple

from .normalization import FactNormalizer
from .temporal import TemporalEngine

STOP_WORDS = {
    "user", "the", "does", "did", "is", "are", "a", "an", "in", "at",
    "my", "to", "and", "or", "of", "for", "with", "has", "have", "had", "this",
    "that", "from", "was", "were", "i", "you", "your", "what", "which", "who",
    "where", "when", "how", "why", "am", "be", "been", "on", "it", "its", "do",
    "would", "could", "should", "will", "can", "may", "might", "me", "him",
    "her", "them", "their", "his", "hers", "as", "about", "up", "down", "out",
}

_VERB_MAP = {
    "owns": "owns",
    "lives_in": "lives in",
    "works_at": "works at",
    "has_pet": "has a pet named",
    "uses": "uses",
    "currently_using": "currently uses",
    "currently_working_on": "is currently working on",
    "favorite": "favorite is",
}

_PAST_VERB_MAP = {
    "owns": "owned",
    "lives_in": "lived in",
    "works_at": "worked at",
    "has_pet": "had a pet named",
    "uses": "used",
    "currently_using": "used",
    "currently_working_on": "was working on",
}

_PREFIX_VERB = {
    "favorite": "favorite",
    "likes": "likes",
    "prefers": "prefers",
    "uses": "uses",
}

# Questions asking for a personal property the history may never have stated.
# "What is my favorite movie?" must not be answered from "uses React" merely
# because the embedding score is high -- the property itself was never stated.
_PROPERTY_WORDS = {
    "favorite", "name", "birthday", "age", "phone", "email", "address",
    "anniversary", "surname", "height", "weight", "salary", "hobby",
    "birthplace", "birth", "relationship", "religion", "old",
}

# Preference/property predicates that CAN answer property questions.
_PREFERENCE_PREDICATES = ("favorite", "likes", "prefers", "loves", "hates")

# Property words -> predicates that legitimately establish them.
_PROPERTY_PREDICATE_MAP = {
    "favorite": ("favorite", "likes", "prefers", "loves", "hates"),
    "name": ("name", "has_pet"),
    "age": ("age",),
    "old": ("age",),
    "birthday": ("birthday", "born", "birth"),
    "phone": ("phone",),
    "email": ("email",),
    "address": ("address", "lives_in"),
    "birthplace": ("birthplace", "born"),
    "birth": ("birthplace", "born", "birthday"),
}


def _predicate_covers_property(pred: str, word: str) -> bool:
    p = (pred or "").lower()
    if word in _PROPERTY_PREDICATE_MAP:
        return any(p == cand or p.startswith(cand) for cand in _PROPERTY_PREDICATE_MAP[word])
    if p == word or p.startswith(word):
        return True
    return any(p.startswith(pp) for pp in _PREFERENCE_PREDICATES)

# "You" takes the base form of the verb ("You use React", not "You uses").
_YOU_PHRASES = {
    "owns": "own",
    "uses": "use",
    "lives in": "live in",
    "works at": "work at",
    "has a pet named": "have a pet named",
    "studies": "study",
    "works on": "work on",
    "currently uses": "currently use",
    "currently working on": "currently working on",
    # Member 1 (gpt-oss-20b) fact verbs -> fluent "You ..." phrasing.
    "listens to": "listen to",
    "interested in": "are interested in",
    "wants": "want to",
    "likes": "like",
    "considering": "are considering",
    "tracks": "track",
    "researches": "research",
    "started": "started",
    "made": "made",
    "attended": "attended",
    "read": "read",
    "acquired": "acquired",
}


def _stem(w: str) -> str:
    """Very light suffix-stripping so using/uses/use and friends align."""
    w = w.lower()
    prev = None
    while w != prev:
        prev = w
        if len(w) >= 5 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("ed"):
            w = w[:-2]
        elif len(w) > 2 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 2 and w.endswith("s"):
            w = w[:-1]
        elif len(w) > 2 and w.endswith("e"):
            w = w[:-1]
    return w


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-zA-Z0-9]+", text.lower()) if w not in STOP_WORDS]


def _subject_label(subject: str) -> str:
    s = str(subject or "user").strip()
    if s.lower() in ("user", "i", "me", "the user"):
        return "You"
    return s[0].upper() + s[1:]


def _predicate_phrase(pred: str, tense: str) -> str:
    p = (pred or "").lower()
    if tense == "past" and p in _PAST_VERB_MAP:
        return _PAST_VERB_MAP[p]
    if p in _VERB_MAP:
        return _VERB_MAP[p]
    for prefix, verb in _PREFIX_VERB.items():
        if p.startswith(prefix) and p != prefix:
            label = p[len(prefix):].replace("_", " ").strip()
            return f"{verb} {label}" if label else verb
    if tense == "current" and p.startswith("currently_"):
        return p[len("currently_"):].replace("_", " ")
    if tense == "past" and p.startswith("past_"):
        return p[len("past_"):].replace("_", " ")
    if tense == "past":
        return f"used to {p.replace('_', ' ')}"
    return p.replace("_", " ")


class ReasoningEngine:
    def __init__(
        self,
        abstention_threshold: float = 0.28,
        normalizer: FactNormalizer = None,
        temporal_engine: TemporalEngine = None,
    ):
        self.threshold = abstention_threshold
        self.normalizer = normalizer or FactNormalizer()
        self.temporal_engine = temporal_engine or TemporalEngine()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def answer(
        self, question: str, memories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Full deliverable output: answer / abstained / confidence / evidence."""
        memories = [m for m in (memories or []) if m]
        if not memories:
            return self._abstain(question, reason="no_memories")

        intent = self.temporal_engine.detect_temporal_intent(question)
        q_tokens = _tokenize(question)
        q_stems = {_stem(w) for w in q_tokens}

        scored = self._score_facts(question, q_tokens, q_stems, memories)
        relevant = [s for s in scored if s["relevance_ok"]]
        if not relevant:
            return self._abstain(
                question,
                reason="no_relevant_evidence",
                confidence=max(s["score"] for s in scored) if scored else 0.0,
            )

        # Property/preference questions ("favorite X", "name", "age"...) can
        # ONLY be answered from facts whose predicate establishes that exact
        # property. A high score on "uses VS Code" does NOT establish
        # "favorite editor", and "owns Honda" does not establish "name".
        prop_words = [w for w in q_tokens if w in _PROPERTY_WORDS]
        if prop_words:
            covered = [
                s for s in relevant
                if any(_predicate_covers_property(s["fact"].get("predicate", ""), w)
                       for w in prop_words)
            ]
            if not covered:
                return self._abstain(
                    question,
                    reason="property_not_established",
                    confidence=relevant[0]["score"],
                )
            relevant = covered

        # Ever-questions are answered by scanning values, not slots.
        if intent == "EVER":
            return self._answer_ever(question, q_tokens, relevant)

        # Cluster relevant memories into evolving attribute slots.
        slots = self._cluster_slots(relevant)
        best_slot = self._pick_best_slot(slots, q_tokens)

        if best_slot is None:
            return self._abstain(
                question, reason="no_slot", confidence=relevant[0]["score"]
            )

        result = self._reason_over_slot(question, intent, best_slot, q_tokens)

        # Two-hop / synthesis: pull in other strongly relevant slots so answers
        # that need information from several sessions are still combined.
        secondary = [
            s for key, s in slots.items()
            if key != best_slot["key"] and s["peak_score"] >= 0.45
        ]
        if secondary and intent in ("CURRENT", "HISTORICAL"):
            result = self._merge_secondary(question, result, secondary)

        if result["confidence"] < self.threshold:
            was_abstained = bool(result["abstained"])
            result["abstained"] = True
            if not was_abstained:
                result["answer"] = self._abstain_message(question)
        return result

    def evaluate(
        self, question: str, memories: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """Backward-compatible API used by MemoryPipeline."""
        result = self.answer(question, memories)
        return bool(result["abstained"]), str(result["answer"])

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def _score_facts(self, question, q_tokens, q_stems, memories):
        scored = []
        for f in memories:
            text = " ".join(
                str(f.get(k, "")) for k in ("predicate", "object", "text")
            ).lower()
            words = _tokenize(text)
            stems = {_stem(w) for w in words}
            stem_overlap = len(q_stems & stems)
            token_overlap = len(set(q_tokens) & set(words))
            sim = float(f.get("similarity_score", 0.0) or 0.0)
            sim = max(0.0, min(1.0, sim))
            has_sim = f.get("similarity_score") is not None
            if stem_overlap == 0 and token_overlap == 0:
                # No lexical alignment: the embedding score alone is not enough
                # to trust the fact for this question (prevents hallucination).
                score = 0.10 * sim + 0.02
            elif has_sim:
                lex = min(1.0, (stem_overlap + token_overlap) / 3.0)
                score = 0.6 * sim + 0.4 * lex
            else:
                # No embedding score available (keyword retrieval): lexical
                # alignment is the only signal.
                lex = min(1.0, (stem_overlap + token_overlap) / 3.0)
                score = 0.45 * lex + 0.10
            relevance_ok = score > 0.15 or (has_sim and sim >= 0.5)
            scored.append(
                {
                    "fact": f,
                    "score": score,
                    "relevance_ok": relevance_ok,
                    "stem_overlap": stem_overlap,
                    "token_overlap": token_overlap,
                    "has_sim": has_sim,
                }
            )
        scored.sort(key=lambda s: s["score"], reverse=True)
        return scored

    def _cluster_slots(self, scored):
        slots = {}
        for s in scored:
            f = s["fact"]
            key = self.normalizer.normalize_predicate(f.get("predicate", ""))
            if not key:
                key = (f.get("subject", "") or "user").lower() + ":unknown"
            slots.setdefault(key, {"key": key, "facts": [], "peak_score": 0.0})
            slots[key]["facts"].append(f)
            slots[key]["peak_score"] = max(slots[key]["peak_score"], s["score"])
        for key in slots:
            slots[key]["facts"] = self.temporal_engine._chronological(slots[key]["facts"])
        return slots

    def _pick_best_slot(self, slots, q_tokens):
        best = None
        for key, slot in slots.items():
            if best is None or slot["peak_score"] > best["peak_score"]:
                best = slot
        return best

    # ------------------------------------------------------------------ #
    # Reasoning over a slot's timeline
    # ------------------------------------------------------------------ #
    def _reason_over_slot(self, question, intent, slot, q_tokens):
        facts = slot["facts"]
        if not facts:
            return self._abstain(question, reason="empty_slot")

        active = [f for f in facts if not f.get("is_superseded")]
        current = active[-1] if active else facts[-1]
        current_idx = facts.index(current)

        # True conflict: two live, different values in the same slot that can
        # not be ordered in time (same session or same timestamp). Otherwise
        # the later fact chronologically overwrites the earlier one.
        conflict = False
        if len(active) > 1:
            vals = {str(f.get("object", "")).lower() for f in active}
            if len(vals) > 1:
                ts0 = int(active[0].get("timestamp", 0) or 0)
                ts1 = int(active[-1].get("timestamp", 0) or 0)
                same_sess = active[0].get("session_id") == active[-1].get("session_id")
                if same_sess or ts0 == ts1:
                    conflict = True
        if conflict:
            return self._answer_conflict(question, intent, active, slot)

        historical = facts[:current_idx] if current_idx > 0 else []
        previous = historical[-1] if historical else None

        if intent in ("CURRENT", "STILL"):
            return self._answer_value(question, "current", current, slot)
        if intent in ("PREVIOUS", "HISTORICAL"):
            if previous is not None:
                return self._answer_value(question, "past", previous, slot)
            if current.get("is_superseded"):
                # The only thing in this slot is a superseded (old) value.
                return self._answer_value(question, "past", current, slot)
            if historical:
                return self._answer_value(question, "past", historical[-1], slot)
            # Asked for something that was never true in another form.
            return self._abstain(
                question,
                reason="no_previous",
                confidence=self._confidence(question, current, slot, "current"),
            )
        if intent == "FIRST":
            first = facts[0]
            return self._answer_value(question, "past", first, slot)
        if intent == "CHANGE":
            return self._answer_change(question, facts, slot)

        return self._answer_value(question, "current", current, slot)

    # ------------------------------------------------------------------ #
    # Answer builders
    # ------------------------------------------------------------------ #
    def _answer_value(self, question, tense, fact, slot):
        subj = _subject_label(fact.get("subject", "user"))
        obj = str(fact.get("object", "")).strip()
        pred = fact.get("predicate", "")

        if pred.startswith("favorite_"):
            category = pred[len("favorite_"):].replace("_", " ").strip()
            category = category or "thing"
            if subj == "You":
                answer = f"Your favorite {category} is {obj}."
            else:
                answer = f"{subj}'s favorite {category} is {obj}."
            conf = self._confidence(question, fact, slot, tense)
            return {
                "question": question,
                "answer": answer,
                "abstained": conf < self.threshold,
                "confidence": conf,
                "evidence": self._evidence([fact]),
                "intent": tense,
            }

        if pred == "name":
            answer = f"Your name is {obj}." if subj == "You" else f"{subj}'s name is {obj}."
            conf = self._confidence(question, fact, slot, tense)
            return {
                "question": question,
                "answer": answer,
                "abstained": conf < self.threshold,
                "confidence": conf,
                "evidence": self._evidence([fact]),
                "intent": tense,
            }

        if pred == "age":
            answer = f"You are {obj} years old." if subj == "You" else f"{subj} is {obj} years old."
            conf = self._confidence(question, fact, slot, tense)
            return {
                "question": question,
                "answer": answer,
                "abstained": conf < self.threshold,
                "confidence": conf,
                "evidence": self._evidence([fact]),
                "intent": tense,
            }

        if pred in ("occupation",):
            answer = f"You are a {obj}." if subj == "You" else f"{subj} is a {obj}."
            conf = self._confidence(question, fact, slot, tense)
            return {
                "question": question,
                "answer": answer,
                "abstained": conf < self.threshold,
                "confidence": conf,
                "evidence": self._evidence([fact]),
                "intent": tense,
            }

        if pred == "year_of_study":
            answer = f"You are in your {obj}." if subj == "You" else f"{subj} is in {obj}."
            conf = self._confidence(question, fact, slot, tense)
            return {
                "question": question,
                "answer": answer,
                "abstained": conf < self.threshold,
                "confidence": conf,
                "evidence": self._evidence([fact]),
                "intent": tense,
            }

        if tense == "current":
            phrase = _predicate_phrase(pred, "current")
            if subj == "You":
                phrase = _YOU_PHRASES.get(phrase, phrase)
            answer = f"{subj} {phrase} {obj}."
        else:
            phrase = _predicate_phrase(pred, "past")
            answer = f"{subj} previously {phrase} {obj}."
            answer = answer.replace("previously previously", "previously")

        conf = self._confidence(question, fact, slot, tense)
        return {
            "question": question,
            "answer": answer,
            "abstained": conf < self.threshold,
            "confidence": conf,
            "evidence": self._evidence([fact]),
            "intent": tense,
        }

    def _answer_ever(self, question, q_tokens, scored):
        # Prefer facts whose VALUE matches an entity named in the question
        # (e.g. "Did I ever use Vue?" -> facts about Vue, not React).
        q_values = {w.lower() for w in q_tokens if len(w) >= 3}
        value_hits = []
        for s in scored:
            f = s["fact"]
            obj = str(f.get("object", "")).lower()
            if not obj:
                continue
            if any(v == obj or (len(v) >= 4 and v in obj) for v in q_values):
                value_hits.append(f)

        candidates = value_hits if value_hits else [s["fact"] for s in scored]
        candidates = self.temporal_engine._chronological(candidates)

        if not candidates:
            return self._abstain(question, reason="never", confidence=0.05)

        last = candidates[-1]
        value = str(last.get("object", "")).strip()
        subj = _subject_label(last.get("subject", "user"))
        pred = last.get("predicate", "")
        phrase = _predicate_phrase(pred, "past")
        if not value_hits:
            conf = 0.25  # answered only on weak lexical overlap
            answer = (f"There is limited evidence that {subj} {phrase} "
                      f"{value} in the conversation history.")
        else:
            conf = min(0.9, 0.5 + 0.15 * len(candidates))
            answer = (f"Yes. {subj} {phrase} {value} "
                      f"(mentioned in {len(candidates)} session(s)).")
        return {
            "question": question,
            "answer": answer,
            "abstained": conf < self.threshold,
            "confidence": conf,
            "evidence": self._evidence(candidates),
            "intent": "ever",
        }

    def _answer_change(self, question, facts, slot):
        sequence = [str(f.get("object", "")).strip() for f in facts if str(f.get("object", "")).strip()]
        uniq = []
        for v in sequence:
            if not uniq or uniq[-1].lower() != v.lower():
                uniq.append(v)
        if not uniq:
            return self._abstain(question, reason="no_values")

        subj = _subject_label(facts[-1].get("subject", "user"))
        pred = facts[-1].get("predicate", "")
        timeline = " -> ".join(uniq)
        possessive = "Your" if subj == "You" else f"{subj}'s"
        answer = f"{possessive} history: {timeline}. Currently: {uniq[-1]}."
        conf = min(0.95, 0.6 + 0.08 * len(facts))
        return {
            "question": question,
            "answer": answer,
            "abstained": conf < self.threshold,
            "confidence": conf,
            "evidence": self._evidence(facts),
            "intent": "change",
        }

    def _answer_conflict(self, question, intent, active, slot):
        options = [str(f.get("object", "")).strip() for f in active]
        subj = _subject_label(active[0].get("subject", "user"))
        verb = "are" if subj == "You" else "is"
        answer = (f"Conflicting information found: {subj} {verb} recorded as "
                  f"{' and '.join(options)} across sessions. "
                  f"Cannot determine the current value with certainty.")
        conf = 0.15
        return {
            "question": question,
            "answer": answer,
            "abstained": conf < self.threshold,
            "confidence": conf,
            "evidence": self._evidence(active),
            "intent": "conflict",
        }

    def _merge_secondary(self, question, result, secondary):
        extra = []
        for s in secondary:
            active = [f for f in s["facts"] if not f.get("is_superseded")]
            f = active[-1] if active else s["facts"][-1]
            obj = str(f.get("object", "")).strip()
            pred = f.get("predicate", "")
            if obj:
                extra.append(f"{_predicate_phrase(pred, 'current')} {obj}")
        if extra and not result["abstained"]:
            result = dict(result)
            result["answer"] += " Also: " + "; ".join(extra) + "."
            result["confidence"] = round(0.85 * result["confidence"], 3)
            result["evidence"] = self._evidence(
                result.get("evidence", []) + [s["facts"][-1] for s in secondary]
            )
        return result

    # ------------------------------------------------------------------ #
    # Confidence + abstention
    # ------------------------------------------------------------------ #
    def _confidence(self, question, fact, slot, tense):
        base = float(fact.get("similarity_score", 0.0) or 0.0)
        q_tokens = _tokenize(question)
        q_stems = {_stem(w) for w in q_tokens}
        blob = " ".join(
            str(fact.get(k, "")) for k in ("predicate", "object", "text")
        ).lower()
        blob_stems = {_stem(w) for w in _tokenize(blob)}
        alignment = len(q_stems & blob_stems) / max(1, len(q_stems))

        n_facts = max(1, len(slot["facts"]))
        evidence_support = min(1.0, n_facts / 3.0)

        if tense == "current" and not fact.get("is_superseded"):
            temporal_ok = 1.0
        elif tense == "past" and fact.get("is_superseded"):
            temporal_ok = 0.9
        elif tense == "past":
            temporal_ok = 0.7
        else:
            temporal_ok = 0.6

        conf = 0.45 * min(1.0, max(base, 0.0) + 0.2 * alignment)
        conf += 0.25 * temporal_ok
        conf += 0.30 * evidence_support
        if alignment == 0.0:
            # Match came purely from embeddings, no word-level support.
            conf = min(conf, 0.55)
        return round(max(0.0, min(1.0, conf)), 3)

    def _abstain(self, question, reason, confidence=0.0):
        return {
            "question": question,
            "answer": self._abstain_message(question),
            "abstained": True,
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "evidence": [],
            "reason": reason,
        }

    @staticmethod
    def _abstain_message(question: str) -> str:
        return ("I don't have enough evidence in the conversation history "
                "to answer this.")

    @staticmethod
    def _evidence(facts) -> List[str]:
        seen, out = set(), []
        for f in facts:
            sid = f.get("session_id", "") if isinstance(f, dict) else str(f)
            if sid and sid not in seen:
                seen.add(sid)
                out.append(str(sid))
        return out