"""Interactive tester for Person-3 features.

Type your own questions against built-in memory scenarios, inject
custom memories as JSON, or paste RAW chat conversations (auto-extracted
into facts) and ask away.

Usage:
    python test_reasoning_live.py
"""

import json
import sys
from memory.reasoning import ReasoningEngine

try:
    from memory.extraction import FactExtractor
except ImportError:
    from memory.extraction import FactExtractor

engine = ReasoningEngine()

SCENARIOS = {
    "1": {
        "name": "Framework history (React -> Vue -> React)",
        "memories": [
            {"subject": "user", "predicate": "uses", "object": "React", "text": "User uses React", "timestamp": 1700000000, "session_id": "session_1", "is_superseded": False, "similarity_score": 0.8},
            {"subject": "user", "predicate": "uses", "object": "Vue", "text": "User uses Vue", "timestamp": 1705000000, "session_id": "session_20", "is_superseded": True, "similarity_score": 0.8},
            {"subject": "user", "predicate": "uses", "object": "React", "text": "User uses React", "timestamp": 1710000000, "session_id": "session_35", "is_superseded": False, "similarity_score": 0.85},
        ],
    },
    "2": {
        "name": "Car ownership (Honda -> Toyota)",
        "memories": [
            {"subject": "user", "predicate": "owns", "object": "Honda car", "text": "User owns Honda car", "timestamp": 1704103200, "session_id": "sess_car_1", "is_superseded": True, "similarity_score": 0.75},
            {"subject": "user", "predicate": "owns", "object": "Toyota", "text": "User owns Toyota", "timestamp": 1714557600, "session_id": "sess_car_8", "is_superseded": False, "similarity_score": 0.8},
        ],
    },
    "3": {
        "name": "Mixed profile (Pune + TechCorp + pet Leo)",
        "memories": [
            {"subject": "user", "predicate": "lives_in", "object": "Pune", "text": "User lives in Pune", "timestamp": 1700000000, "session_id": "s1", "is_superseded": False, "similarity_score": 0.7},
            {"subject": "user", "predicate": "works_at", "object": "TechCorp", "text": "User works at TechCorp", "timestamp": 1701000000, "session_id": "s2", "is_superseded": False, "similarity_score": 0.65},
            {"subject": "user", "predicate": "has_pet", "object": "Leo", "text": "User's pet is named Leo", "timestamp": 1702000000, "session_id": "s3", "is_superseded": False, "similarity_score": 0.6},
        ],
    },
    "4": {
        "name": "Empty memory (test abstention)",
        "memories": [],
    },
}


def print_result(res):
    status = "ABSTAIN" if res["abstained"] else "ANSWER"
    print(f"\n  [{status}]")
    print(f"  Answer:      {res['answer']}")
    print(f"  Confidence:  {res['confidence']}")
    print(f"  Evidence:    {res['evidence']}")


def ask_loop(memories):
    print("\n  Type a question (or 'menu' to switch scenario, 'quit' to exit).")
    while True:
        try:
            q = input("\n  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if q.lower() in ("quit", "exit", "q"):
            sys.exit(0)
        if q.lower() in ("menu", "m"):
            return
        if not q:
            continue
        print_result(engine.answer(q, memories))


def parse_conversation(lines):
    """Parse 'role: message' lines into turns. Unprefixed lines are treated
    as user turns (the conversation is about the user)."""
    turns = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            role, content = line.split(":", 1)
            turns.append({"role": role.strip().lower(), "content": content.strip()})
        else:
            turns.append({"role": "user", "content": line})
    return turns


def raw_conversation_mode():
    """Paste raw chat turns, auto-extract facts (LLM if GROQ_API_KEY is set,
    rule-based otherwise), then ask questions against them."""
    print("\n  Paste a raw conversation, one message per line: 'role: message'.")
    print("  (user: / assistant: / you: all work). Press Enter on an empty line when done.")
    print("  Sessions are separated by a line containing '---'.\n")

    extractor = FactExtractor()
    memories = []
    ts = 1700000000
    session_no = 1
    current_turns = []

    def flush():
        nonlocal current_turns, ts, session_no
        if current_turns:
            facts = extractor.extract_facts(current_turns, ts)
            for i, f in enumerate(facts):
                memories.append({
                    "subject": f.get("subject", "user"),
                    "predicate": f.get("predicate", ""),
                    "object": f.get("object", ""),
                    "text": f.get("text", ""),
                    "timestamp": ts + i,
                    "session_id": f"convo_session_{session_no}",
                    "is_superseded": False,
                })
            print(f"  [extracted {len(facts)} facts from session {session_no}]")
            session_no += 1
            ts += 86400 * 7
            current_turns = []

    while True:
        try:
            line = input("  ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip() == "---":
            flush()
            continue
        if line.strip() == "":
            flush()
            break
        current_turns.extend(parse_conversation([line]))

    flush()
    if not memories:
        print("\n  [!] No facts were extracted from that conversation.")
        print("  You can still ask questions - expect ABSTAIN answers (nothing was stored).")
        ask_loop([])
        return

    print(f"\n  Extracted {len(memories)} facts total:")
    for m in memories:
        print(f"    - {m['text']}  (session {m['session_id']})")
    ask_loop(memories)


def main():
    print("=" * 70)
    print("PERSON 3 — INTERACTIVE FEATURE TESTER")
    print("=" * 70)
    while True:
        print("\nScenarios:")
        for k, v in SCENARIOS.items():
            print(f"  {k}. {v['name']} ({len(v['memories'])} memories)")
        print("  5. Custom memories (paste JSON array)")
        print("  6. RAW CONVERSATION (paste chat, auto-extract facts, then ask)")
        try:
            choice = input("\nChoose: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice == "6":
            raw_conversation_mode()
        elif choice == "5":
            print("  Paste a JSON array of memories, then press Enter twice:")
            lines = []
            while True:
                try:
                    line = input("  ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    return
                if line.strip() == "":
                    break
                lines.append(line)
            try:
                memories = json.loads("\n".join(lines))
                if not isinstance(memories, list):
                    raise ValueError("must be a list")
            except Exception as e:
                print(f"  [!] Invalid JSON: {e}")
                continue
            ask_loop(memories)
        elif choice in SCENARIOS:
            ask_loop(SCENARIOS[choice]["memories"])
        else:
            print("  [!] Invalid choice.")


if __name__ == "__main__":
    main()