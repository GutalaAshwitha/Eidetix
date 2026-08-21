import requests

def query(cypher):
    print('QUERY:', cypher)
    resp = requests.post(
        'http://127.0.0.1:8443/v1/graphs/default/query',
        headers={
            'Authorization': 'Bearer local-development-token-32-bytes',
            'X-Graph-Namespace': 'default',
            'Content-Type': 'application/json',
        },
        json={'cell_id': 'cell-0', 'query': cypher},
    )
    print('RESPONSE:', resp.status_code, resp.text)
    return resp.json()

query('CREATE (a {id: 700000101})-[:TEST]->(b {id: 700000102})')
