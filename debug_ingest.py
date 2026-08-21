from memory.pipeline import MemoryPipeline
pipeline = MemoryPipeline()
# mock query to capture cypher
original_query = pipeline.retrieval.storage.query
def hooked_query(cypher):
    print('CYPHER:', cypher)
    res = original_query(cypher)
    print('RESULT:', res)
    return res
pipeline.retrieval.storage.query = hooked_query

s1 = [{'role': 'user', 'content': 'I bought a Honda car.'}]
pipeline.ingest_session('sess_car_1', s1, '2024/01/01 10:00', 1704103200)
