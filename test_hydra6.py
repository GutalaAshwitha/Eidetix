import requests

def query(cypher):
    resp = requests.post(
        'http://127.0.0.1:8443/v1/graphs/default/query',
        headers={
            'Authorization': 'Bearer local-development-token-32-bytes',
            'X-Graph-Namespace': 'default',
            'Content-Type': 'application/json',
        },
        json={'cell_id': 'cell-0', 'query': cypher},
    )
    print(cypher, '->', resp.status_code, resp.text)

query('MATCH (f {id: 999999999}) RETURN f.text AS text')
