"""Real HTTP client for the live HydraDB dev node.

Member 2's HydraDBClient assumed a driver with execute(cypher, params).
The live HTTP API (confirmed on the dev node) accepts ONLY inline literal
values -- there is no $parameter substitution in the JSON envelope
("missing OpenCypher query parameter $x" for every params shape tried).

This client therefore substitutes $name placeholders into the query text
with safely-escaped literal values, then POSTs the exact envelope shape
the server expects ({"cell_id", "query"}), mapping the typed result rows
back into column-keyed dicts identical to what the fake client returns.

Usage:
    from member2.hydra_client import live_storage
    storage = live_storage()            # real node, or fake-client fallback
    storage.create_user("Dheeraj")      # now persisted in HydraDB
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .storage import HydraStorage, HydraDBClient

HYDRA_HTTP_ADDR = os.environ.get("HYDRA_HTTP_ADDR", "http://127.0.0.1:18443")
HYDRA_TOKEN = os.environ.get(
    "HYDRA_TOKEN", "local-dev-auth-token-32-characters-long"
)
HYDRA_NAMESPACE = os.environ.get("HYDRA_NAMESPACE", "local")
HYDRA_CELL_ID = os.environ.get("HYDRA_CELL_ID", "cell-0")

_PARAM_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _esc(value: Any) -> str:
    """Render a Python value as a Cypher literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    s = str(value).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    return f'"{s}"'


def substitute(cypher: str, params: Optional[Dict[str, Any]]) -> str:
    """Replace $name placeholders with literal values (params may be keyed
    with or without the leading '$')."""
    if not params:
        return cypher
    lookup = {k.lstrip("$"): v for k, v in params.items()}

    def repl(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name not in lookup:
            raise KeyError(f"no value supplied for query parameter ${name}")
        return _esc(lookup[name])

    return _PARAM_RE.sub(repl, cypher)


def _value(item: Any) -> Any:
    """Unwrap the server's typed value envelope, e.g. {"type":"vertex_id","value":2}."""
    if isinstance(item, dict) and "value" in item:
        return item["value"]
    return item


class HydraHttpClient:
    """execute(cypher, params) -> list[dict], matching HydraDBClient's surface
    but talking to the real HTTP API. Columns keep their projected names
    ("m.id", "b.content", "count(*)"), same as the fake client."""

    def __init__(
        self,
        base_url: str = HYDRA_HTTP_ADDR,
        token: str = HYDRA_TOKEN,
        namespace: str = HYDRA_NAMESPACE,
        cell_id: str = HYDRA_CELL_ID,
        timeout: int = 15,
    ):
        self.url = f"{base_url.rstrip('/')}/v1/graphs/default/query"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "X-Graph-Namespace": namespace,
            "Content-Type": "application/json",
        }
        self.cell_id = cell_id
        self.timeout = timeout

    def execute(
        self, cypher: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if requests is None:  # pragma: no cover
            raise RuntimeError("requests is not installed")
        query = substitute(cypher, params)
        resp = requests.post(
            self.url,
            headers=self.headers,
            json={"cell_id": self.cell_id, "query": query},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"HydraDB {resp.status_code}: {resp.text[:300]} for query: {query}"
            )
        envelope = resp.json()
        columns = envelope.get("columns", [])
        rows = envelope.get("rows", [])
        return [
            {columns[i]: _value(cell) for i, cell in enumerate(row)}
            for row in rows
        ]


def live_storage(
    base_url: str = HYDRA_HTTP_ADDR,
    token: str = HYDRA_TOKEN,
    namespace: str = HYDRA_NAMESPACE,
) -> HydraStorage:
    """Return a HydraStorage backed by the real HTTP node. If the node is
    unreachable or the live build still fails, fall back to the in-memory
    fake client so the rest of the system never breaks."""
    try:
        client = HydraHttpClient(base_url=base_url, token=token, namespace=namespace)
        # prove the node answers before committing to it
        client.execute("MATCH (a {id: 0})-[:FOLLOWS]->(b {id: 0}) RETURN b.id")
        from .hydra_storage import HydraHttpStorage

        return HydraHttpStorage(client)
    except Exception as e:
        from .fake_client import FakeConn

        print(f"[hydra] live node unavailable ({e}); using in-memory fake client")
        return HydraStorage(HydraDBClient(FakeConn()))