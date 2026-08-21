#!/usr/bin/env python3
"""
LongMemEval -> structured memories extractor (Member 1 deliverable)

Pipeline:
  1. Load a LongMemEval instance file (longmemeval_s_cleaned.json etc.)
  2. For each haystack session, ask an LLM to extract atomic memory facts
     (entities, preferences, facts, events, projects, relationships),
     tagged with session_id / timestamp / source message / source location.
  3. Run a second pass that groups facts about the same topic across
     sessions (in chronological order) and marks each as "current" or
     "superseded" when a later session contradicts/updates an earlier one.
  4. Write out one clean memories.json per instance (or one big file),
     ready for Member 2 to load into HydraDB.

Usage:
    export GROQ_API_KEY=gsk-...
    python extract_memories.py \
        --input data/longmemeval_s_cleaned.json \
        --output out/memories.json \
        --limit 5          # optional, for testing on a few instances first
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "openai/gpt-oss-20b"

_total_tokens = 0
# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You extract structured long-term memories from a single chat session between a user and an assistant.

For each session, identify atomic, self-contained facts worth remembering long-term. Categorize each into exactly one of:
- "entity"        (a person, place, organization, tool, product mentioned)
- "preference"     (something the user likes/dislikes/prefers)
- "fact"           (a stable fact about the user or their life/work)
- "event"          (something that happened or is planned to happen)
- "project"        (a project, task, or goal the user is working on)
- "relationship"   (a relationship between the user and another person/entity)

Rules:
- Only extract facts stated by or clearly about the USER (not general knowledge the assistant states).
- Each fact must be atomic (one idea per fact) and self-contained (understandable without the rest of the conversation).
- Write each fact as a short third-person statement, e.g. "user switched from VS Code to Cursor".
- Quote the shortest exact source snippet (<= 20 words) that supports the fact.
- If nothing memorable is in the session, return an empty list.

Return ONLY valid JSON (no markdown fences, no preamble), matching this schema:
{
  "facts": [
    {
      "fact": "string, third-person atomic statement",
      "category": "entity|preference|fact|event|project|relationship",
      "topic_key": "short lowercase snake_case key used to group facts about the same topic across sessions, e.g. 'preferred_code_editor'",
      "source_snippet": "short verbatim quote (<=20 words) from the session supporting this fact",
      "turn_index": integer index (0-based) of the turn in this session that best supports the fact
    }
  ]
}"""

SUPERSEDE_SYSTEM_PROMPT = """You are given a dictionary where each key is a topic_key and the value is a list of extracted facts for that topic, ordered chronologically by session date. Some facts within the same topic may directly update or contradict earlier ones (e.g. "user uses VS Code" -> "user switched to Cursor" -> "user is back to VS Code"). Others may simply co-exist without conflict.

For each fact across all topics, decide its status:
- "current":     the fact is still true as of the latest information
- "superseded":  a later fact on the same topic replaced/contradicted it

Return ONLY valid JSON (no markdown, no preamble), mapping each original fact's global index to its new status:
{
  "statuses": [
    {"index": integer (the exact global index provided in the input), "status": "current|superseded"}
  ]
}"""


# Rate limiter: enforce minimum interval between API calls
_last_call_time = 0.0
_MIN_CALL_INTERVAL = 13.0  # seconds; keeps us under 5 RPM free-tier limit


