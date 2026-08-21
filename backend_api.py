
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from threading import Lock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import mimetypes
import mimetypes

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from memory.extraction import FactExtractor
from memory.integration import parse_memory_content, to_reasoning_memories
from memory.reasoning import ReasoningEngine
from member2.hydra_client import HydraHttpClient, HYDRA_HTTP_ADDR, HYDRA_TOKEN, HYDRA_NAMESPACE
from member2.hydra_client import live_storage
from member2.retrieve import retrieve as hydra_retrieve

DB_DIR = ROOT / "data"
DB_FILE = DB_DIR / "app.json"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_LOCK = Lock()

if not DB_FILE.exists():
    DB_FILE.write_text(json.dumps({
        "users": [],
        "conversations": [],
        "messages": [],
    }, indent=2), encoding="utf-8")


def read_db():
    with DB_LOCK:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))


def write_db(db):
    with DB_LOCK:
        tmp = DB_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(db, indent=2), encoding="utf-8")
        tmp.replace(DB_FILE)


def new_id():
    return str(uuid.uuid4())


def now():
    return time.time()


# ---------------------------------------------------------------------------
# Hydra connection
# ---------------------------------------------------------------------------

STORAGE = live_storage()
HYDRA_LIVE = False

try:
    probe = HydraHttpClient(
        base_url=HYDRA_HTTP_ADDR,
        token=HYDRA_TOKEN,
        namespace=HYDRA_NAMESPACE,
    )
    probe.execute("MATCH (a {id: 0}) RETURN a.id")
    HYDRA_LIVE = True
except Exception as exc:
    print(f"[hydra] not connected: {exc}")


# ---------------------------------------------------------------------------
# HTML / URL ingestion
# ---------------------------------------------------------------------------

class VisibleTextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg"}
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.parts.append(value)

    def text(self):
        return "\n".join(self.parts)


PROVIDER_LABELS = (
    "user", "human", "me", "you",
    "assistant", "ai", "bot",
    "qwen", "chatgpt", "claude", "gemini", "copilot",
)


def detect_provider(text="", url=""):
    s = f"{url} {text}".lower()
    if "qwen" in s:
        return "Qwen"
    if "chatgpt" in s or "openai" in s:
        return "ChatGPT"
    if "claude" in s or "anthropic" in s:
        return "Claude"
    if "gemini" in s or "google ai" in s:
        return "Gemini"
    if "copilot" in s:
        return "Copilot"
    return "Imported AI"


def fetch_public_url(url):
    import requests
    r = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Eidetix/1.0 conversation-ingestor",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain",
        },
    )
    r.raise_for_status()
    content_type = r.headers.get("content-type", "")
    if "html" in content_type:
        parser = VisibleTextParser()
        parser.feed(r.text)
        return parser.text()
    return r.text


def parse_conversation(text):
    lines = [x.strip() for x in str(text).splitlines() if x.strip()]
    messages = []
    role = None
    buf = []

    user_re = re.compile(r"^(user|human|me|you)\s*:\s*(.*)$", re.I)
    ai_re = re.compile(r"^(assistant|ai|bot|qwen|chatgpt|claude|gemini|copilot)\s*:\s*(.*)$", re.I)

    def flush():
        nonlocal buf
        if buf:
            messages.append({
                "role": role or "user",
                "content": " ".join(buf).strip(),
            })
        buf = []

    for line in lines:
        um = user_re.match(line)
        am = ai_re.match(line)
        if um:
            flush()
            role = "user"
            buf = [um.group(2)]
        elif am:
            flush()
            role = "assistant"
            buf = [am.group(2)]
        else:
            buf.append(line)
    flush()

    if not messages:
        messages = [{"role": "user", "content": str(text).strip()}]

    return messages


def conversation_title(messages, provider):
    for m in messages:
        if m["role"] == "user" and m["content"].strip():
            return m["content"].strip()[:55]
    return f"{provider} conversation"


