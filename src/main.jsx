import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Bell,
  Brain,
  Check,
  ChevronDown,
  Clock3,
  Copy,
  Database,
  FileText,
  History,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Mic,
  Network,
  Pin,
  Plus,
  Search,
  Send,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";

import "./styles.css";

const API = "";
const LS = "eidetix_user";

const examples = [
  "What am I using now?",
  "How did my project change?",
  "What do you remember about me?",
  "What is my favorite movie?",
];

function App() {
  const [user, setUser] = useState(() =>
    JSON.parse(localStorage.getItem(LS) || "null")
  );

  const [auth, setAuth] = useState("login");

  if (!user) {
    return (
      <Auth
        mode={auth}
        setMode={setAuth}
        onLogin={(u) => {
          localStorage.setItem(LS, JSON.stringify(u));
          setUser(u);
        }}
      />
    );
  }

  return (
    <Workspace
      user={user}
      logout={() => {
        localStorage.removeItem(LS);
        setUser(null);
      }}
    />
  );
}

/* =========================================================
   AUTH
========================================================= */

function Auth({ mode, setMode, onLogin }) {
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    password: "",
  });

  const [msg, setMsg] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setMsg("");

    try {
      if (mode === "signup") {
        const r = await fetch(`${API}/api/signup`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(form),
        });

        const d = await r.json();

        if (!r.ok) {
          setMsg(d.error || "Unable to create account.");
          return;
        }

        setMsg("Account created successfully. Please log in.");
        setMode("login");
        return;
      }

      if (mode === "forgot") {
        const r = await fetch(`${API}/api/forgot`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email: form.email,
          }),
        });

        const d = await r.json();

        setMsg(
          d.message ||
            "If the email exists, recovery instructions will be provided."
        );

        return;
      }

      const r = await fetch(`${API}/api/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: form.email,
          password: form.password,
        }),
      });

      const d = await r.json();

      if (!r.ok) {
        setMsg(d.error || "Invalid email or password.");
        return;
      }

      onLogin(d.user);
    } catch (error) {
      setMsg(
        "Unable to connect to the Eidetix server. Make sure npm run dev is running."
      );
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-left">
        <div className="auth-brand">
          <div className="logo">
            <Brain />
          </div>

          <span>Eidetix</span>
        </div>

        <div className="auth-copy">
          <div className="eyebrow">
            <Sparkles size={14} />
            Personal AI memory
          </div>

          <h1>Remember what was true.</h1>

          <p>
            Eidetix turns your conversations into a private, searchable memory
            that understands time, change, evidence and uncertainty.
          </p>

          <div className="auth-points">
            <span>
              <ShieldCheck />
              Evidence-first
            </span>

            <span>
              <History />
              Temporal memory
            </span>

            <span>
              <Network />
              Graph-ready
            </span>
          </div>
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-card-head">
          <div className="mini-logo">
            <Brain size={18} />
          </div>

          <div>
            <h2>
              {mode === "signup"
                ? "Create your account"
                : mode === "forgot"
                ? "Reset your password"
                : "Welcome back"}
            </h2>

            <p>
              {mode === "signup"
                ? "Create an Eidetix workspace."
                : mode === "forgot"
                ? "Enter your email to start recovery."
                : "Sign in to continue to your memory."}
            </p>
          </div>
        </div>

        <form onSubmit={submit}>
          {mode === "signup" && (
            <Input
              label="Full name"
              value={form.name}
              onChange={(v) => setForm({ ...form, name: v })}
              placeholder="Your name"
            />
          )}

          <Input
            label="Email"
            value={form.email}
            onChange={(v) => setForm({ ...form, email: v })}
            placeholder="you@example.com"
            type="email"
          />

          {mode === "signup" && (
            <Input
              label="Phone number"
              value={form.phone}
              onChange={(v) => setForm({ ...form, phone: v })}
              placeholder="+91 98765 43210"
              type="tel"
            />
          )}

          {mode !== "forgot" && (
            <Input
              label="Password"
              value={form.password}
              onChange={(v) => setForm({ ...form, password: v })}
              placeholder="••••••••"
              type="password"
            />
          )}

          {msg && <div className="auth-msg">{msg}</div>}

          <button className="primary wide">
            {mode === "signup"
              ? "Create account"
              : mode === "forgot"
              ? "Send recovery instructions"
              : "Log in"}

            <ArrowRight size={16} />
          </button>
        </form>

        <div className="auth-switch">
          {mode === "login" ? (
            <>
              <span>New to Eidetix?</span>

              <button onClick={() => setMode("signup")}>
                Create account
              </button>

              <button
                className="link-muted"
                onClick={() => setMode("forgot")}
              >
                Forgot password?
              </button>
            </>
          ) : (
            <button onClick={() => setMode("login")}>
              <ArrowLeft size={14} />
              Back to login
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}) {
  return (
    <label className="field">
      <span>{label}</span>

      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        type={type}
        required={label !== "Phone number"}
      />
    </label>
  );
}

/* =========================================================
   WORKSPACE
========================================================= */

function Workspace({ user, logout }) {
  const [page, setPage] = useState("dashboard");
  const [convos, setConvos] = useState([]);
  const [memories, setMemories] = useState([]);
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState("");

  const refresh = async () => {
    try {
      const [conversationResponse, memoryResponse] = await Promise.all([
        fetch(`${API}/api/conversations?userId=${user.id}`),
        fetch(`${API}/api/memories?userId=${user.id}`),
      ]);

      const conversations = await conversationResponse.json();
      const memoryData = await memoryResponse.json();

      setConvos(conversations);
      setMemories(memoryData);

      if (!selected && conversations[0]) {
        setSelected(conversations[0]);
      }
    } catch (error) {
      console.error("Unable to refresh workspace:", error);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const notify = (message) => {
    setToast(message);

    setTimeout(() => {
      setToast("");
    }, 2400);
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div
          className="brand"
          onClick={() => setPage("dashboard")}
        >
          <div className="logo small">
            <Brain size={19} />
          </div>

          <div>
            <b>Eidetix</b>
            <span>Personal AI memory</span>
          </div>
        </div>

        <div className="account-card">
          <div className="avatar">
            {user.name.slice(0, 1).toUpperCase()}
          </div>

          <div>
            <b>{user.name}</b>
            <span>{user.email}</span>
          </div>

          <ChevronDown size={14} />
        </div>

        <div className="side-section">
          <span className="side-label">Workspace</span>

          <Nav
            icon={<LayoutDashboard />}
            label="Overview"
            active={page === "dashboard"}
            onClick={() => setPage("dashboard")}
          />

          <Nav
            icon={<Upload />}
            label="Ingest conversations"
            active={page === "ingest"}
            onClick={() => setPage("ingest")}
            hot
          />

          <Nav
            icon={<MessageCircle />}
            label="Ask Memory"
            active={page === "ask"}
            onClick={() => setPage("ask")}
          />

          <Nav
            icon={<Network />}
            label="Memory Graph"
            active={page === "graph"}
            onClick={() => setPage("graph")}
          />

          <Nav
            icon={<Clock3 />}
            label="Timeline"
            active={page === "timeline"}
            onClick={() => setPage("timeline")}
          />

          <Nav
            icon={<Activity />}
            label="Benchmark"
            active={page === "benchmark"}
            onClick={() => setPage("benchmark")}
          />
        </div>

        <div className="side-bottom">
          <Nav
            icon={<SettingsIcon />}
            label="Account & settings"
            active={page === "settings"}
            onClick={() => setPage("settings")}
          />

          <button
            className="nav-item"
            onClick={logout}
          >
            <LogOut />
            Sign out
          </button>

          <HydraStatus />
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="crumb">
            Eidetix <span>/</span> {title(page)}
          </div>

          <div className="top-user">
            <Bell size={17} />

            <div className="avatar tiny">
              {user.name.slice(0, 1)}
            </div>

            <b>{user.name}</b>
          </div>
        </header>

        <div className="content">
          {page === "dashboard" && (
            <Dashboard
              user={user}
              convos={convos}
              memories={memories}
              setPage={setPage}
            />
          )}

          {page === "ingest" && (
            <Ingest
              user={user}
              onDone={refresh}
              notify={notify}
            />
          )}

          {page === "ask" && (
            <Ask
              user={user}
              memories={memories}
              convos={convos}
              setPage={setPage}
            />
          )}

          {page === "graph" && (
            <Graph memories={memories} />
          )}

          {page === "timeline" && (
            <Timeline memories={memories} />
          )}

          {page === "benchmark" && (
            <Benchmark />
          )}

          {page === "settings" && (
            <AccountSettings
              user={user}
              notify={notify}
            />
          )}
        </div>
      </main>

      {toast && (
        <div className="toast">
          <Check size={16} />
          {toast}
        </div>
      )}
    </div>
  );
}

function title(page) {
  return {
    dashboard: "Overview",
    ingest: "Ingest conversations",
    ask: "Ask Memory",
    graph: "Memory Graph",
    timeline: "Timeline",
    benchmark: "Benchmark",
    settings: "Account & settings",
  }[page];
}

function Nav({
  icon,
  label,
  active,
  onClick,
  hot,
}) {
  return (
    <button
      className={`nav-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      {React.cloneElement(icon, { size: 18 })}

      <span>{label}</span>

      {hot && <em>MAIN</em>}
    </button>
  );
}

