# Track 03: Memory System Improvement Plan to Ace LongMemEval Benchmarks

## Executive Summary
Your system has good architecture but relies on brittle keyword matching. To ace LongMemEval (achieve >80% accuracy), you need:
1. **Semantic retrieval** (embeddings-based)
2. **Confidence scoring** for abstention decisions
3. **Formal evaluation** against LongMemEval_S
4. **Better fact extraction** with semantic matching for supersession

The benchmark tasks:
- 500 questions across 5 categories
- 30-40 sessions per question (~115k tokens)
- Critical: **Abstention accuracy** (knowing when NOT in history)
- Long-context models drop 30-60% here - you can beat them with smart design

---

## Phase 1: Semantic Retrieval (Week 1)

### Current Problem
```python
# Current: Brittle keyword matching in retrieval.py
if any(w in keywords for w in ["car", "vehicle"]) and pred in ["owns", "sold"]:
    relevant_facts.append(f)
```
- Misses synonyms (automobile vs. car)
- Hardcoded predicates (won't generalize to LongMemEval)
- No ranking by relevance

### Solution: Use Embeddings
```python
# New approach: Semantic similarity
from sentence_transformers import SentenceTransformer

class SemanticRetrievalEngine:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')  # or 'all-mpnet-base-v2' for better quality
        self.fact_embeddings = {}
    
    def encode_fact(self, fact):
        text = f"{fact['subject']} {fact['predicate']} {fact['object']}"
        return self.model.encode(text)
    
    def retrieve(self, query, top_k=5):
        query_embedding = self.model.encode(query)
        scores = []
        for fact_id, fact in enumerate(self.facts):
            fact_embedding = self.fact_embeddings[fact_id]
            similarity = query_embedding @ fact_embedding  # cosine similarity
            scores.append((similarity, fact))
        
        return sorted(scores, reverse=True)[:top_k]
```

### Implementation Steps
1. Add `sentence-transformers` to requirements
2. Create `SemanticRetrievalEngine` in `memory/retrieval.py`
3. Cache embeddings in storage for performance
4. Update `MemoryPipeline` to use semantic retrieval
5. **Test**: Should handle open-domain predicates

### Expected Improvement
- Keyword matching: ~40% accuracy
- Semantic retrieval: ~65% accuracy

---

## Phase 2: Confidence-Based Abstention (Week 1-2)

### Current Problem
```python
# Current: Binary decision with keyword matching
topic_match = False
if any(w in keywords for w in ["car"]) and ("car" in text or pred in ["owns"]):
    topic_match = True
return topic_match  # True = answer, False = abstain
```
- Too aggressive on false negatives (abstains when should answer)
- No measure of confidence
- Hard to tune

### Solution: Confidence Scoring
```python
class ConfidenceAbstentionEngine:
    def __init__(self, semantic_retrieval_engine):
        self.retrieval = semantic_retrieval_engine
        self.threshold = 0.5  # Tunable
    
    def evaluate(self, question, facts):
        if not facts:
            return True, "ABSTAIN: No relevant information found."
        
        # Calculate confidence based on top retrieved fact's similarity
        top_fact = facts[0]
        confidence = top_fact.get('similarity_score', 0.0)
        
        # Check semantic alignment between question and answer
        question_keywords = extract_keywords(question)
        answer_keywords = extract_keywords(top_fact['text'])
        keyword_overlap = len(question_keywords & answer_keywords) / len(question_keywords)
        
        # Combined confidence
        combined_confidence = 0.7 * confidence + 0.3 * keyword_overlap
        
        if combined_confidence < self.threshold:
            return True, "ABSTAIN: Insufficient confidence in answer."
        
        return False, str(top_fact.get('object'))
```

### Implementation Steps
1. Add similarity scores to retrieval results
2. Create `ConfidenceAbstentionEngine`
3. Add confidence threshold parameter (start at 0.5)
4. Track: precision and recall of abstention
5. **Tune** based on validation set performance

### Expected Improvement
- Keyword abstention: ~50% abstention F1
- Confidence-based: ~75% abstention F1

---

## Phase 3: Better Supersession Detection (Week 2)

### Current Problem
```python
# Current: Hardcoded for specific predicates
if new_pred == "owns" and old_pred == "owns":
    if new_fact.get("object") != old.get("object"):
        superseded.append(old)
```
- Won't work for arbitrary predicates (e.g., "studied_at", "visited")
- Doesn't handle synonyms (owns vs. has)
- Missing complex updates

### Solution: Semantic Entity Matching
```python
class SemanticSupersessionEngine:
    def __init__(self):
        self.semantic_retrieval = SemanticRetrievalEngine()
    
    def find_superseded_facts(self, new_fact, existing_facts):
        superseded = []
        new_ts = new_fact['timestamp']
        new_subject = new_fact['subject']
        new_pred = new_fact['predicate']
        new_obj = new_fact['object']
        
        for old in existing_facts:
            if old.get('is_superseded'):
                continue
            old_ts = old['timestamp']
            
            # Only newer facts supersede older ones
            if new_ts <= old_ts:
                continue
            
            # Check semantic similarity of entities
            subject_similarity = self._similarity(new_subject, old['subject'])
            object_similarity = self._similarity(new_obj, old['object'])
            pred_similarity = self._similarity(new_pred, old['predicate'])
            
            # Case 1: Same subject and predicate, different object
            if subject_similarity > 0.8 and pred_similarity > 0.8:
                if object_similarity < 0.5:
                    superseded.append(old)
            
            # Case 2: Contradictory actions (e.g., sold vs owns)
            if self._is_contradictory(new_pred, old_pred):
                if subject_similarity > 0.8 and object_similarity > 0.7:
                    superseded.append(old)
        
        return superseded
    
    def _similarity(self, text1, text2):
        e1 = self.model.encode(text1)
        e2 = self.model.encode(text2)
        return np.dot(e1, e2)  # Cosine similarity
    
    def _is_contradictory(self, pred1, pred2):
        contradictions = {
            ('owns', 'sold'): True,
            ('works_at', 'quit'): True,
            ('lives_in', 'moved_from'): True,
        }
        return contradictions.get((pred1, pred2)) or contradictions.get((pred2, pred1))
```

### Implementation Steps
1. Replace hardcoded supersession logic
2. Use semantic similarity for entity/predicate matching
3. Add predicate contradiction rules
4. **Test**: Verify car example still works (Honda → Toyota)

---

## Phase 4: Formal Evaluation (Week 2-3)

### Setup Evaluation Pipeline
```python
# new file: memory/evaluator.py

import json
import jsonl
from memory.pipeline import MemoryPipeline

def evaluate_on_longmemeval(dataset_path, output_path):
    pipeline = MemoryPipeline()
    with open(dataset_path) as f:
        dataset = json.load(f)
    
    hypotheses = []
    for item in dataset:
        question_id = item['question_id']
        question = item['question']
        sessions = item['haystack_sessions']
        
        # Ingest all sessions
        for i, session in enumerate(sessions):
            pipeline.ingest_session(
                session_id=f"{question_id}_session_{i}",
                turns=session,
                date_str=item['haystack_dates'][i],
                timestamp=parse_timestamp(item['haystack_dates'][i])
            )
        
        # Answer question
        result = pipeline.answer_question(question)
        
        hypotheses.append({
            'question_id': question_id,
            'hypothesis': result['answer']
        })
    
    # Save for LongMemEval evaluation script
    with open(output_path, 'w') as f:
        for h in hypotheses:
            f.write(json.dumps(h) + '\n')

if __name__ == '__main__':
    evaluate_on_longmemeval(
        'LongMemEval/data/longmemeval_oracle.json',
        'eval_results.jsonl'
    )
```

### Run Evaluation
```bash
# After generating eval_results.jsonl
export OPENAI_API_KEY=your_key
cd LongMemEval/src/evaluation
python evaluate_qa.py gpt-4o ../../../eval_results.jsonl ../../data/longmemeval_oracle.json
```

### Metrics to Track
- Overall accuracy by question type
- Abstention precision/recall
- Temporal reasoning accuracy
- Knowledge update accuracy

---

## Phase 5: Optimization & Tuning (Week 3-4)

### Key Tuning Parameters
1. **Embedding model**: all-MiniLM-L6-v2 vs all-mpnet-base-v2
2. **Similarity threshold** (retrieval top-k cutoff)
3. **Abstention confidence threshold**
4. **Semantic similarity thresholds** (supersession)

### Optimization Strategy
```python
# Use validation set to tune hyperparameters
from sklearn.model_selection import ParameterGrid

params = {
    'embedding_model': ['all-MiniLM-L6-v2', 'all-mpnet-base-v2'],
    'retrieval_top_k': [3, 5, 10],
    'abstention_threshold': [0.4, 0.5, 0.6, 0.7],
    'entity_similarity_threshold': [0.7, 0.8, 0.9]
}

best_accuracy = 0
for param_set in ParameterGrid(params):
    pipeline = MemoryPipeline(**param_set)
    accuracy = evaluate_on_longmemeval_subset(pipeline, validation_set)
    if accuracy > best_accuracy:
        best_accuracy = accuracy
        best_params = param_set
```

### Benchmarking Against Baselines
- GPT-4 with 115k context: ~70% accuracy
- GPT-4o mini with semantic retrieval: target >85%
- Your system with all optimizations: target >90%

---

## Architecture Diagram (Post-Improvement)

```
Input Session
    ↓
FactExtractor (with LLM confidence)
    ↓
Storage (HydraDB)
    ↓
SemanticRetrievalEngine (embeddings)
    ↓
Retrieved Facts (ranked by similarity)
    ↓
TemporalFilter (current/historical/first)
    ↓
ConfidenceAbstentionEngine (semantic + confidence)
    ↓
Output (Answer or ABSTAIN)
```

---

## Quick Wins (Implement First)

### 1. Add Embeddings-Based Retrieval (1-2 days)
```python
pip install sentence-transformers
# Then implement SemanticRetrievalEngine
```
Expected boost: ~15% accuracy improvement

### 2. Add Confidence Scoring to Abstention (1 day)
```python
# Simple: Use similarity score from retrieval
# Threshold abstention: confidence < 0.5 → abstain
```
Expected boost: ~10% abstention accuracy

### 3. Run LongMemEval Evaluation (1 day)
```bash
python evaluate_on_longmemeval.py
# Get baseline metrics
```
Expected result: See where you stand (likely 40-50% on full set)

---

## Files to Modify/Create

### Modify
- `memory/retrieval.py` → Add `SemanticRetrievalEngine`
- `memory/abstention.py` → Add confidence scoring
- `memory/supersession.py` → Add semantic entity matching
- `memory/pipeline.py` → Use new engines

### Create
- `memory/evaluator.py` → LongMemEval evaluation
- `memory/embeddings.py` → Embedding utilities
- `requirements.txt` → Add sentence-transformers

### Test
- `tests/test_semantic_retrieval.py` → Test embedding-based retrieval
- `tests/test_confidence_abstention.py` → Test new abstention logic
- `tests/test_longmemeval.py` → Integration test with LongMemEval subset

---

## Success Criteria

| Phase | Metric | Target | Current |
|-------|--------|--------|---------|
| 1-2 | Overall Accuracy | >75% | ~40% |
| 1-2 | Abstention F1 | >0.75 | ~0.50 |
| 3 | Temporal Reasoning Accuracy | >80% | ~50% |
| 4 | Knowledge Update Accuracy | >85% | ~60% |
| 5 | Final Accuracy (Oracle) | >90% | ~40% |

---

## Resources

### Embedding Models
- `all-MiniLM-L6-v2` (384 dims): Fast, good for retrieval
- `all-mpnet-base-v2` (768 dims): Better quality, slower
- `all-t5-large-v1` (1024 dims): State-of-the-art

### Reference
- LongMemEval Paper: https://arxiv.org/pdf/2410.10813.pdf
- Semantic Search: https://www.sbert.net/
- Abstention in QA: https://github.com/xiaowu0162/LongMemEval

---

## Next Immediate Steps
1. ✅ Read this document
2. ⬜ Install sentence-transformers
3. ⬜ Implement `SemanticRetrievalEngine`
4. ⬜ Add similarity scores to facts
5. ⬜ Update `ConfidenceAbstentionEngine`
6. ⬜ Create `evaluator.py` and run baseline
7. ⬜ Track metrics in spreadsheet
