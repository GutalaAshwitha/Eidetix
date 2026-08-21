from memory.extraction import FactExtractor
from memory.retrieval import RetrievalEngine
from memory.storage import StorageManager

ex = FactExtractor()
turns = [{"role": "user", "content": "I live in Pune and work at TechCorp."}]
facts = ex.extract_facts(turns, 1706788800)
print("Extracted facts:", facts)
