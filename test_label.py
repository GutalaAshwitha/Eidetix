from memory.storage import StorageManager

s = StorageManager()

# Create fresh 1-hop edge
s.query('CREATE (sess {id: 920000001, session_id: "s1"})-[:HAS_FACT]->(f {id: 920000002, text: "User owns Honda", timestamp: 1700000000})')
s.query('MATCH (f {id: 920000002}) SET f:Fact')

res1 = s.query('MATCH (sess {id: 920000001})-[:HAS_FACT]->(f) RETURN f.id AS id, f.text AS text')
print("Match HAS_FACT edge:", res1)
