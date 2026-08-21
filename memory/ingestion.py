import time
from typing import Dict, List, Any

try:
    from .storage import StorageManager
    from .extraction import FactExtractor
    from .normalization import FactNormalizer
    from .supersession import SupersessionEngine
except ImportError:
    from memory.storage import StorageManager
    from memory.extraction import FactExtractor
    from memory.normalization import FactNormalizer
    from memory.supersession import SupersessionEngine


class IngestionPipeline:
    def __init__(
        self,
        storage: StorageManager = None,
        extractor: FactExtractor = None,
        normalizer: FactNormalizer = None,
        supersession_engine: SupersessionEngine = None,
    ):
        self.storage = storage or StorageManager()
        self.extractor = extractor or FactExtractor()
        self.normalizer = normalizer or FactNormalizer()
        self.supersession_engine = (
            supersession_engine or SupersessionEngine(self.normalizer)
        )

    def ingest_session(
        self,
        session_id: str,
        turns: List[Dict[str, str]],
        date_str: str,
        timestamp: int,
        user_id: str = "user_default",
    ) -> List[Dict[str, Any]]:
        self.storage.create_session(session_id, date_str, timestamp, user_id)
        raw_facts = self.extractor.extract_facts(turns, timestamp)
        existing_facts = self.storage.get_all_facts()

        ingested_facts = []
        fact_idx = 0
        now_ns = time.time_ns()

        for rf in raw_facts:
            fact_idx += 1
            fact_key = f"{session_id}_{fact_idx}_{now_ns}"

            subj = rf.get("subject", "user")
            pred = rf.get("predicate", "")
            obj = rf.get("object", "")
            text = rf.get("text", "")

            new_fact_dict = {
                "subject": subj,
                "predicate": pred,
                "object": obj,
                "text": text,
                "timestamp": timestamp,
            }
            superseded = self.supersession_engine.find_superseded_facts(
                new_fact_dict, existing_facts
            )

            fact_id = self.storage.create_fact(
                fact_key=fact_key,
                subject=subj,
                predicate=pred,
                obj=obj,
                text=text,
                timestamp=timestamp,
                session_id=session_id,
                is_superseded=False,
            )

            for old_fact in superseded:
                old_id = old_fact.get("id")
                if old_id:
                    self.storage.mark_superseded(old_id, fact_id)
                    old_fact["is_superseded"] = True

            new_fact_dict["id"] = fact_id
            new_fact_dict["is_superseded"] = False
            new_fact_dict["session_id"] = session_id
            existing_facts.append(new_fact_dict)
            ingested_facts.append(new_fact_dict)

        return ingested_facts
