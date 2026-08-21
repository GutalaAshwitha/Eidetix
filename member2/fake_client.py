"""In-memory fake HydraDB client, ONLY for local testing of retrieve.py's
logic/shape. Implements the same execute(cypher, params) surface as the real
driver would, but against Python dicts instead of the real engine. This is
not a substitute for testing against the real HydraDB — just a way to prove
the retrieval logic is correct before wiring it up.
"""
import re


class FakeConn:
    def __init__(self):
        self.nodes = {}   # label -> {id: {props}}
        self.edges = []   # (type, src_id, dst_id, props)

    def execute(self, cypher, params):
        cypher_norm = " ".join(cypher.split())

        # CREATE (x:Label {...})
        m = re.match(r"CREATE \((\w+):(\w+) \{(.+?)\}\)$", cypher_norm)
        if m:
            _, label, _ = m.groups()
            props = {k: params[k] for k in params}
            self.nodes.setdefault(label, {})[props["id"]] = props
            return []

        # MATCH (a:L1 {id: $x}), (b:L2 {id: $y}) CREATE (a)-[:TYPE {...}]->(b)
        m = re.match(
            r"MATCH \((\w+):(\w+) \{id: \$(\w+)\}\), \((\w+):(\w+) \{id: \$(\w+)\}\) "
            r"CREATE \(\w+\)-\[:(\w+)(?:\s*\{(.+?)\})?\]->\(\w+\)$",
            cypher_norm,
        )
        if m:
            _, _, src_key, _, _, dst_key, rel_type, _ = m.groups()
            src_id, dst_id = params[src_key], params[dst_key]
            edge_props = {k: v for k, v in params.items() if k not in (src_key, dst_key)}
            self.edges.append((rel_type, src_id, dst_id, edge_props))
            return []

        # SET old.valid = false
        m = re.match(r"MATCH \((\w+):Memory \{id: \$old_id\}\) SET \w+\.valid = false$", cypher_norm)
        if m:
            self.nodes["Memory"][params["old_id"]]["valid"] = False
            return []

        # MATCH (e:Entity) RETURN e.id, e.name, e.type
        if cypher_norm == "MATCH (e:Entity) RETURN e.id, e.name, e.type":
            return [{"e.id": n["id"], "e.name": n["name"], "e.type": n["type"]}
                    for n in self.nodes.get("Entity", {}).values()]

        # MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:Memory) RETURN ... ORDER BY m.ts DESC LIMIT $limit
        if "MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:Memory)" in cypher_norm:
            uid = params["user_id"]
            out = []
            for (etype, src, dst, props) in self.edges:
                if etype == "HAS_MEMORY" and src == uid:
                    mem = self.nodes["Memory"][dst]
                    out.append({"m.id": mem["id"], "m.content": mem["content"],
                                "m.ts": mem["ts"], "m.valid": mem["valid"]})
            out.sort(key=lambda r: r["m.ts"], reverse=True)
            return out[: int(params.get("limit", 50))]

        # MATCH (m:Memory)-[:MENTIONS]->(e:Entity {id: $entity_id}) RETURN ...
        if "MATCH (m:Memory)-[:MENTIONS]->(e:Entity {id: $entity_id})" in cypher_norm:
            eid = params["entity_id"]
            out = []
            for (etype, src, dst, props) in self.edges:
                if etype == "MENTIONS" and dst == eid:
                    mem = self.nodes["Memory"][src]
                    out.append({"m.id": mem["id"], "m.content": mem["content"],
                                "m.ts": mem["ts"], "m.valid": mem["valid"]})
            return out

        # MATCH (a:Entity {id: $entity_id})-[r:RELATED_TO]->(b:Entity) RETURN ...
        if "MATCH (a:Entity {id: $entity_id})-[r:RELATED_TO]->(b:Entity)" in cypher_norm:
            eid = params["entity_id"]
            out = []
            for (etype, src, dst, props) in self.edges:
                if etype == "RELATED_TO" and src == eid:
                    ent = self.nodes["Entity"][dst]
                    out.append({"b.id": ent["id"], "b.name": ent["name"],
                                "b.type": ent["type"], "r.weight": props.get("weight", 1.0)})
            return out

        # MATCH (m:Memory {id: $memory_id})-[:OCCURRED_IN]->(s:Session) RETURN ...
        if "MATCH (m:Memory {id: $memory_id})-[:OCCURRED_IN]->(s:Session)" in cypher_norm:
            mid = params["memory_id"]
            for (etype, src, dst, props) in self.edges:
                if etype == "OCCURRED_IN" and src == mid:
                    s = self.nodes["Session"][dst]
                    if "s.id, m.ts" in cypher_norm:
                        mem = self.nodes["Memory"][mid]
                        return [{"s.id": s["id"], "m.ts": mem["ts"]}]
                    return [{"s.id": s["id"], "s.user_id": s["user_id"], "s.started_at": s["started_at"]}]
            return []

        # MATCH (msg:Message {session_id: $session_id}) WHERE msg.ts <= $memory_ts RETURN ...
        if "MATCH (msg:Message {session_id: $session_id})" in cypher_norm and "memory_ts" in params:
            sid, mts, limit = params["session_id"], params["memory_ts"], params["limit"]
            msgs = [n for n in self.nodes.get("Message", {}).values()
                    if n["session_id"] == sid and n["ts"] <= mts]
            msgs.sort(key=lambda x: x["ts"], reverse=True)
            return [{"msg.id": m["id"], "msg.text": m["text"], "msg.role": m["role"], "msg.ts": m["ts"]}
                    for m in msgs[:limit]]

        raise NotImplementedError(f"Fake client doesn't handle: {cypher_norm}")
