import json
from collections import defaultdict
import random

# For reproducibility so we get the same selection if we rerun
random.seed(42)

def main():
    with open('data/longmemeval_oracle.json', 'r') as f:
        data = json.load(f)
        
    abs_cases = []
    category_groups = defaultdict(list)
    
    # 1 & 2. Load and group instances
    for idx, instance in enumerate(data):
        q_id = instance.get('question_id', '')
        q_type = instance.get('question_type', 'unknown')
        
        item = {"index": idx, "question_id": q_id, "question_type": q_type}
        
        if q_id.endswith('_abs'):
            abs_cases.append(item)
        else:
            category_groups[q_type].append(item)
            
    selected_instances = []
    
    # 3. Pick a target count
    # Pick 6 abstention cases
    selected_abs = random.sample(abs_cases, min(6, len(abs_cases)))
    selected_instances.extend(selected_abs)
    
    # Pick 3 from each category to stay safely under the 200k token quota (3 * 6 = 18 + 6 abs = 24 total)
    for q_type, items in category_groups.items():
        chosen = random.sample(items, min(3, len(items)))
        selected_instances.extend(chosen)
        
    # Sort them back by original index
    selected_instances.sort(key=lambda x: x["index"])
    
    # 5. Save selected indices/question_ids to a JSON file
    with open('out/demo_subset_ids.json', 'w') as f:
        json.dump({
            "indices": [x["index"] for x in selected_instances],
            "question_ids": [x["question_id"] for x in selected_instances]
        }, f, indent=2)
        
    # 4. Print out grouped by category
    print_groups = defaultdict(list)
    for x in selected_instances:
        if x["question_id"].endswith('_abs'):
            print_groups["Abstention Cases (_abs)"].append(x["question_id"])
        else:
            print_groups[x["question_type"]].append(x["question_id"])
            
    print(f"Total Selected: {len(selected_instances)} instances\n")
    for group, q_ids in print_groups.items():
        print(f"--- {group} ({len(q_ids)} instances) ---")
        for q_id in q_ids:
            print(f"  {q_id}")
            
    print(f"\nSaved {len(selected_instances)} items to out/demo_subset_ids.json")

if __name__ == "__main__":
    main()
