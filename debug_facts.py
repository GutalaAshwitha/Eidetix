from memory.pipeline import MemoryPipeline

p = MemoryPipeline()
facts = p.retrieval.storage.get_all_facts()
print(f"Total facts stored: {len(facts)}")
for f in facts:
    print("  ->", f)