def call_llm(client, system, user_content, max_tokens=2000, retries=5):
    global _last_call_time, _total_tokens
    for attempt in range(retries):
        # Throttle: wait until enough time has passed since last call
        now = time.time()
        wait = _MIN_CALL_INTERVAL - (now - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        try:
            _last_call_time = time.time()
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
            if hasattr(resp, "usage") and resp.usage:
                _total_tokens += resp.usage.total_tokens
            text = resp.choices[0].message.content or ""
            text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            err_str = str(e)
            print(f"  retry {attempt+1}/{retries} after error: {e}", file=sys.stderr)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                time.sleep(60)  # rate limit: wait a full minute
            else:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError("Failed to get valid JSON after retries")


def format_session_for_prompt(session_turns):
    lines = []
    for i, turn in enumerate(session_turns):
        role = turn.get("role", "unknown")
        if role in ("system", "tool"):
            continue
        content = turn.get("content", "")
        if role == "assistant" and len(content) > 100:
            content = content[:100] + "... [TRUNCATED]"
        lines.append(f"[{i}] {role}: {content}")
    return "\n".join(lines)


def extract_facts_for_session(client, session_id, date, session_turns):
    session_text = format_session_for_prompt(session_turns)
    user_content = f"Session date: {date}\n\nSession transcript:\n{session_text}"
    result = call_llm(client, EXTRACTION_SYSTEM_PROMPT, user_content, max_tokens=4096)
    facts = result.get("facts", [])

    enriched = []
    for f in facts:
        turn_idx = f.get("turn_index")
        source_message = None
        if isinstance(turn_idx, int) and 0 <= turn_idx < len(session_turns):
            source_message = session_turns[turn_idx]

        enriched.append({
            "fact": f.get("fact"),
            "category": f.get("category"),
            "topic_key": f.get("topic_key"),
            "session_id": session_id,
            "timestamp": date,
            "source_snippet": f.get("source_snippet"),
            "source_message": source_message,
            "source_location": {"session_id": session_id, "turn_index": turn_idx},
            "status": "current",  # default; refined in supersede pass
        })
    return enriched


def resolve_supersedes(client, all_facts):
    """Group by topic_key, and run ONE batch supersede detection call for all groups."""
    from collections import defaultdict

    groups = defaultdict(list)
    for idx, f in enumerate(all_facts):
        key = f.get("topic_key") or "misc"
        groups[key].append((idx, f))

    batch_payload = {}
    for topic_key, items in groups.items():
        if len(items) < 2:
            continue
        items_sorted = sorted(items, key=lambda p: (p[1]["timestamp"] or "", p[1]["session_id"]))
        batch_payload[topic_key] = [
            {"index": orig_idx, "fact": f["fact"], "session_id": f["session_id"], "timestamp": f["timestamp"]}
            for orig_idx, f in items_sorted
        ]

    if not batch_payload:
        return all_facts

    try:
        result = call_llm(
            client,
            SUPERSEDE_SYSTEM_PROMPT,
            json.dumps({"topics": batch_payload}, ensure_ascii=False),
            max_tokens=3000,
        )
        for s in result.get("statuses", []):
            idx = s.get("index")
            status = s.get("status")
            if isinstance(idx, int) and 0 <= idx < len(all_facts):
                if status in ("current", "superseded"):
                    all_facts[idx]["status"] = status
    except RuntimeError as e:
        print(f"  batch supersede resolution failed: {e}", file=sys.stderr)

    return all_facts


def process_instance(client, instance):
    question_id = instance["question_id"]
    session_ids = instance["haystack_session_ids"]
    dates = instance["haystack_dates"]
    sessions = instance["haystack_sessions"]

    all_facts = []
    for sid, date, turns in zip(session_ids, dates, sessions):
        print(f"  session {sid} ({date}) - {len(turns)} turns")
        facts = extract_facts_for_session(client, sid, date, turns)
        all_facts.extend(facts)

    all_facts = resolve_supersedes(client, all_facts)

    return {
        "question_id": question_id,
        "memories": all_facts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to longmemeval_*.json")
    parser.add_argument("--output", required=True, help="Path to write output JSON")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N instances (testing)")
    parser.add_argument("--start", type=int, default=0, help="Start index (for resuming)")
    parser.add_argument("--subset", type=str, default=None, help="Path to JSON file with target question_ids")
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: set GROQ_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    with open(args.input, "r") as f:
        data = json.load(f)

    if args.subset:
        with open(args.subset, "r") as f:
            subset_json = json.load(f)
            # Support both our generated dict format and raw lists
            target_qids = set(subset_json.get("question_ids", [])) if isinstance(subset_json, dict) else set(subset_json)
        data = [inst for inst in data if inst.get("question_id") in target_qids]
        if args.start > 0:
            data = data[args.start:]
        print(f"Filtered dataset to {len(data)} instances using subset file.")
    else:
        if args.limit:
            data = data[args.start:args.start + args.limit]
        elif args.start > 0:
            data = data[args.start:]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    if args.start > 0 and out_path.exists():
        try:
            with open(out_path, "r") as f:
                results = json.load(f)
            print(f"Loaded {len(results)} existing instances from {out_path}")
        except Exception as e:
            print(f"Warning: could not load existing {out_path}: {e}")
            
    for i, instance in enumerate(data):
        print(f"[{i+1}/{len(data)}] {instance['question_id']}")
        try:
            result = process_instance(client, instance)
            results.append(result)
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            continue

        # write incrementally so partial progress isn't lost
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(results)} instances to {out_path}")
    print(f"\nTOTAL TOKENS USED: {_total_tokens}")


if __name__ == "__main__":
    main()