# ---------------------------------------------------------------------------
# Backend memory operations
# ---------------------------------------------------------------------------

EXTRACTOR = FactExtractor()
REASONER = ReasoningEngine()


def ensure_hydra_user(user):
    if user.get("hydra_user_id"):
        return user["hydra_user_id"]

    huser = STORAGE.create_user(user["name"])
    user["hydra_user_id"] = str(huser.id)

    db = read_db()
    for item in db["users"]:
        if item["id"] == user["id"]:
            item["hydra_user_id"] = user["hydra_user_id"]
            break
    write_db(db)
    return user["hydra_user_id"]


def user_record(user_id):
    db = read_db()
    return next((u for u in db["users"] if u["id"] == user_id), None)



def augment_rule_facts(messages, timestamp):
    """Small compatibility layer for UI imports.

    The repository's FactExtractor is intentionally conservative. The web
    ingest surface also needs common conversational forms such as:
      "I'm using React"
      "I switched to Vue"
      "I'm working on ChronoMemory"
      "my favorite movie is Inception"
    We add only facts that the repository extractor did not already emit.
    """
    facts = []
    for turn in messages:
        if str(turn.get("role", "")).lower() != "user":
            continue
        text = str(turn.get("content", "")).strip()
        patterns = [
            (r"\bI(?:'m| am)\s+(?:currently\s+)?using\s+([A-Za-z0-9 .+#_-]{2,50})",
             "uses", "User uses {}"),
            (r"\bI\s+(?:switched|moved)\s+(?:back\s+)?to\s+([A-Za-z0-9 .+#_-]{2,50})",
             "uses", "User switched to {}"),
            (r"\bI(?:'m| am)\s+(?:currently\s+)?working\s+on\s+([A-Za-z0-9 .+#_-]{2,60})",
             "works_on", "User works on {}"),
            (r"\bI(?:'m| am)\s+building\s+([A-Za-z0-9 .+#_-]{2,60})",
             "works_on", "User is building {}"),
            (r"\bmy\s+favorite\s+([A-Za-z ]{2,30})\s+is\s+([A-Za-z0-9 .,'!#_-]{2,60})",
             "favorite", None),
            (r"\bI\s+(?:prefer|like|love)\s+([A-Za-z0-9 .,'!#_+-]{2,60})",
             "prefers", "User prefers {}"),
        ]
        for pattern, predicate, template in patterns:
            for match in re.finditer(pattern, text, re.I):
                if predicate == "favorite":
                    category = match.group(1).strip().replace(" ", "_")
                    value = match.group(2).strip().rstrip(".!?")
                    facts.append({
                        "subject": "user",
                        "predicate": f"favorite_{category}",
                        "object": value,
                        "text": f"User's favorite {match.group(1).strip()} is {value}",
                        "timestamp": timestamp,
                    })
                else:
                    value = match.group(1).strip().rstrip(".!?")
                    facts.append({
                        "subject": "user",
                        "predicate": predicate,
                        "object": value,
                        "text": template.format(value),
                        "timestamp": timestamp,
                    })
    return facts


def existing_user_facts(hydra_user_id):
    rows = STORAGE.get_memories_for_user(hydra_user_id, limit=1000)
    out = []
    for row in rows:
        parsed = parse_memory_content(row.get("m.content", ""))
        out.append({
            "id": row.get("m.id"),
            "subject": parsed["subject"],
            "predicate": parsed["predicate"],
            "object": parsed["object"],
            "text": row.get("m.content", ""),
            "timestamp": float(row.get("m.ts") or 0),
            "is_superseded": not bool(row.get("m.valid", True)),
        })
    return out