function HydraStatus() {
  const [ok, setOk] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/hydradb/status`)
      .then((r) => r.json())
      .then((d) => setOk(!!d.connected))
      .catch(() => setOk(false));
  }, []);

  return (
    <div className="hydra">
      <span className={ok ? "online" : "offline"} />

      <div>
        <b>HydraDB</b>
        <span>
          {ok ? "Connected" : "Not connected"}
        </span>
      </div>
    </div>
  );
}

/* =========================================================
   DASHBOARD
========================================================= */

function Dashboard({
  user,
  convos,
  memories,
  setPage,
}) {
  return (
    <>
      <div className="hero">
        <div>
          <div className="eyebrow">
            <Sparkles size={14} />
            Your memory workspace
          </div>

          <h1>
            Hi {user.name.split(" ")[0]}, what should Eidetix remember?
          </h1>

          <p>
            Ingest your past AI conversations, then ask questions across
            everything you've shared.
          </p>
        </div>

        <button
          className="primary"
          onClick={() => setPage("ingest")}
        >
          <Upload size={17} />
          Ingest conversations
        </button>
      </div>

      <div className="stats">
        <Stat label="Conversations" value={convos.length} />
        <Stat label="Memories" value={memories.length} />

        <Stat
          label="Current facts"
          value={memories.filter((m) => m.status === "current").length}
        />

        <Stat
          label="Sources"
          value={new Set(convos.map((c) => c.provider)).size}
        />
      </div>

      <div className="dashboard-grid">
        <section className="card main-card">
          <div className="card-head">
            <div>
              <h2>Recent conversations</h2>
              <p>
                Your imported AI history, grouped by source.
              </p>
            </div>

            <button
              className="link"
              onClick={() => setPage("ingest")}
            >
              Add more
              <ArrowRight size={14} />
            </button>
          </div>

          {convos.length ? (
            <ConversationList
              convos={convos}
              setPage={setPage}
            />
          ) : (
            <EmptyIngest setPage={setPage} />
          )}
        </section>

        <section className="card">
          <div className="card-head">
            <div>
              <h2>Quick ask</h2>
              <p>Query your imported memory.</p>
            </div>
          </div>

          <QuickAsk setPage={setPage} />

          <div className="mini-flow">
            <Flow
              n="01"
              t="Ingest"
              s="Conversations"
            />

            <Flow
              n="02"
              t="Remember"
              s="Facts + time"
            />

            <Flow
              n="03"
              t="Answer"
              s="Evidence / abstain"
            />
          </div>
        </section>
      </div>
    </>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function Flow({ n, t, s }) {
  return (
    <div>
      <small>{n}</small>
      <b>{t}</b>
      <span>{s}</span>
    </div>
  );
}

function EmptyIngest({ setPage }) {
  return (
    <div className="empty">
      <Upload size={25} />

      <h3>No conversations yet</h3>

      <p>
        Import a Qwen, ChatGPT, Claude, Gemini or other AI
        conversation to start building your memory.
      </p>

      <button
        className="primary"
        onClick={() => setPage("ingest")}
      >
        Import your first chat
      </button>
    </div>
  );
}

function ConversationList({
  convos,
  setPage,
}) {
  return (
    <div className="conv-list">
      {convos.slice(0, 8).map((c) => (
        <button
          className="conv-row"
          key={c.id}
          onClick={() => setPage("ask")}
        >
          <div className="provider-logo">
            {c.provider.slice(0, 1)}
          </div>

          <div className="conv-copy">
            <b>{c.title}</b>

            <span>
              {c.provider} •{" "}
              {new Date(c.updatedAt).toLocaleString()}
            </span>
          </div>

          {c.pinned && (
            <Pin
              size={14}
              fill="currentColor"
            />
          )}

          <ChevronDown size={15} />
        </button>
      ))}
    </div>
  );
}

function QuickAsk({ setPage }) {
  return (
    <div className="quick">
      <button onClick={() => setPage("ask")}>
        What am I using now?
      </button>

      <button onClick={() => setPage("ask")}>
        How did my project change?
      </button>

      <button onClick={() => setPage("ask")}>
        What do you remember about me?
      </button>
    </div>
  );
}

/* =========================================================
   INGEST
========================================================= */

function Ingest({
  user,
  onDone,
  notify,
}) {
  const [tab, setTab] = useState("url");

  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [provider, setProvider] = useState("Auto-detect");
  const [titleValue, setTitleValue] = useState("");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();

    setLoading(true);

    try {
      let body = {
        userId: user.id,
        url,
        text,
        provider:
          provider === "Auto-detect"
            ? ""
            : provider,
        title: titleValue,
      };

      const r = await fetch(`${API}/api/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      const d = await r.json();

      if (!r.ok) {
        throw new Error(
          d.error || "Unable to ingest conversation."
        );
      }

      setResult(d);

      onDone();

      notify("Conversation ingested successfully.");

      setText("");
      setUrl("");
      setTitleValue("");
    } catch (err) {
      notify(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <Upload size={14} />
            Main feature
          </div>

          <h1>Ingest conversations</h1>

          <p>
            Bring your AI history into Eidetix. We identify the
            source, preserve the conversation, and turn useful
            statements into memory.
          </p>
        </div>
      </div>

      <div className="ingest-grid">
        <section className="card ingest-card">
          <div className="source-tabs">
            <button
              className={tab === "url" ? "active" : ""}
              onClick={() => setTab("url")}
            >
              <Network size={16} />
              Public AI URL
            </button>

            <button
              className={tab === "paste" ? "active" : ""}
              onClick={() => setTab("paste")}
            >
              <Copy size={16} />
              Paste conversation
            </button>
          </div>

          <form onSubmit={submit}>
            {tab === "url" ? (
              <>
                <label className="field">
                  <span>Conversation URL</span>

                  <input
                    value={url}
                    onChange={(e) =>
                      setUrl(e.target.value)
                    }
                    placeholder="Paste a public Qwen / ChatGPT / Claude / Gemini link"
                    required
                  />
                </label>

                <div className="url-note">
                  <ShieldCheck size={16} />

                  <div>
                    <b>Public links only</b>

                    <span>
                      Private/login-only pages may need a
                      dedicated provider connector.
                    </span>
                  </div>
                </div>

                <label className="field">
                  <span>Provider</span>

                  <select
                    value={provider}
                    onChange={(e) =>
                      setProvider(e.target.value)
                    }
                  >
                    <option>Auto-detect</option>
                    <option>Qwen</option>
                    <option>ChatGPT</option>
                    <option>Claude</option>
                    <option>Gemini</option>
                    <option>Copilot</option>
                    <option>Other</option>
                  </select>
                </label>
              </>
            ) : (
              <>
                <label className="field">
                  <span>Conversation</span>

                  <textarea
                    value={text}
                    onChange={(e) =>
                      setText(e.target.value)
                    }
                    placeholder={`User: I started with React...
AI: What changed?
User: I switched to Vue...
AI: And now?
User: I moved back to React.`}
                    required
                  />
                </label>

                <div className="paste-tip">
                  <FileText size={16} />

                  <span>
                    Tip: use <b>User:</b> and <b>AI:</b>{" "}
                    prefixes for the most accurate message
                    separation.
                  </span>
                </div>

                <div className="two-fields">
                  <label className="field">
                    <span>Provider</span>

                    <select
                      value={provider}
                      onChange={(e) =>
                        setProvider(e.target.value)
                      }
                    >
                      <option>Auto-detect</option>
                      <option>Qwen</option>
                      <option>ChatGPT</option>
                      <option>Claude</option>
                      <option>Gemini</option>
                      <option>Copilot</option>
                      <option>Other</option>
                    </select>
                  </label>

                  <label className="field">
                    <span>
                      Conversation name (optional)
                    </span>

                    <input
                      value={titleValue}
                      onChange={(e) =>
                        setTitleValue(e.target.value)
                      }
                      placeholder="e.g. AI Memory Hackathon"
                    />
                  </label>
                </div>
              </>
            )}

            <button
              className="primary wide"
              disabled={loading}
            >
              {loading ? (
                <Activity className="spin" />
              ) : (
                <Upload size={16} />
              )}

              {loading
                ? "Processing..."
                : "Ingest conversation"}
            </button>
          </form>

          {result && (
            <div className="result">
              <Check size={18} />

              <div>
                <b>
                  {result.conversation.provider} imported
                </b>

                <span>
                  {result.conversation.title} •{" "}
                  {result.memories.length} memories extracted
                </span>
              </div>
            </div>
          )}
        </section>

        <section className="card side-explain">
          <div className="explain-icon">
            <Brain />
          </div>

          <h2>What Eidetix does</h2>

          <Step
            n="01"
            title="Identify source"
            text="Qwen, ChatGPT, Claude, Gemini or generic AI."
          />

          <Step
            n="02"
            title="Preserve history"
            text="The full conversation stays attached to your account."
          />

          <Step
            n="03"
            title="Extract memory"
            text="Facts and preferences become searchable memory."
          />

          <Step
            n="04"
            title="Track change"
            text="Later conflicting facts can supersede earlier ones."
          />

          <Step
            n="05"
            title="Answer safely"
            text="Ask Memory uses evidence and can abstain."
          />
        </section>
      </div>
    </div>
  );
}

