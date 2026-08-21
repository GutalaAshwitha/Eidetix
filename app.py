import streamlit as st
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory.pipeline import MemoryPipeline
from memory.storage import StorageManager, extract_row_val

# --- Page Config ---
st.set_page_config(
    page_title="Eidetix - Agent Memory",
    page_icon="🧠",
    layout="wide",
)

# --- CSS ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #888;
        margin-top: -10px;
        margin-bottom: 30px;
    }
</style>
""", unsafe_allow_html=True)


# --- Initialize Pipeline (cached) ---
@st.cache_resource
def get_pipeline():
    return MemoryPipeline()


pipeline = get_pipeline()

# --- Header ---
st.markdown('<div class="main-header">🧠 Eidetix</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Agent Memory & Context Retrieval Layer — powered by HydraDB</div>', unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.header("📋 Navigation")
    page = st.radio(
        "Go to",
        ["💬 Ask a Question", "📥 Ingest Sessions", "🗃️ Memory Browser", "📊 System Status"],
        label_visibility="collapsed",
    )

# =============================================================
# PAGE: Ask a Question
# =============================================================
if page == "💬 Ask a Question":
    st.header("💬 Ask a Question")
    st.write("Ask anything about the user's history. The system retrieves evidence from HydraDB and answers — or abstains if the information isn't available.")

    question = st.text_input(
        "Your question:",
        placeholder="e.g., What car does the user currently own?",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        ask_btn = st.button("🔍 Ask", type="primary", use_container_width=True)

    if ask_btn and question:
        with st.spinner("Retrieving from HydraDB..."):
            result = pipeline.answer_question(question)

        st.divider()

        if result["should_abstain"]:
            st.warning("🚫 **" + result["answer"] + "**")
        else:
            st.success("✅ **Answer:** " + result["answer"])

        # Show evidence
        if result["retrieved_facts"]:
            st.subheader("📄 Supporting Evidence")
            for f in result["retrieved_facts"]:
                sup_label = "🔴 SUPERSEDED" if f.get("is_superseded") else "🟢 ACTIVE"
                with st.expander(sup_label + " — " + f.get("text", "N/A"), expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Subject", f.get("subject", "—"))
                    c2.metric("Predicate", f.get("predicate", "—"))
                    c3.metric("Object", f.get("object", "—"))
                    st.caption("Session: `" + str(f.get("session_id", "—")) + "` | Timestamp: `" + str(f.get("timestamp", "—")) + "`")
        else:
            st.info("No facts were retrieved for this query.")

    # Quick examples
    st.divider()
    st.subheader("💡 Try these example questions")
    ex_cols = st.columns(3)
    examples = [
        "What car does the user currently own?",
        "What car did the user previously own?",
        "What is the user's favorite football team?",
    ]
    for i, ex in enumerate(examples):
        with ex_cols[i]:
            st.code(ex, language=None)


# =============================================================
# PAGE: Ingest Sessions
# =============================================================
elif page == "📥 Ingest Sessions":
    st.header("📥 Ingest Chat Sessions")

    tab1, tab2 = st.tabs(["✍️ Manual Entry", "📁 Upload JSON"])

    with tab1:
        st.subheader("Add a session manually")

        session_id = st.text_input("Session ID", value="session_" + str(int(time.time())))
        date_str = st.text_input("Date", value="2024/01/01 10:00")
        timestamp = st.number_input("Timestamp (epoch)", value=int(time.time()), step=1)

        st.write("**Chat messages** (one per line, format: `role: message`)")
        messages_text = st.text_area(
            "Messages",
            value="user: I bought a Honda car today!",
            height=150,
        )

        if st.button("🚀 Ingest Session", type="primary"):
            turns = []
            for line in messages_text.strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    role, content = line.split(":", 1)
                    turns.append({"role": role.strip().lower(), "content": content.strip()})

            if turns:
                with st.spinner("Ingesting into HydraDB..."):
                    pipeline.ingest_session(session_id, turns, date_str, int(timestamp))
                st.success("✅ Session `" + session_id + "` ingested with " + str(len(turns)) + " message(s)!")
            else:
                st.error("No valid messages found. Use format: `user: message text`")

    with tab2:
        st.subheader("Upload a JSON file with sessions")
        st.write("Expected format:")
        st.code("""[
  {
    "session_id": "session-1",
    "date_str": "2024/01/10 10:00",
    "timestamp": 1704880800,
    "messages": [
      {"role": "user", "content": "I bought a Honda car today!"},
      {"role": "assistant", "content": "Nice!"}
    ]
  }
]""", language="json")

        uploaded = st.file_uploader("Choose a JSON file", type=["json"])
        if uploaded and st.button("🚀 Ingest All Sessions", type="primary"):
            data = json.loads(uploaded.read())
            progress = st.progress(0)
            for i, sess in enumerate(data):
                pipeline.ingest_session(
                    sess["session_id"],
                    sess["messages"],
                    sess.get("date_str", "2024/01/01 00:00"),
                    sess.get("timestamp", int(time.time())),
                )
                progress.progress((i + 1) / len(data))
            st.success("✅ Ingested " + str(len(data)) + " sessions!")


# =============================================================
# PAGE: Memory Browser
# =============================================================
elif page == "🗃️ Memory Browser":
    st.header("🗃️ Memory Browser")
    st.write("All facts currently stored in the HydraDB graph.")

    if st.button("🔄 Refresh", type="primary"):
        st.cache_data.clear()

    facts = pipeline.retrieval.storage.get_all_facts()

    if not facts:
        st.info("No facts in the database yet. Go to **📥 Ingest Sessions** to add some!")
    else:
        # Stats
        active_facts = [f for f in facts if not f.get("is_superseded")]
        superseded_facts = [f for f in facts if f.get("is_superseded")]
        sessions = set(f.get("session_id", "") for f in facts)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Facts", len(facts))
        c2.metric("Active Facts", len(active_facts))
        c3.metric("Superseded", len(superseded_facts))
        c4.metric("Sessions", len(sessions))

        st.divider()

        # Filter
        show_filter = st.radio(
            "Show:", ["All", "Active Only", "Superseded Only"], horizontal=True
        )
        if show_filter == "Active Only":
            display_facts = active_facts
        elif show_filter == "Superseded Only":
            display_facts = superseded_facts
        else:
            display_facts = facts

        # Sort by timestamp
        display_facts = sorted(display_facts, key=lambda x: x.get("timestamp", 0), reverse=True)

        for f in display_facts:
            is_sup = f.get("is_superseded", False)
            icon = "🔴" if is_sup else "🟢"
            status = "SUPERSEDED" if is_sup else "ACTIVE"

            with st.container():
                col1, col2, col3, col4, col5 = st.columns([1, 3, 2, 2, 2])
                col1.write(icon)
                col2.write("**" + f.get("text", "—") + "**")
                col3.write("`" + f.get("predicate", "—") + "`")
                col4.write("`" + f.get("session_id", "—") + "`")
                col5.write("`" + status + "`")


# =============================================================
# PAGE: System Status
# =============================================================
elif page == "📊 System Status":
    st.header("📊 System Status")

    # HydraDB health check
    st.subheader("🔗 HydraDB Connection")
    try:
        import requests
        resp = requests.get("http://127.0.0.1:9090/readyz", timeout=3)
        if resp.status_code == 200:
            st.success("✅ HydraDB is **ONLINE** (port 8443/9090)")
        else:
            st.error("⚠️ HydraDB returned status " + str(resp.status_code))
    except Exception:
        st.error("❌ HydraDB is **OFFLINE** — run `bash scripts/start_hydradb.sh`")

    st.divider()

    # Graph stats
    st.subheader("📈 Graph Statistics")
    try:
        facts = pipeline.retrieval.storage.get_all_facts()
        active = [f for f in facts if not f.get("is_superseded")]
        superseded = [f for f in facts if f.get("is_superseded")]
        sessions = set(f.get("session_id", "") for f in facts)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Facts", len(facts))
        c2.metric("Active", len(active))
        c3.metric("Superseded", len(superseded))
        c4.metric("Sessions", len(sessions))
    except Exception as e:
        st.warning("Could not fetch graph stats: " + str(e))

    st.divider()

    # Architecture
    st.subheader("🏗️ Architecture")
    st.code("""
Chat Session -> Fact Extraction -> Normalization -> Supersession Detection
                                                         |
                                                    HydraDB Graph
                                                         |
Query -> Retrieval -> Temporal Reasoning -> Abstention Check -> Answer
    """)

    st.divider()

    # Environment
    st.subheader("⚙️ Environment")
    st.json({
        "HYDRA_URL": os.environ.get("HYDRA_URL", "http://127.0.0.1:8443/v1/graphs/default/query"),
        "GROQ_API_KEY": "***" if os.environ.get("GROQ_API_KEY") else "Not set",
        "OPENAI_API_KEY": "***" if os.environ.get("OPENAI_API_KEY") else "Not set",
    })
