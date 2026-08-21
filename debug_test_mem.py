from memory.pipeline import MemoryPipeline

p = MemoryPipeline()
turns = [{"role": "user", "content": "I live in Pune and work at TechCorp."}]
ing = p.ingest_session("test_s1", turns, "2024/02/01 12:00", 1706788800)
print("Ingested facts:", ing)

all_f = p.retrieval.storage.get_all_facts()
print("All facts count:", len(all_f))
for f in all_f:
    if f.get("session_id") == "test_s1":
        print("Test_s1 fact:", f)

ret = p.retrieval.retrieve("Where does the user live?")
print("Retrieved facts for query:", ret)

ev = p.abstention.evaluate("Where does the user live?", ret)
print("Evaluation:", ev)
