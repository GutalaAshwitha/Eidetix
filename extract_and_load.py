import hashlib
import json
import os
import requests
from datetime import datetime
from groq import Groq

HYDRA_URL = "http://127.0.0.1:8443/v1/graphs/default/query"
HYDRA_TOKEN = "local-development-token-32-bytes"
GROQ_MODEL = "llama-3.3-70b-versatile"

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

META_ID = None
ROOT_ID = None


def stable_id(s):
    h = hashlib.sha256(s.encode()).hexdigest()[:12]
    return int(h, 16) % (2**31 - 1)


def escape_cypher_string(s):
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", " ")
    s = s.replace("\r", " ")
    return s


def hydra_query(cypher):
    resp = requests.post(
        HYDRA_URL,
        headers={
            "Authorization": f"Bearer {HYDRA_TOKEN}",
            "X-Graph-Namespace": "default",
            "Content-Type": "application/json",
        },
        json={"cell_id": "cell-0", "query": cypher},
    )
    if resp.status_code != 200:
        print("HydraDB error:", resp.status_code, resp.text)
        print("Query was:", cypher)
        resp.raise_for_status()
    return resp.json()


def ensure_root():
    global META_ID, ROOT_ID
    META_ID = 900000001
    ROOT_ID = 900000002

    # Check if it already exists first - never blindly CREATE/MERGE the same id twice
    result = hydra_query(f'MATCH (r {{id: {ROOT_ID}}}) RETURN r.id AS id')
    if result.get("rows"):
        print(f"Root already exists (id={ROOT_ID}).")
        return

    # Bare CREATE, no labels, no extra props - matches the pattern that worked earlier
    hydra_query(f'CREATE (m {{id: {META_ID}}})-[:ROOT]->(r {{id: {ROOT_ID}}})')

    # Add labels afterward via SET, which is documented as supported after MATCH
    hydra_query(f'MATCH (m {{id: {META_ID}}}) SET m:Meta')
    hydra_query(f'MATCH (r {{id: {ROOT_ID}}}) SET r:Root')

    print(f"Created Root anchor node (id={ROOT_ID}).")


def parse_date(date_str):
    clean = date_str.split(" (")[0] + " " + date_str.split(") ")[1]
    dt = datetime.strptime(clean, "%Y/%m/%d %H:%M")
    return int(dt.timestamp())


def extract_facts(session_turns):
    convo_text = "\n".join(
        f"{t['role'].upper()}: {t['content']}" for t in session_turns
    )
    prompt = f"""Extract discrete, atomic facts about the USER from this conversation.
Only extract facts stated by or clearly about the user (not general advice).
Return ONLY a JSON array of short fact strings, nothing else. Example:
["User's dog is named Leo", "User lives in Pune"]

Conversation:
{convo_text}
"""
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        facts = json.loads(text)
        return [f for f in facts if isinstance(f, str)]
    except json.JSONDecodeError:
        print("  [!] Could not parse facts, raw output was:", text[:200])
        return []


def load_question_into_graph(question):
    qid = question["question_id"]
    print(f"\n=== Loading question {qid} ===")
    print("Question:", question["question"])

    sessions = question["haystack_sessions"]
    dates = question["haystack_dates"]

    fact_counter = 0
    for i, (session, date_str) in enumerate(zip(sessions, dates)):
        session_id = stable_id(f"{qid}_session_{i}")
        ts = parse_date(date_str)
        safe_date_str = escape_cypher_string(date_str)
        safe_qid = escape_cypher_string(qid)

        hydra_query(
            f'CREATE (r {{id: {ROOT_ID}}})-[:HAS_SESSION]->'
            f'(s {{id: {session_id}, question_id: "{safe_qid}", timestamp: {ts}, date_str: "{safe_date_str}"}})'
        )
        hydra_query(f'MATCH (s {{id: {session_id}}}) SET s:Session')

        facts = extract_facts(session)
        print(f"  Session {i} ({date_str}): {len(facts)} facts extracted")

        for fact_text in facts:
            fact_counter += 1
            fact_id = stable_id(f"{qid}_fact_{fact_counter}")
            safe_fact_text = escape_cypher_string(fact_text)

            hydra_query(
                f'CREATE (s {{id: {session_id}}})-[:HAS_FACT]->'
                f'(f {{id: {fact_id}, text: "{safe_fact_text}", timestamp: {ts}, question_id: "{safe_qid}"}})'
            )
            hydra_query(f'MATCH (f {{id: {fact_id}}}) SET f:Fact')
            print(f"    - {fact_text}")

    print(f"Done. Loaded {fact_counter} facts across {len(sessions)} sessions.")


if __name__ == "__main__":
    ensure_root()

    with open("LongMemEval/data/longmemeval_oracle.json") as f:
        data = json.load(f)

    load_question_into_graph(data[0])