def ingest_into_hydra(user, messages, session_id, timestamp):
    hydra_user_id = ensure_hydra_user(user)
    session = STORAGE.create_session(
        hydra_user_id,
        started_at=timestamp,
    )

    for message in messages:
        STORAGE.create_message(
            session.id,
            message["role"],
            message["content"],
            ts=timestamp,
        )

    facts = EXTRACTOR.extract_facts(
        messages,
        int(timestamp),
    )

    # Extend the repository extractor for natural web-chat phrasing.
    extra_facts = augment_rule_facts(messages, int(timestamp))
    seen = {
        (
            str(f.get("predicate", "")).lower(),
            str(f.get("object", "")).strip().lower(),
        )
        for f in facts
    }
    for fact in extra_facts:
        key = (
            str(fact.get("predicate", "")).lower(),
            str(fact.get("object", "")).strip().lower(),
        )
        if key not in seen:
            facts.append(fact)
            seen.add(key)

    old_facts = existing_user_facts(hydra_user_id)
    created = []

    # One entity per distinct memory object, matching the repository's graph
    # design.
    entity_map = {}

    for fact in facts:
        content = fact.get("text") or (
            f"User {fact.get('predicate', 'related to')} "
            f"{fact.get('object', '')}"
        )
        memory = STORAGE.create_memory(
            content,
            ts=float(fact.get("timestamp") or timestamp),
        )
        STORAGE.link_has_memory(
            hydra_user_id,
            memory.id,
        )
        STORAGE.link_occurred_in(
            memory.id,
            session.id,
        )

        obj = str(fact.get("object") or "").strip()
        if obj:
            key = obj.lower()
            if key not in entity_map:
                entity_map[key] = STORAGE.create_entity(
                    obj,
                    fact.get("predicate") or "entity",
                )
            STORAGE.link_mentions(
                memory.id,
                entity_map[key].id,
                confidence=0.95,
            )

        new_pred = str(fact.get("predicate") or "").lower()
        new_obj = obj.lower()

        # Temporal supersession: a newer fact with the same semantic predicate
        # but a different value supersedes the older value.
        for old in old_facts:
            if old.get("is_superseded"):
                continue
            if float(old.get("timestamp") or 0) >= float(timestamp):
                continue
            old_pred = str(old.get("predicate") or "").lower()
            old_obj = str(old.get("object") or "").lower()
            if old_pred == new_pred and old_obj != new_obj:
                try:
                    STORAGE.link_supersedes(
                        str(memory.id),
                        str(old["id"]),
                    )
                except Exception as exc:
                    print("[hydra] supersede warning:", exc)

        created.append({
            "id": str(memory.id),
            "subject": fact.get("subject", "user"),
            "predicate": fact.get("predicate", ""),
            "object": fact.get("object", ""),
            "text": content,
            "timestamp": float(fact.get("timestamp") or timestamp),
            "session_id": str(session.id),
            "status": "current",
            "provider": "",
        })

        old_facts.append({
            "id": memory.id,
            "subject": fact.get("subject", "user"),
            "predicate": fact.get("predicate", ""),
            "object": fact.get("object", ""),
            "text": content,
            "timestamp": float(fact.get("timestamp") or timestamp),
            "is_superseded": False,
        })

    return session, created


def user_memory_rows(user):
    hydra_user_id = user.get("hydra_user_id")
    if not hydra_user_id:
        return []
    return STORAGE.get_memories_for_user(
        hydra_user_id,
        limit=1000,
    )


def structured_memories(user):
    rows = user_memory_rows(user)
    memories = []
    for row in rows:
        content = row.get("m.content", "")
        parsed = parse_memory_content(content)
        memories.append({
            "id": str(row.get("m.id")),
            "subject": parsed["subject"],
            "predicate": parsed["predicate"],
            "object": parsed["object"],
            "text": content,
            "createdAt": float(row.get("m.ts") or 0),
            "timestamp": float(row.get("m.ts") or 0),
            "status": "current" if bool(row.get("m.valid", True)) else "superseded",
            "provider": "Eidetix backend",
        })
    return memories


