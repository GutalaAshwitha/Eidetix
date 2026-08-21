from memory.storage import StorageManager

s = StorageManager()

query = 'CREATE (a {id: 1010})-[:FOLLOWS]->(b {id: 1020})'
res = s.query(query)
print("Create result:", res)

res2 = s.query('MATCH (a {id: 1010})-[:FOLLOWS]->(b) RETURN b.id AS id')
print("Match result:", res2)
