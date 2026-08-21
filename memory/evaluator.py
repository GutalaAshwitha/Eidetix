"""memory/evaluator.py — LongMemEval benchmark runner (Member 3 + Member 4 hook).

End-to-end evaluation:

    LongMemEval instance
      -> sessions  (memory.extraction.FactExtractor  -- Member 1 stand-in)
      -> graph     (member2.loader.load_memories    -- Member 2)
      -> answer    (member2.retrieve + memory.reasoning -- Member 3)
      -> score     (normalized comparison vs the dataset's `answer`)

Run (fake backend, first 20 instances, per-category):
    python -m memory.evaluator --subset 20 --backend fake

Run (live HydraDB node; start it with hydradb/start_dev_node.sh first):
    python -m memory.evaluator --subset 20 --backend live

Full 500-instance scoreboard:
    python -m memory.evaluator --backend fake --out eval_results.jsonl

Threshold calibration sweep:
    python -m memory.evaluator --subset 12 --calibrate

Output metrics (overall + per category):
    accuracy, precision, coverage, abstention_rate, answered, n
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from member2.loader import load_memories, memories_from_oracle_instance
from member2.storage import HydraStorage
from memory.reasoning import ReasoningEngine
from memory.integration import answer_from_storage

STOP = {
    "the", "a", "an", "my", "i", "you", "your", "me", "is", "are", "am", "was",
    "were", "did", "do", "does", "what", "which", "who", "when", "where", "how",
    "why", "to", "of", "for", "with", "in", "on", "at", "it", "its", "and", "or",
    "but", "that", "this", "these", "those", "not", "no", "as", "be", "been",
    "have", "has", "had", "from", "about", "by", "now", "then", "also", "just",
    "really", "very", "like", "got", "get", "got", "one", "could", "would",
}


def _store_factory(backend: str, **kw) -> HydraStorage:
    if backend == "live":
        from member2.hydra_client import live_storage
        return live_storage(**kw)
    from member2.fake_client import FakeConn
    from member2.storage import HydraDBClient
    return HydraStorage(HydraDBClient(FakeConn()))


# ---------------------------------------------------------------------------
# Answer normalization + comparison
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    import re as _re
    s = _re.sub(r"[^a-z0-9\s%$€£]", " ", str(text or "").lower())
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def content_tokens(text: str) -> set:
    return {t for t in normalize_text(text).split() if t not in STOP}


def answers_match(predicted: str, truth: str) -> bool:
    """Return True when the predicted answer supports the ground truth.

    Heuristic (no LLM judge, no API quota): the ground-truth answer in
    LongMemEval is a short keyphrase. We count it as a match when the
    predicted sentence contains all its content words, or the normalized
    strings overlap heavily.
    """
    p = normalize_text(predicted)
    t = normalize_text(truth)
    if not t:
        return False
    if t in p:
        return True
    p_tok, t_tok = content_tokens(p), content_tokens(t)
    if not t_tok:
        return False
    if t_tok <= p_tok:
        return True
    ratio = len(t_tok & p_tok) / len(t_tok)
    return ratio >= 0.6


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------


def load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_memory_map(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load Member 1's memories.json into {question_id: [records]}.

    Accepts:
      - Member 1's real output: a LIST of {"question_id": ..., "memories": [...]}
      - a dict already keyed by question_id
      - a flat list of records (each may carry "question_id")
    Records are passed through member2.loader.normalize_memory_record at load
    time, so any of Member 1's fields (topic_key, status, source_message dict,
    date-string timestamp, ...) are reconciled into the internal schema.
    """
    from member2.loader import normalize_memory_record

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    memory_map: Dict[str, List[Dict[str, Any]]] = {}
    if isinstance(data, dict):
        for qid, records in data.items():
            if not isinstance(records, list):
                continue
            memory_map[str(qid)] = [normalize_memory_record(r) for r in records]
        return memory_map

    # List form. Member 1's real format is [{"question_id", "memories": [...]}];
    # a flat list of records is also accepted.
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("memories"), list):
            qid = str(item.get("question_id") or item.get("instance_id") or "")
            recs = [normalize_memory_record(r) for r in item["memories"]]
            if qid:
                memory_map.setdefault(qid, []).extend(recs)
            else:
                memory_map.setdefault("", []).extend(recs)
        else:
            qid = str(item.get("question_id") or item.get("instance_id") or "")
            rec = normalize_memory_record(item)
            if qid:
                memory_map.setdefault(qid, []).append(rec)
            else:
                memory_map.setdefault("", []).append(rec)
    return memory_map


