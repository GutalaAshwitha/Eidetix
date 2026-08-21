"""Demo: every Person-3 reasoning feature, printed in one run.

Usage:
    python demo_reasoning.py
"""

import json
from memory.reasoning import ReasoningEngine

engine = ReasoningEngine()


def mem(sid, pred, obj, ts, sup=False, sim=0.8):
    return {
        "subject": "user", "predicate": pred, "object": obj,
        "text": f"User {pred} {obj}", "timestamp": ts,
        "session_id": sid, "is_superseded": sup, "similarity_score": sim,
    }


def show(title, question, memories):
    res = engine.answer(question, memories)
    status = "ABSTAIN" if res["abstained"] else "ANSWER"
    print(f"\n[{status}] {title}")
    print(f"  Q: {question}")
    print(f"  A: {res['answer']}")
    print(f"  confidence: {res['confidence']}   evidence: {res['evidence']}")
    return res


print("=" * 72)
print("PERSON 3 — TEMPORAL REASONING + ANSWER/ABSTENTION  (feature demo)")
print("=" * 72)

framework = [
    mem("session_1", "uses", "React", 1700000000),
    mem("session_20", "uses", "Vue", 1705000000, sup=True),
    mem("session_35", "uses", "React", 1710000000),
]

# 1. Understand question + current fact
show("1. CURRENT FACT (chronological sort, superseded handling)",
     "What framework am I currently using?", framework)

# 2. Historical fact
show("2. HISTORICAL (previously used)",
     "What framework did I previously use?", framework)

# 3. First / earliest
show("3. FIRST",
     "What was the first framework I used?", framework)

# 4. Ever (yes/no)
show("4. EVER (did the user ever...)",
     "Did I ever use Vue?", framework)

# 5. Change over time
show("5. CHANGE OVER TIME (timeline)",
     "How has my framework changed over time?", framework)

# 6. Abstention: topic not in history at all
show("6. ABSTENTION (favorite movie never mentioned)",
     "What is my favorite movie?",
     [mem("s1", "lives_in", "Pune", 1700000000, sim=0.12)])

# 7. Abstention: empty memory
show("7. ABSTENTION (no memories at all)",
     "Where does the user live?", [])

# 8. Overwrite detection without flags (purely by chronology)
show("8. OVERWRITE DETECTED (same slot, later fact wins)",
     "Where does the user currently work?",
     [mem("s_old", "works_at", "TechCorp", 1700000000),
      mem("s_new", "works_at", "DataWorks", 1710000000)])

# 9. Conflict detection (same session, contradictory values)
show("9. CONFLICT DETECTED (abstains with explanation)",
     "Where does the user currently live?",
     [mem("s1", "lives_in", "Pune", 1700000000),
      mem("s1", "lives_in", "Mumbai", 1700000000)])

# 10. Multi-session synthesis (two-hop)
show("10. TWO-HOP SYNTHESIS (combines multiple slots)",
     "Where does the user live and work?",
     [mem("s1", "lives_in", "Pune", 1700000000),
      mem("s2", "works_at", "TechCorp", 1701000000, sim=0.5)])

print("\n" + "=" * 72)
print("All 10 features demonstrated above. "
      "Automated checks: python -m unittest discover -s tests")
print("=" * 72)