function Step({
  n,
  title,
  text,
}) {
  return (
    <div className="step">
      <span>{n}</span>

      <div>
        <b>{title}</b>
        <p>{text}</p>
      </div>
    </div>
  );
}

/* =========================================================
   ASK MEMORY / AI CHAT
========================================================= */

function Ask({
  user,
  memories,
  convos,
  setPage,
}) {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState(null);
  const [messages, setMessages] = useState([]);
  const [voice, setVoice] = useState(false);
  const [current, setCurrent] = useState(null);
  const [recentSearches, setRecentSearches] = useState(() =>
    JSON.parse(
      localStorage.getItem(`eidetix_recent_searches_${user.id}`) || "[]"
    )
  );
  const [chatSearch, setChatSearch] = useState("");

  const recognition = useRef(null);

  const ask = async (q) => {
    q = (q ?? query).trim();

    if (!q) return;

    setQuery("");

    setRecentSearches((items) => {
      const next = [
        q,
        ...items.filter((item) => item !== q),
      ].slice(0, 8);

      localStorage.setItem(
        `eidetix_recent_searches_${user.id}`,
        JSON.stringify(next)
      );

      return next;
    });

    setMessages((m) => [
      ...m,
      {
        role: "user",
        content: q,
      },
    ]);

    try {
      const r = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          userId: user.id,
          conversationId: current?.id || null,
          text: q,
        }),
      });

      const d = await r.json();

      if (!r.ok) {
        throw new Error(
          d.error || "Unable to contact Eidetix."
        );
      }

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: d.reply,
        },
      ]);

      setAnswer({
        reply: d.reply,
        evidence: d.evidence || [],
        abstain: !!d.abstained,
        confidence: Number(d.confidence || 0),
      });
    } catch (error) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content:
            "I couldn't reach the Eidetix memory service. Make sure the API server is running.",
        },
      ]);
    }
  };

  const findEvidence = (q, ms) => {
    const lower = q.toLowerCase();

    return ms
      .filter((m) => {
        if (
          lower.includes("use") ||
          lower.includes("using")
        ) {
          return m.predicate === "uses";
        }

        if (lower.includes("favorite")) {
          return m.predicate === "favorite";
        }

        return true;
      })
      .slice(0, 4);
  };

  const loadConversation = async (conversation) => {
    setCurrent(conversation);
    setAnswer(null);

    try {
      const r = await fetch(
        `${API}/api/messages?userId=${user.id}&conversationId=${conversation.id}`
      );
      const data = await r.json();

      if (!r.ok) {
        throw new Error("Unable to load conversation.");
      }

      setMessages(
        data.map((message) => ({
          role: message.role,
          content: message.content,
        }))
      );
    } catch (error) {
      setMessages([]);
    }
  };

  const togglePin = async (conversation, event) => {
    event.stopPropagation();

    try {
      const r = await fetch(
        `${API}/api/conversations/${conversation.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            userId: user.id,
            pinned: !conversation.pinned,
          }),
        }
      );

      if (!r.ok) {
        throw new Error("Unable to update pin.");
      }

      conversation.pinned = !conversation.pinned;
      setCurrent({ ...conversation });
      window.location.reload();
    } catch {
      // Keep the chat usable even if pinning fails.
    }
  };

  const startVoice = () => {
    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert(
        "Voice input is not supported in this browser. Try Chrome or Edge."
      );

      return;
    }

    const r = new SpeechRecognition();

    r.lang = "en-US";
    r.interimResults = true;
    r.continuous = false;

    r.onstart = () => {
      setVoice(true);
    };

    r.onend = () => {
      setVoice(false);
    };

    r.onerror = () => {
      setVoice(false);
    };

    r.onresult = (e) => {
      let text = "";

      for (const result of e.results) {
        text += result[0].transcript;
      }

      setQuery(text);
    };

    recognition.current = r;

    r.start();
  };

  const newChat = () => {
    setCurrent({
      id: null,
      title: "New conversation",
      provider: "Eidetix",
    });

    setMessages([]);
    setAnswer(null);
  };

  return (
    <div className="ask-page">
      <div className="chat-sidebar">
        <button
          className="new-chat"
          onClick={newChat}
        >
          <Plus size={16} />
          New conversation
        </button>

        <div className="chat-search">
          <Search size={14} />

          <input value={chatSearch} onChange={(e) => setChatSearch(e.target.value)} placeholder="Search chats" />
        </div>

        <span className="chat-label">
          Recent
        </span>

        {convos
          .filter((c) =>
            c.title
              .toLowerCase()
              .includes(chatSearch.toLowerCase())
          )
          .slice(0, 8)
          .map((c) => (
            <div
              className={`chat-item ${
                current?.id === c.id
                  ? "selected"
                  : ""
              }`}
              key={c.id}
              onClick={() => loadConversation(c)}
            >
              <div className="provider-mini">
                {c.provider[0]}
              </div>

              <span>{c.title}</span>

              <button
                className="chat-pin"
                title={c.pinned ? "Unpin" : "Pin"}
                onClick={(event) =>
                  togglePin(c, event)
                }
              >
                <Pin
                  size={12}
                  fill={c.pinned ? "currentColor" : "none"}
                />
              </button>
            </div>
          ))}

        <span className="chat-label">
          Pinned
        </span>

        {convos
          .filter((c) => c.pinned)
          .map((c) => (
            <button
              className="chat-item"
              key={`pinned-${c.id}`}
              onClick={() => loadConversation(c)}
            >
              <Pin size={13} />

              <span>{c.title}</span>
            </button>
          ))}

        {!convos.filter((c) => c.pinned).length && (
          <div className="no-pins">
            No pinned conversations
          </div>
        )}

        {recentSearches.length > 0 && (
          <>
            <span className="chat-label">
              Recent searches
            </span>

            {recentSearches.slice(0, 5).map((search) => (
              <button
                className="chat-item"
                key={search}
                onClick={() => {
                  setQuery(search);
                  ask(search);
                }}
              >
                <Search size={13} />
                <span>{search}</span>
              </button>
            ))}
          </>
        )}
      </div>

      <section className="chat-main">
        <div className="chat-header">
          <div>
            <div className="eyebrow">
              <Brain size={13} />
              Eidetix AI
            </div>

            <h1>
              {current?.title ||
                "New conversation"}
            </h1>
          </div>

          <div className="chat-head-actions">
            <button
              title="Voice input"
              className={
                voice ? "active-icon" : ""
              }
              onClick={startVoice}
            >
              <Mic size={17} />
            </button>

            <button
              onClick={() =>
                setPage("settings")
              }
            >
              <SettingsIcon size={17} />
            </button>
          </div>
        </div>

        <div className="chat-messages">
          {messages.length ? (
            messages.map((m, i) => (
              <div
                className={`bubble-row ${m.role}`}
                key={i}
              >
                <div className="bubble-avatar">
                  {m.role === "assistant" ? (
                    <Brain size={15} />
                  ) : (
                    user.name[0]
                  )}
                </div>

                <div className="bubble">
                  <p>{m.content}</p>

                  {m.role === "assistant" &&
                    answer &&
                    i === messages.length - 1 && (
                      <div className="answer-meta">
                        {answer.abstain ? (
                          <span className="red">
                            <ShieldCheck size={13} />
                            Abstained
                          </span>
                        ) : (
                          <span className="green">
                            <Check size={13} />
                            Evidence checked
                          </span>
                        )}

                        {answer.evidence.length > 0 && (
                          <button
                            onClick={() =>
                              setPage("timeline")
                            }
                          >
                            View evidence
                            <ArrowRight size={12} />
                          </button>
                        )}

                        {answer.confidence > 0 && (
                          <span>
                            Confidence: {Math.round(answer.confidence * 100)}%
                          </span>
                        )}
                      </div>
                    )}
                </div>
              </div>
            ))
          ) : (
            <div className="chat-empty">
              <div className="big-ai">
                <Brain size={30} />
              </div>

              <h2>
                What do you want to remember?
              </h2>

              <p>
                Ask about your imported conversations.
                Eidetix searches your memory and uses
                chronology before it answers.
              </p>

              <div className="example-grid">
                {examples.map((example) => (
                  <button
                    key={example}
                    onClick={() => ask(example)}
                  >
                    {example}
                    <ArrowRight size={13} />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="composer">
          <button
            className={voice ? "mic-on" : ""}
            onClick={startVoice}
            title="Voice input"
          >
            <Mic size={18} />
          </button>

          <textarea
            value={query}
            onChange={(e) =>
              setQuery(e.target.value)
            }
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey
              ) {
                e.preventDefault();
                ask();
              }
            }}
            placeholder="Message Eidetix..."
          />

          <button
            className="send"
            onClick={() => ask()}
          >
            <Send size={17} />
          </button>

          <small>
            {voice
              ? "Listening..."
              : "Press Enter to send • Shift+Enter for new line"}
          </small>
        </div>
      </section>
    </div>
  );
}

/* =========================================================
   GRAPH
========================================================= */

function Graph({ memories }) {
  const current = memories
    .filter((m) => m.status === "current")
    .slice(0, 8);

  return (
    <Page
      title="Memory Graph"
      icon={<Network />}
      sub="A live view of the memories currently stored for your account."
    >
      <section className="card graph-live">
        <div className="graph-center">
          <Brain size={23} />
          <b>You</b>
        </div>

        {current.map((m, i) => (
          <div
            key={m.id}
            className="memory-node"
            style={{
              "--i": i,
            }}
          >
            <span>{m.object}</span>
            <small>{m.predicate}</small>
          </div>
        ))}

        {!current.length && <EmptyGraph />}
      </section>
    </Page>
  );
}

function EmptyGraph() {
  return (
    <div className="graph-empty">
      Ingest a conversation to build your personal
      memory graph.
    </div>
  );
}

/* =========================================================
   TIMELINE
========================================================= */

function Timeline({ memories }) {
  return (
    <Page
      title="Timeline"
      icon={<Clock3 />}
      sub="Older memories remain available, while later facts can become the current truth."
    >
      <section className="card">
        <div className="timeline-list">
          {memories.map((m) => (
            <div
              className="timeline-row"
              key={m.id}
            >
              <div
                className={`timeline-dot ${m.status}`}
              />

              <div>
                <span>
                  {new Date(
                    m.createdAt
                  ).toLocaleString()}{" "}
                  • {m.status}
                </span>

                <h3>
                  {m.predicate}: {m.object}
                </h3>

                <p>
                  Source: {m.provider}
                </p>
              </div>
            </div>
          ))}

          {!memories.length && (
            <EmptyGraph />
          )}
        </div>
      </section>
    </Page>
  );
}

/* =========================================================
   BENCHMARK
========================================================= */

function Benchmark() {
  return (
    <Page
      title="Benchmark"
      icon={<Activity />}
      sub="Evaluation surface for long-context retrieval, chronology and abstention."
    >
      <div className="stats">
        <Stat
          label="Answer accuracy"
          value="—"
        />

        <Stat
          label="Temporal accuracy"
          value="—"
        />

        <Stat
          label="Abstention accuracy"
          value="—"
        />

        <Stat
          label="Evidence precision"
          value="—"
        />
      </div>

      <section className="card benchmark-note">
        <ShieldCheck size={20} />

        <div>
          <b>No fake benchmark scores.</b>

          <p>
            Connect the official challenge dataset
            and runner here. Eidetix intentionally
            leaves metrics blank until a real
            evaluation has been executed.
          </p>
        </div>
      </section>
    </Page>
  );
}

/* =========================================================
   GENERIC PAGE
========================================================= */

function Page({
  title,
  icon,
  sub,
  children,
}) {
  return (
    <div className="page">
      <div className="page-head">
        <div className="eyebrow">
          {React.cloneElement(icon, {
            size: 14,
          })}
          Eidetix
        </div>

        <h1>{title}</h1>

        <p>{sub}</p>
      </div>

      {children}
    </div>
  );
}

/* =========================================================
   ACCOUNT SETTINGS
========================================================= */

function AccountSettings({
  user,
  notify,
}) {
  const [privacy, setPrivacy] =
    useState(true);

  const [notifyOn, setNotifyOn] =
    useState(true);

  return (
    <Page
      title="Account & settings"
      icon={<SettingsIcon />}
      sub="Your account lives here, along with privacy and memory controls."
    >
      <div className="settings-grid">
        <section className="card profile-card">
          <div className="profile-large">
            {user.name[0]}
          </div>

          <h2>{user.name}</h2>

          <p>{user.email}</p>

          {user.phone && (
            <p>{user.phone}</p>
          )}

          <button className="secondary">
            Edit profile
          </button>
        </section>

        <section className="card">
          <Setting
            title="Private workspace"
            desc="Keep memories scoped to your account."
            value={privacy}
            setValue={setPrivacy}
          />

          <Setting
            title="Memory notifications"
            desc="Show reminders when memory processing finishes."
            value={notifyOn}
            setValue={setNotifyOn}
          />

          <div className="setting-line">
            <Database size={17} />

            <div>
              <b>HydraDB</b>

              <span>
                Not connected — no server is
                configured yet.
              </span>
            </div>
          </div>

          <button
            className="primary"
            onClick={() =>
              notify("Settings saved.")
            }
          >
            Save settings
          </button>
        </section>
      </div>
    </Page>
  );
}

function Setting({
  title,
  desc,
  value,
  setValue,
}) {
  return (
    <div className="setting">
      <div>
        <b>{title}</b>
        <span>{desc}</span>
      </div>

      <button
        className={`toggle ${
          value ? "on" : ""
        }`}
        onClick={() =>
          setValue(!value)
        }
      >
        <i />
      </button>
    </div>
  );
}

/* =========================================================
   START APP
========================================================= */

createRoot(
  document.getElementById("root")
).render(<App />);