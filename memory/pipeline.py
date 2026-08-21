from typing import Dict, List, Tuple, Any

try:
    from .storage import StorageManager
    from .ingestion import IngestionPipeline
    from .retrieval import RetrievalEngine
    from .abstention import AbstentionEngine
except ImportError:
    from memory.storage import StorageManager
    from memory.ingestion import IngestionPipeline
    from memory.retrieval import RetrievalEngine
    from memory.abstention import AbstentionEngine


class MemoryPipeline:
    def __init__(
        self,
        ingestion: IngestionPipeline = None,
        retrieval: RetrievalEngine = None,
        abstention: AbstentionEngine = None,
        storage: StorageManager = None,
    ):
        # A single shared storage so offline (in-memory) mode and online mode
        # behave identically: facts written by ingestion are visible to retrieval.
        shared_storage = storage or StorageManager()
        self.ingestion = ingestion or IngestionPipeline(storage=shared_storage)
        self.retrieval = retrieval or RetrievalEngine(storage=shared_storage)
        self.abstention = abstention or AbstentionEngine()

    def ingest_session(
        self, session_id: str, turns: List[Dict[str, str]], date_str: str, timestamp: int
    ):
        return self.ingestion.ingest_session(session_id, turns, date_str, timestamp)

    def answer_question(self, question: str) -> Dict[str, Any]:
        # 1. Retrieve candidate facts from HydraDB
        retrieved_facts = self.retrieval.retrieve(question)

        # 2. Reason over evidence: temporal + answer/abstention
        result = self.abstention.answer(question, retrieved_facts)

        return {
            "question": question,
            "should_abstain": result["abstained"],
            "answer": result["answer"],
            "confidence": result["confidence"],
            "evidence": result["evidence"],
            "retrieved_facts": retrieved_facts,
        }


if __name__ == "__main__":
    print("=== Testing End-to-End Memory Pipeline ===")
    pipeline = MemoryPipeline()

    # Synthetic session 1
    s1_turns = [{"role": "user", "content": "I bought a Honda car today!"}]
    pipeline.ingest_session("sess_1", s1_turns, "2024/01/10 10:00", 1704880800)

    # Synthetic session 8
    s8_turns = [{"role": "user", "content": "I sold my Honda and bought a Toyota!"}]
    pipeline.ingest_session("sess_8", s8_turns, "2024/06/15 14:00", 1718460000)

    # Test queries
    q1 = "What car does the user currently own?"
    res1 = pipeline.answer_question(q1)
    print(f"Q: {q1}\nA: {res1['answer']}\n")

    q2 = "What car did the user previously own?"
    res2 = pipeline.answer_question(q2)
    print(f"Q: {q2}\nA: {res2['answer']}\n")

    q3 = "What is the user's favorite football team?"
    res3 = pipeline.answer_question(q3)
    print(f"Q: {q3}\nA: {res3['answer']}\n")