def records_for_instance(
    instance: Dict[str, Any],
    memory_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    max_sessions: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Records for one instance: prefer Member 1's pre-extracted memories,
    fall back to the rule-based stand-in."""
    qid = str(instance.get("question_id", ""))
    if memory_map:
        if qid in memory_map:
            return memory_map[qid]
        session_ids = set(instance.get("haystack_session_ids", []) or [])
        pooled = []
        for rec in memory_map.get("", []):
            if rec.get("session_id") in session_ids:
                pooled.append(rec)
        if pooled:
            return pooled
    return memories_from_oracle_instance(instance, max_sessions=max_sessions)


def select_subset(dataset: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """Pick n instances with category coverage (round-robin), then fill."""
    if n >= len(dataset):
        return dataset
    from collections import defaultdict
    by_cat: Dict[str, list] = defaultdict(list)
    for inst in dataset:
        by_cat[inst.get("question_type", "other")].append(inst)
    cats = list(by_cat)
    chosen, seen = [], set()
    i = 0
    while len(chosen) < n:
        cat = cats[i % len(cats)]
        pool = [x for x in by_cat[cat] if x["question_id"] not in seen]
        if not pool:
            cats.remove(cat)
            if not cats:
                break
            continue
        item = pool[0]
        seen.add(item["question_id"])
        chosen.append(item)
        i += 1
    return chosen


# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------


def evaluate_instances(
    instances: List[Dict[str, Any]],
    backend: str = "fake",
    max_sessions: Optional[int] = None,
    threshold: float = 0.28,
    verbose: bool = False,
    memory_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    engine = ReasoningEngine(abstention_threshold=threshold)
    storage = _store_factory(backend)

    results = []
    for inst in instances:
        qid = inst.get("question_id", "?")
        question = inst.get("question", "")
        truth = inst.get("answer", "")

        records = records_for_instance(inst, memory_map=memory_map, max_sessions=max_sessions)
        if not records:
            results.append({
                "question_id": qid, "category": inst.get("question_type", "other"),
                "question": question, "truth": truth, "predicted": None,
                "abstained": True, "correct": False, "memories_ingested": 0,
                "skip": "no_memories_extracted",
            })
            continue

        stats = load_memories(storage, records, user_name=f"u_{qid[:16]}")
        t0 = time.time()
        res = answer_from_storage(engine, storage, question, user_id=stats.user_id)
        elapsed = time.time() - t0

        abstained = bool(res.get("abstained", False))
        predicted = res.get("answer", "") or ""
        correct = (not abstained) and answers_match(predicted, truth)

        results.append({
            "question_id": qid,
            "category": inst.get("question_type", "other"),
            "question": question,
            "truth": truth,
            "predicted": predicted,
            "abstained": abstained,
            "confidence": round(float(res.get("confidence", 0.0)), 4),
            "evidence": res.get("evidence", []),
            "correct": correct,
            "memories_ingested": stats.n_memories,
            "latency_s": round(elapsed, 3),
        })
        if verbose:
            mark = "OK " if correct else ("AB " if abstained else "XX ")
            print(f"{mark} [{inst.get('question_type','?'):24s}] {question[:70]}")
            if not correct:
                print(f"      truth={truth!r}  predicted={predicted!r}")

    return compute_metrics(results)


def compute_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    answered = [r for r in results if not r.get("abstained")]
    correct = [r for r in results if r.get("correct")]
    abstained = [r for r in results if r.get("abstained")]
    by_cat: Dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r.get("category", "other"), []).append(r)

    def metrics_for(items: list) -> Dict[str, Any]:
        n = len(items)
        ans = [r for r in items if not r.get("abstained")]
        corr = [r for r in items if r.get("correct")]
        abst = [r for r in items if r.get("abstained")]
        return {
            "n": n,
            "answered": len(ans),
            "abstained": len(abst),
            "correct": len(corr),
            "accuracy": round(len(corr) / n, 4) if n else 0.0,        # correct / all
            "precision": round(len(corr) / len(ans), 4) if ans else 0.0,  # correct / answered
            "coverage": round(len(ans) / n, 4) if n else 0.0,         # answered / all
            "abstention_rate": round(len(abst) / n, 4) if n else 0.0,
        }

    overall = metrics_for(results)
    categories = {cat: metrics_for(items) for cat, items in sorted(by_cat.items())}
    return {
        "n": total,
        "overall": overall,
        "categories": categories,
        "results": results,
    }


def calibration_sweep(
    instances: List[Dict[str, Any]],
    backend: str = "fake",
    max_sessions: Optional[int] = None,
    thresholds=(0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50),
    memory_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Re-run evaluation on a fixed subset at each abstention threshold and
    report accuracy/precision/coverage so the team can pick the operating point."""
    rows = []
    for t in thresholds:
        metrics = evaluate_instances(
            instances, backend=backend, max_sessions=max_sessions, threshold=float(t),
            memory_map=memory_map,
        )
        o = metrics["overall"]
        rows.append({
            "threshold": float(t),
            "accuracy": o["accuracy"],
            "precision": o["precision"],
            "coverage": o["coverage"],
            "abstention_rate": o["abstention_rate"],
            "correct": o["correct"],
            "answered": o["answered"],
        })
        print(f"thr={t:.2f}  acc={o['accuracy']:.3f}  prec={o['precision']:.3f}  "
              f"cov={o['coverage']:.3f}  abst={o['abstention_rate']:.3f}  ({o['correct']}/{o['answered']})")
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="LongMemEval benchmark runner")
    ap.add_argument("--data", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "LongMemEval", "data", "longmemeval_oracle.json"))
    ap.add_argument("--backend", choices=("fake", "live"), default="fake")
    ap.add_argument("--subset", type=int, default=0, help="0 = all instances")
    ap.add_argument("--category", default=None, help="only this question_type")
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=0.28)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--memories", default=None,
                    help="Member 1 memories.json (flat list or {qid: [...]}); "
                         "skips rule-based extraction when present")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", default=None, help="write per-instance jsonl")
    args = ap.parse_args(argv)

    dataset = load_dataset(args.data)
    memory_map = load_memory_map(args.memories) if args.memories else None

    # With pre-extracted memories, restrict to the instances they cover BEFORE
    # subsetting/calibrating, otherwise --subset would pick non-mapped qids.
    if memory_map:
        mapped = set(memory_map) - {""}
        if mapped:
            instances = [x for x in dataset if x.get("question_id") in mapped]
        else:
            instances = dataset
    else:
        instances = dataset
    instances = select_subset(instances, args.subset or len(instances))
    if args.category:
        instances = [x for x in instances if x.get("question_type") == args.category]

    src = "pre-extracted memories" if memory_map else "rule-based extraction"
    print(f"dataset: {os.path.basename(args.data)}  instances: {len(instances)}  "
          f"backend: {args.backend}  threshold: {args.threshold}  memories: {src}")

    if args.calibrate:
        calibration_sweep(
            instances, backend=args.backend, max_sessions=args.max_sessions,
            memory_map=memory_map,
        )
        return 0

    t0 = time.time()
    metrics = evaluate_instances(
        instances,
        backend=args.backend,
        max_sessions=args.max_sessions,
        threshold=args.threshold,
        verbose=args.verbose,
        memory_map=memory_map,
    )
    elapsed = time.time() - t0
    o = metrics["overall"]
    print(f"\nran {metrics['n']} instances in {elapsed:.1f}s  "
          f"(memories ingested: {sum(r['memories_ingested'] for r in metrics['results'])})")
    print(f"OVERALL   accuracy={o['accuracy']:.3f}  precision={o['precision']:.3f}  "
          f"coverage={o['coverage']:.3f}  abstention={o['abstention_rate']:.3f}  "
          f"({o['correct']} correct / {o['answered']} answered / {o['n']} total)")
    for cat, m in metrics["categories"].items():
        print(f"  {cat:24s} accuracy={m['accuracy']:.3f}  precision={m['precision']:.3f}  "
              f"coverage={m['coverage']:.3f}  abstention={m['abstention_rate']:.3f}  "
              f"({m['correct']}/{m['answered']}/{m['n']})")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            for r in metrics["results"]:
                fh.write(json.dumps(r) + "\n")
        print(f"\nper-instance results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())