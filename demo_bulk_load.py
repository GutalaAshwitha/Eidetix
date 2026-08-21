"""Scale check: load 500 synthetic memories via the loader and time the
end-to-end retrieve + answering path over a fake backend.

Demonstrates Member 2's bulk loader throughput and Member 3's per-query
latency at hackathon scale (the full LongMemEval oracle is 500 instances).

Usage:  python demo_bulk_load.py
"""
from __future__ import annotations

import random
import time

from member2.loader import load_memories, normalize_memory_record
from member2.fake_client import FakeConn
from member2.storage import HydraStorage
from member2.retrieve import MemoryRetriever
from memory.reasoning import ReasoningEngine
from memory.integration import answer_from_storage


def build_synthetic(n: int) -> list[dict]:
    """500 deterministic synthetic memories spread across ~25 sessions."""
    cats = [
        ("owns", ["bike", "car", "laptop", "phone", "headphones", "keyboard"]),
        ("uses", ["VS Code", "Cursor", "PyCharm", "Neovim", "Sublime Text"]),
        ("lives_in", ["New York", "San Francisco", "Austin", "Seattle"]),
        ("favorite", ["coffee", "tea", "sushi", "pizza"]),
    ]
    records = []
    rng = random.Random(42)
    for i in range(n):
        cat, opts = rng.choice(cats)
        val = rng.choice(opts)
        sid = f"session_{i % 25 + 1}"
        if cat == "favorite":
            fact = f"user's favorite {cat} is {val}"
        else:
            fact = f"user {cat} {val}"
        records.append(normalize_memory_record({
            "fact": fact,
            "category": cat,
            "session_id": sid,
            "timestamp": str(1000 + i),
            "source_message": f"synthetic record {i+1}",
            "source_location": sid,
            "status": "current",
        }))
    return records


def main() -> None:
    n = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 500
    records = build_synthetic(n)
    storage = HydraStorage(FakeConn())

    t0 = time.time()
    stats = load_memories(storage, records, user_name="u_scale")
    load_dt = time.time() - t0
    # backend-agnostic access to the raw connection for counts
    conn = getattr(storage.client, "_conn", storage.client)
    n_nodes = sum(len(v) for v in conn.nodes.values())
    n_edges = len(getattr(conn, "edges", []))
    print(f"loaded {stats.n_memories} memories  ({stats.n_sessions} sessions, "
          f"{stats.n_entities} entities)")
    print(f"load time: {load_dt:.3f}s  ({load_dt*1000/stats.n_memories:.2f} ms/memory)")
    print(f"graph nodes: {n_nodes}  edges: {n_edges}")

    engine = ReasoningEngine(0.28)
    questions = [
        "What editor am I currently using?",
        "Where do I live?",
        "What is my favorite drink?",
        "What did I own first, a bike or a car?",
    ]
    # warm
    for q in questions[:1]:
        answer_from_storage(engine, storage, q, user_id=stats.user_id)

    latencies = []
    for q in questions * 5:  # 20 queries
        t = time.time()
        res = answer_from_storage(engine, storage, q, user_id=stats.user_id)
        latencies.append(time.time() - t)
    latencies.sort()
    print(f"per-query latency (n={len(latencies)}): "
          f"min={latencies[0]*1000:.1f}ms  median={latencies[len(latencies)//2]*1000:.1f}ms  "
          f"max={latencies[-1]*1000:.1f}ms")


if __name__ == "__main__":
    main()
