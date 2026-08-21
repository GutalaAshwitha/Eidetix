from memory.pipeline import MemoryPipeline

pipeline = MemoryPipeline()
res = pipeline.retrieval.storage.query('MATCH (s)-[:HAS_FACT]->(f) RETURN f.id')
print('ALL FACTS:', res)
res2 = pipeline.retrieval.storage.query('MATCH (n) RETURN n.id LIMIT 10')
print('ALL NODES:', res2)
