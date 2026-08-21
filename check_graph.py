from memory.storage import StorageManager

s = StorageManager()

print("Root node id:", s.query('MATCH (r {id: 900000002}) RETURN r.id AS id'))
print("Sessions connected to root:", s.query('MATCH (r {id: 900000002})-[:HAS_SESSION]->(s) RETURN s.id AS id, s.session_id AS session_id'))
print("All facts connected to any session:", s.query('MATCH (s)-[:HAS_FACT]->(f) RETURN f.id AS id, f.text AS text, f.subject AS subject, f.predicate AS predicate, f.object AS object, f.timestamp AS timestamp, f.is_superseded AS is_superseded, f.session_id AS session_id'))
