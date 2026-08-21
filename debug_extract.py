from memory.pipeline import MemoryPipeline

pipeline = MemoryPipeline()
s1 = [{'role': 'user', 'content': 'I bought a Honda car.'}]
facts = pipeline.ingestion.extractor.extract_facts(s1, 1704103200)
print('EXTRACTED FACTS:', facts)
