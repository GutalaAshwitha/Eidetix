"""POST /ask — Person 3 reasoning-layer API.

Runs with zero third-party dependencies (stdlib http.server only).

Usage:
    python memory/api.py [port]          # default 8000

Request:
    POST /ask
    {
      "question": "What framework am I currently using?",
      "memories": [ {"subject": "user", "predicate": "uses", "object": "React",
                     "text": "User uses React", "timestamp": 1700000000,
                     "session_id": "session_35", "is_superseded": false,
                     "similarity_score": 0.87} ]
    }

Response:
    {
      "question": "...",
      "answer": "You currently use React.",
      "abstained": false,
      "confidence": 0.86,
      "evidence": ["session_35"]
    }
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from .reasoning import ReasoningEngine
except ImportError:
    from memory.reasoning import ReasoningEngine

ENGINE = ReasoningEngine()


class AskHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "engine": "ReasoningEngine"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            self._send(400, {"error": f"invalid JSON body: {e}"})
            return

        question = body.get("question")
        memories = body.get("memories", [])
        if not question or not isinstance(question, str):
            self._send(400, {"error": "missing 'question' (string)"})
            return
        if not isinstance(memories, list):
            self._send(400, {"error": "'memories' must be a list"})
            return

        result = ENGINE.answer(question, memories)
        result.pop("reason", None)
        self._send(200, result)

    def log_message(self, fmt, *args):
        sys.stderr.write("[ask] " + fmt % args + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("0.0.0.0", port), AskHandler)
    print(f"POST /ask listening on http://0.0.0.0:{port}  (health: /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()