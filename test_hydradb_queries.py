import requests
import json

url = 'http://127.0.0.1:8443/v1/graphs/default/query'
headers = {
    'Authorization': 'Bearer local-development-token-32-bytes',
    'X-Graph-Namespace': 'default',
    'Content-Type': 'application/json',
}

queries = [
    'MATCH (n) RETURN n LIMIT 1',
    'CREATE (n {id: 1})',
    'RETURN 1 as value',
    'CREATE (n {id: 1}) RETURN n',
    'MATCH (n) WHERE n.id = 1 RETURN n',
]

for q in queries:
    try:
        r = requests.post(
            url,
            headers=headers,
            json={'cell_id': 'cell-0', 'query': q},
            timeout=5
        )
        print(f"Query: {q[:50]}")
        print(f"  Status: {r.status_code}")
        if r.status_code >= 400:
            try:
                error = r.json().get('error', {}).get('message', r.text[:100])
                print(f"  Error: {error}")
            except:
                print(f"  Response: {r.text[:100]}")
        else:
            print(f"  Success!")
        print()
    except Exception as e:
        print(f"Query: {q[:50]}")
        print(f"  Exception: {e}\n")
