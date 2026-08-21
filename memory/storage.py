import hashlib
import json
import os
import requests
from typing import Dict, List, Optional, Any

HYDRA_URL = os.environ.get('HYDRA_URL', 'http://127.0.0.1:18443/v1/graphs/default/query')
HYDRA_TOKEN = os.environ.get('HYDRA_TOKEN', 'local-dev-auth-token-32-characters-long')
HYDRA_NAMESPACE = os.environ.get('HYDRA_NAMESPACE', 'local')
ROOT_ID = 900000002
META_ID = 900000001


def _log(msg: str):
    """Console-safe print (Windows cp1252 cannot encode some symbols)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'replace').decode('ascii'))


def stable_id(s: str) -> int:
    h = hashlib.sha256(str(s).encode()).hexdigest()[:12]
    return int(h, 16) % (2**31 - 1)

def escape_cypher_string(s: Optional[str]) -> str:
    if s is None:
        return ''
    s = str(s)
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', ' ')
    s = s.replace('\r', ' ')
    return s

def extract_row_val(item: Any) -> Any:
    if isinstance(item, dict):
        if item.get('type') == 'null':
            return None
        if 'value' in item:
            return item['value']
    return item

class StorageManager:
    """Graph storage on HydraDB. Falls back to an in-memory store when the
    database is unreachable so the rest of the system keeps working."""

    def __init__(self, url: str = HYDRA_URL, token: str = HYDRA_TOKEN):
        self.url = os.environ.get('HYDRA_URL', url)
        self.token = os.environ.get('HYDRA_TOKEN', token)
        self.namespace = os.environ.get('HYDRA_NAMESPACE', HYDRA_NAMESPACE)
        self.connected = True
        self._mem_facts = {}
        self._mem_superseded = set()
        try:
            self.ensure_root()
        except Exception as e:
            _log(f'[!] HydraDB Connection Warning: {e}')
            _log('    Continuing in offline (in-memory) mode - queries will not persist')
            self.connected = False

    # ------------------------------------------------------------ #
    # Low-level query
    # ------------------------------------------------------------ #
    def query(self, cypher: str) -> Dict[str, Any]:
        if not self.connected:
            _log(f'[!] Offline mode: Skipping query - {cypher[:50]}...')
            return {'rows': []}

        try:
            resp = requests.post(
                self.url,
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'X-Graph-Namespace': self.namespace,
                    'Content-Type': 'application/json',
                },
                json={'cell_id': 'cell-0', 'query': cypher},
                timeout=10,
            )
            if resp.status_code != 200:
                _log(f'HydraDB query error: {resp.status_code} {resp.text}')
                _log(f'Failed Cypher: {cypher}')
                resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _log(f'[!] Query failed: {e}')
            self.connected = False
            return {'rows': []}

    def ensure_root(self):
        if not self.connected:
            return
        try:
            res = self.query(f'MATCH (r {{id: {ROOT_ID}}}) RETURN r.id LIMIT 1')
            rows = res.get('rows', [])
            if not rows or not rows[0] or extract_row_val(rows[0][0]) is None:
                self.query(f'CREATE (m {{id: {META_ID}}})-[:ROOT]->(r {{id: {ROOT_ID}}})')
        except Exception as e:
            _log(f'[!] Could not ensure root: {e}')
            self.connected = False

    # ------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------ #
    def create_session(
        self, session_id: str, date_str: str, timestamp: int, user_id: str = 'user_default'
    ) -> int:
        sess_num_id = stable_id(f'session_{session_id}_{timestamp}')
        safe_sid = escape_cypher_string(session_id)
        safe_date = escape_cypher_string(date_str)

        if not self.connected:
            self._mem_facts.setdefault('__sessions__', {})[sess_num_id] = {
                'session_id': session_id,
                'timestamp': timestamp,
                'date_str': date_str,
            }
            return sess_num_id

        try:
            self.query(
                f'CREATE (r {{id: {ROOT_ID}}})-[:HAS_SESSION]->(s {{id: {sess_num_id}, session_id: "{safe_sid}", timestamp: {timestamp}, date_str: "{safe_date}"}})'
            )
        except Exception as e:
            _log(f'[!] Failed to create session: {e}')
            self.connected = False
        return sess_num_id

    # ------------------------------------------------------------ #
    # Facts
    # ------------------------------------------------------------ #
    def create_fact(
        self,
        fact_key: str,
        subject: str,
        predicate: str,
        obj: str,
        text: str,
        timestamp: int,
        session_id: str,
        is_superseded: bool = False,
    ) -> int:
        sess_num_id = self.create_session(session_id, '2024/01/01 00:00', timestamp)
        fact_num_id = stable_id(f'fact_{fact_key}')

        safe_subj = escape_cypher_string(subject)
        safe_pred = escape_cypher_string(predicate)
        safe_obj = escape_cypher_string(obj)
        safe_text = escape_cypher_string(text)
        safe_sid = escape_cypher_string(session_id)
        super_str = 'true' if is_superseded else 'false'

        if not self.connected:
            self._mem_facts[fact_num_id] = {
                'id': fact_num_id,
                'subject': subject,
                'predicate': predicate,
                'object': obj,
                'text': text,
                'timestamp': timestamp,
                'session_id': session_id,
                'is_superseded': is_superseded or (fact_num_id in self._mem_superseded),
            }
            return fact_num_id

        try:
            self.query(
                f'CREATE (s {{id: {sess_num_id}}})-[:HAS_FACT]->(f {{id: {fact_num_id}, subject: "{safe_subj}", predicate: "{safe_pred}", object: "{safe_obj}", text: "{safe_text}", timestamp: {timestamp}, session_id: "{safe_sid}", is_superseded: "{super_str}"}})'
            )
        except Exception as e:
            _log(f'[!] Failed to create fact: {e}')
            self.connected = False
        return fact_num_id

    def mark_superseded(self, old_fact_id: int, new_fact_id: int):
        if not self.connected:
            self._mem_superseded.add(old_fact_id)
            if old_fact_id in self._mem_facts:
                self._mem_facts[old_fact_id]['is_superseded'] = True
            return
        self.query(
            f'CREATE (nf {{id: {new_fact_id}}})-[:SUPERSEDES]->(of {{id: {old_fact_id}}})'
        )

    def get_superseded_fact_ids(self) -> set:
        if not self.connected:
            return set(self._mem_superseded)
        res = self.query('MATCH (nf)-[:SUPERSEDES]->(of) RETURN of.id AS id')
        rows = res.get('rows', [])
        sup_ids = set()
        for r in rows:
            if r and r[0] is not None:
                val = extract_row_val(r[0])
                if val is not None:
                    sup_ids.add(int(val))
        return sup_ids

    def get_all_facts(self) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                dict(f) for f in self._mem_facts.values()
                if isinstance(f, dict) and 'predicate' in f
            ]

        res = self.query(
            'MATCH (s)-[:HAS_FACT]->(f) RETURN f.id AS id, f.text AS text, f.subject AS subject, f.predicate AS predicate, f.object AS object, f.timestamp AS timestamp, f.is_superseded AS is_superseded, f.session_id AS session_id'
        )
        rows = res.get('rows', [])
        sup_ids = self.get_superseded_fact_ids()

        facts = []
        for r in rows:
            if len(r) >= 8 and r[0] is not None:
                f_id = extract_row_val(r[0])
                if f_id is not None and str(f_id).isdigit() and int(f_id) > 0:
                    fact_int_id = int(f_id)
                    is_sup = (fact_int_id in sup_ids) or (str(extract_row_val(r[6])) == 'true')
                    facts.append(
                        {
                            'id': fact_int_id,
                            'text': str(extract_row_val(r[1]) or ''),
                            'subject': str(extract_row_val(r[2]) or ''),
                            'predicate': str(extract_row_val(r[3]) or ''),
                            'object': str(extract_row_val(r[4]) or ''),
                            'timestamp': int(extract_row_val(r[5]))
                            if extract_row_val(r[5]) is not None
                            else 0,
                            'is_superseded': is_sup,
                            'session_id': str(extract_row_val(r[7]) or ''),
                        }
                    )
        return facts