def answer_question(user, question):
    hydra_user_id = user.get("hydra_user_id")
    if not hydra_user_id:
        return {
            "reply": "I don't have enough evidence in your memory yet. Ingest a conversation first.",
            "abstained": True,
            "confidence": 0.0,
            "evidence": [],
        }

    # Use the repository's actual entity retrieval + temporal reasoning.
    retrieved = hydra_retrieve(
        STORAGE,
        question,
        evidence_limit=5,
    )

    user_rows = user_memory_rows(user)
    allowed_ids = {str(r.get("m.id")) for r in user_rows}

    retrieved["memories"] = [
        m for m in retrieved.get("memories", [])
        if str(m.get("m.id")) in allowed_ids
    ]
    retrieved["evidence"] = [
        e for e in retrieved.get("evidence", [])
        if str(e.get("memory_id")) in allowed_ids
    ]
    retrieved["timeline"] = [
        t for t in retrieved.get("timeline", [])
        if str(t.get("memory_id", "")) in allowed_ids
        or not t.get("memory_id")
    ]

    # Generic questions ("where do I live?", "what do you remember?")
    # may not name an entity. In that case reason over this user's graph only.
    if not retrieved["memories"]:
        retrieved["memories"] = [
            {
                "m.id": r.get("m.id"),
                "m.content": r.get("m.content"),
                "m.ts": r.get("m.ts"),
                "m.valid": r.get("m.valid"),
            }
            for r in user_rows
        ]

        # Build evidence for the fallback path too, so an answer is never
        # shown as "evidence checked" without a source message.
        fallback_evidence = []
        for row in retrieved["memories"][:10]:
            try:
                msgs = STORAGE.get_evidence_for_memory(
                    row["m.id"],
                    limit=5,
                )
            except Exception:
                msgs = []
            if msgs:
                fallback_evidence.append({
                    "memory_id": row["m.id"],
                    "session_id": None,
                    "messages": msgs,
                })
        retrieved["evidence"] = fallback_evidence

    reasoning_memories = to_reasoning_memories(retrieved)
    result = REASONER.answer(
        question,
        reasoning_memories,
    )

    # Keep the backend's evidence contract, but make it easy for the UI to show.
    evidence_ids = set(result.get("evidence", []) or [])
    evidence = []
    for item in retrieved.get("evidence", []):
        if not evidence_ids or str(item.get("session_id")) in {str(x) for x in evidence_ids}:
            evidence.append(item)

    if not evidence:
        evidence = retrieved.get("evidence", [])[:5]

    return {
        "reply": result.get("answer") or result.get("response") or
                 "I don't have enough evidence to answer that.",
        "abstained": bool(result.get("abstained", False)),
        "confidence": float(result.get("confidence", 0.0) or 0.0),
        "evidence": evidence,
        "timeline": retrieved.get("timeline", []),
    }


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "EidetixBackend/1.0"

    def send_json(self, status, payload):
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json(204, {})

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Serve React/Vite frontend
        if not path.startswith("/api/"):
            try:
                dist = ROOT / "dist"
                requested = dist / path.lstrip("/") if path != "/" else dist / "index.html"

                # Prevent path traversal
                if not str(requested.resolve()).startswith(str(dist.resolve())):
                    return self.send_json(403, {"error": "Forbidden"})

                if requested.is_file():
                    content = requested.read_bytes()
                    content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

                # React SPA fallback
                index = dist / "index.html"
                content = index.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as exc:
                print("[static] error:", repr(exc))
                return self.send_json(500, {"error": str(exc)})

        
        # Serve React/Vite frontend
        if not path.startswith("/api/"):
            dist = ROOT / "dist"
            requested = dist / path.lstrip("/") if path != "/" else dist / "index.html"

            if requested.is_file():
                content = requested.read_bytes()
                content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            index = dist / "index.html"
            content = index.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        try:
            if path == "/api/health":
                return self.send_json(200, {
                    "ok": True,
                    "backend": "Eidetix memory backend",
                    "hydraDb": HYDRA_LIVE,
                })

            if path == "/api/hydradb/status":
                return self.send_json(200, {
                    "configured": bool(os.environ.get("HYDRA_HTTP_ADDR")),
                    "connected": HYDRA_LIVE,
                    "endpoint": HYDRA_HTTP_ADDR if HYDRA_LIVE else None,
                })

            if path == "/api/conversations":
                from urllib.parse import parse_qs
                user_id = parse_qs(parsed.query).get("userId", [""])[0]
                db = read_db()
                rows = [
                    c for c in db["conversations"]
                    if c["userId"] == user_id
                ]
                rows.sort(key=lambda x: x["updatedAt"], reverse=True)
                return self.send_json(200, rows)

            if path == "/api/memories":
                from urllib.parse import parse_qs
                user_id = parse_qs(parsed.query).get("userId", [""])[0]
                user = user_record(user_id)
                if not user:
                    return self.send_json(404, {"error": "User not found"})
                return self.send_json(200, structured_memories(user))

            if path == "/api/messages":
                from urllib.parse import parse_qs
                q = parse_qs(parsed.query)
                user_id = q.get("userId", [""])[0]
                conversation_id = q.get("conversationId", [""])[0]
                db = read_db()
                rows = [
                    m for m in db["messages"]
                    if m["userId"] == user_id and
                    m["conversationId"] == conversation_id
                ]
                rows.sort(key=lambda x: x["createdAt"])
                return self.send_json(200, rows)

            return self.send_json(404, {"error": "API route not found."})

        except Exception as exc:
            print("[api] GET error:", repr(exc))
            return self.send_json(500, {"error": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            body = self.read_json()

            if path == "/api/signup":
                name = str(body.get("name", "")).strip()
                email = str(body.get("email", "")).strip().lower()
                phone = str(body.get("phone", "")).strip()
                password = str(body.get("password", ""))

                if not name or not email or not password:
                    return self.send_json(400, {
                        "error": "Name, email and password are required."
                    })

                db = read_db()
                if any(u["email"] == email for u in db["users"]):
                    return self.send_json(409, {
                        "error": "An account with that email already exists."
                    })

                user = {
                    "id": new_id(),
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "password": password,
                    "createdAt": now(),
                    "hydra_user_id": None,
                }

                db["users"].append(user)
                write_db(db)

                # Create the actual user node in the backend graph.
                try:
                    ensure_hydra_user(user)
                except Exception as exc:
                    print("[hydra] user creation warning:", exc)

                return self.send_json(200, {
                    "ok": True,
                    "forceLogin": True,
                })

            if path == "/api/login":
                email = str(body.get("email", "")).strip().lower()
                password = str(body.get("password", ""))
                db = read_db()
                user = next(
                    (
                        u for u in db["users"]
                        if u["email"] == email and
                        u["password"] == password
                    ),
                    None,
                )
                if not user:
                    return self.send_json(401, {
                        "error": "Invalid email or password."
                    })

                try:
                    ensure_hydra_user(user)
                except Exception:
                    pass

                return self.send_json(200, {
                    "user": {
                        "id": user["id"],
                        "name": user["name"],
                        "email": user["email"],
                        "phone": user.get("phone", ""),
                    }
                })

            if path == "/api/forgot":
                return self.send_json(200, {
                    "ok": True,
                    "message": "If that email exists, recovery instructions would be sent in production."
                })

            if path == "/api/ingest":
                user = user_record(str(body.get("userId", "")))
                if not user:
                    return self.send_json(404, {"error": "User not found."})

                text = str(body.get("text", "") or "").strip()
                url = str(body.get("url", "") or "").strip()
                forced_provider = str(body.get("provider", "") or "").strip()

                if url and not text:
                    try:
                        text = fetch_public_url(url)
                    except Exception as exc:
                        return self.send_json(422, {
                            "error": f"Could not fetch that public URL: {exc}"
                        })

                if not text:
                    return self.send_json(400, {
                        "error": "Paste a conversation or provide a public URL."
                    })

                provider = forced_provider or detect_provider(text, url)
                messages = parse_conversation(text)
                title = str(body.get("title", "") or "").strip() or conversation_title(messages, provider)

                conversation_id = new_id()
                timestamp = now()
                session_id = new_id()

                db = read_db()
                db["conversations"].append({
                    "id": conversation_id,
                    "userId": user["id"],
                    "title": title,
                    "provider": provider,
                    "sourceUrl": url,
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                    "pinned": False,
                    "sessionId": session_id,
                })

                for i, message in enumerate(messages):
                    db["messages"].append({
                        "id": new_id(),
                        "userId": user["id"],
                        "conversationId": conversation_id,
                        "role": message["role"],
                        "content": message["content"],
                        "createdAt": timestamp + i / 1000.0,
                    })

                write_db(db)

                session, memories = ingest_into_hydra(
                    user,
                    messages,
                    session_id,
                    timestamp,
                )

                for memory in memories:
                    memory["provider"] = provider

                return self.send_json(200, {
                    "ok": True,
                    "conversation": db["conversations"][-1],
                    "messages": messages,
                    "memories": memories,
                    "hydraDb": HYDRA_LIVE,
                })

            if path == "/api/chat":
                user = user_record(str(body.get("userId", "")))
                if not user:
                    return self.send_json(404, {"error": "User not found."})

                text = str(body.get("text", "") or "").strip()
                if not text:
                    return self.send_json(400, {"error": "Missing chat message."})

                conversation_id = body.get("conversationId")
                db = read_db()
                conversation = next(
                    (
                        c for c in db["conversations"]
                        if c["id"] == conversation_id and
                        c["userId"] == user["id"]
                    ),
                    None,
                )

                if not conversation:
                    conversation = {
                        "id": new_id(),
                        "userId": user["id"],
                        "title": text[:55],
                        "provider": "Eidetix",
                        "sourceUrl": "",
                        "createdAt": now(),
                        "updatedAt": now(),
                        "pinned": False,
                        "sessionId": new_id(),
                    }
                    db["conversations"].append(conversation)

                db["messages"].append({
                    "id": new_id(),
                    "userId": user["id"],
                    "conversationId": conversation["id"],
                    "role": "user",
                    "content": text,
                    "createdAt": now(),
                })

                result = answer_question(user, text)

                db["messages"].append({
                    "id": new_id(),
                    "userId": user["id"],
                    "conversationId": conversation["id"],
                    "role": "assistant",
                    "content": result["reply"],
                    "createdAt": now(),
                })

                conversation["updatedAt"] = now()
                write_db(db)

                return self.send_json(200, {
                    "conversation": conversation,
                    **result,
                })

            return self.send_json(404, {"error": "API route not found."})

        except Exception as exc:
            import traceback
            traceback.print_exc()
            return self.send_json(500, {
                "error": f"Eidetix backend error: {exc}"
            })

    def do_PATCH(self):
        path = urlparse(self.path).path

        try:
            body = self.read_json()

            match = re.fullmatch(r"/api/conversations/([^/]+)", path)
            if not match:
                return self.send_json(404, {"error": "API route not found."})

            conversation_id = match.group(1)
            user_id = str(body.get("userId", ""))

            db = read_db()
            conversation = next(
                (
                    c for c in db["conversations"]
                    if c["id"] == conversation_id and
                    c["userId"] == user_id
                ),
                None,
            )

            if not conversation:
                return self.send_json(404, {
                    "error": "Conversation not found."
                })

            if isinstance(body.get("pinned"), bool):
                conversation["pinned"] = body["pinned"]

            conversation["updatedAt"] = now()
            write_db(db)

            return self.send_json(200, conversation)

        except Exception as exc:
            print("[api] PATCH error:", repr(exc))
            return self.send_json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("[api]", fmt % args)


def main():
    port = int(os.environ.get("PORT", os.environ.get("EIDETIX_API_PORT", "8787")))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Eidetix backend API running at http://localhost:{port}")
    print(f"HydraDB connected: {HYDRA_LIVE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEidetix backend stopped.")


if __name__ == "__main__":
    main()


