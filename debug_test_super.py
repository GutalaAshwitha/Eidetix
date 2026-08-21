from memory.pipeline import MemoryPipeline

pipeline = MemoryPipeline()

s1 = [{"role": "user", "content": "I bought a Honda car."}]
pipeline.ingest_session("sess_car_1", s1, "2024/01/01 10:00", 1704103200)

s8 = [{"role": "user", "content": "I sold my Honda and bought a Toyota."}]
pipeline.ingest_session("sess_car_8", s8, "2024/05/01 10:00", 1714557600)

facts = pipeline.retrieval.storage.get_all_facts()
print(f"Total facts retrieved: {len(facts)}")
for f in facts:
    print("  ->", f)

res_current = pipeline.answer_question("What car does the user currently own?")
print("res_current:", res_current)
