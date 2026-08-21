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
    print(resp.status_code, resp.text)

query('CREATE (a {id: 774446})-[:TEST2]->(c {id: 111111})')
