import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";
import "./styles.css";

mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
let mermaidDiagramSequence = 0;

type ModelRef = { server_id: string; model_id: string };
type Server = {
  id: string;
  alias: string;
  base_url: string;
  enabled: boolean;
  verify_ssl: boolean;
  use_corporate_ca: boolean;
  follow_redirects: boolean;
  proxy_enabled: boolean;
  http_proxy?: string | null;
  https_proxy?: string | null;
  no_proxy?: string | null;
  proxy_username?: string | null;
  has_proxy_password: boolean;
  has_api_key: boolean;
};
type AppState = {
  model_servers: Server[];
  roles: { chat: ModelRef | null; embeddings: ModelRef | null };
  profile: Record<string, unknown> & { id: string };
  persona: { loaded: boolean; estimated_tokens: number; over_budget: boolean };
  avatar: { configured: boolean; revision: number };
  chat_message_count: number;
  knowledge: { ready: boolean; documents: number; chunks: number };
  paths: { workspace: string; knowledge: string; persona: string; avatar: string; corporate_ca: string; model_traffic_log: string };
  diagnostics: { model_traffic_logging: boolean };
};
type Evidence = {
  evidence_id: string;
  filename: string;
  relative_path: string;
  heading?: string | null;
  chunk_index: number;
  text: string;
  score: number;
  match_type: string;
};
type ChatMessage = { role: "user" | "assistant"; content: string; evidence?: Evidence[]; warnings?: string[]; startedAt?: number };
type ResultEnvelope = { request_id: string; type: "result"; ok: boolean; payload?: any; error?: string };
type ProgressEnvelope = { request_id: string; type: "progress"; payload: Record<string, any> };

class CommandSocket {
  private socket: WebSocket;
  private ready: Promise<void>;
  private pending = new Map<string, { resolve: (value: any) => void; reject: (error: Error) => void; progress?: (data: any) => void }>();

  constructor() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    this.socket = new WebSocket(`${protocol}://${location.host}/ws`);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener("open", () => resolve(), { once: true });
      this.socket.addEventListener("error", () => reject(new Error("Could not open the local command channel")), { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data)) as ResultEnvelope | ProgressEnvelope;
      const request = this.pending.get(message.request_id);
      if (!request) return;
      if (message.type === "progress") {
        if (typeof request.progress === "function") request.progress(message.payload);
        return;
      }
      this.pending.delete(message.request_id);
      if (message.ok) request.resolve(message.payload);
      else request.reject(new Error(message.error || "Command failed"));
    });
  }

  async send(action: string, payload: Record<string, unknown> = {}, progress?: (data: any) => void): Promise<any> {
    await this.ready;
    const request_id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      this.pending.set(request_id, { resolve, reject, progress });
      this.socket.send(JSON.stringify({ request_id, action, payload }));
    });
  }
}

const EMPTY_SERVER = {
  id: "",
  alias: "",
  base_url: "",
  api_key: "",
  enabled: true,
  verify_ssl: true,
  use_corporate_ca: false,
  follow_redirects: true,
  proxy_enabled: false,
  http_proxy: "",
  https_proxy: "",
  no_proxy: "",
  proxy_username: "",
  proxy_password: "",
};

function modelValue(ref: ModelRef | null): string {
  return ref ? `${ref.server_id}::${ref.model_id}` : "";
}

function parseModelValue(value: string): ModelRef | null {
  if (!value) return null;
  const separator = value.indexOf("::");
  return { server_id: value.slice(0, separator), model_id: value.slice(separator + 2) };
}

class AppErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <div className="center-card"><strong>VirtualMate could not render this view.</strong><p>Please reload the application and try again.</p><code>{this.state.error.message || "Unknown rendering error"}</code><button onClick={() => location.reload()}>Reload application</button></div>;
    }
    return this.props.children;
  }
}

function App() {
  const socket = useMemo(() => new CommandSocket(), []);
  const [state, setState] = useState<AppState | null>(null);
  const [view, setView] = useState<"chat" | "admin">("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [serverForm, setServerForm] = useState({ ...EMPTY_SERVER });
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [chatRole, setChatRole] = useState("");
  const [embeddingsRole, setEmbeddingsRole] = useState("");
  const [progress, setProgress] = useState<Record<string, any> | null>(null);
  const [chatProgress, setChatProgress] = useState<Record<string, any> | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  const transcriptEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/bootstrap")
      .then((response) => {
        if (!response.ok) throw new Error(`Bootstrap failed: HTTP ${response.status}`);
        return response.json();
      })
      .then((data: AppState) => {
        setState(data);
        setChatRole(modelValue(data.roles.chat));
        setEmbeddingsRole(modelValue(data.roles.embeddings));
      })
      .catch((reason) => setError(String(reason)));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("virtualmate-theme", theme); } catch { /* local storage may be disabled */ }
  }, [theme]);

  useEffect(() => {
    const target = transcriptEnd.current;
    if (target && typeof target.scrollIntoView === "function") target.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const availableModels = useMemo(() => {
    const values: { value: string; label: string }[] = [];
    for (const server of state?.model_servers || []) {
      const ids = [...(models[server.id] || [])];
      for (const current of [state?.roles.chat, state?.roles.embeddings]) {
        if (current?.server_id === server.id && !ids.includes(current.model_id)) ids.push(current.model_id);
      }
      for (const id of ids) values.push({ value: `${server.id}::${id}`, label: `${server.alias} — ${id}` });
    }
    return values;
  }, [state, models]);

  async function run(command: () => Promise<any>) {
    setError("");
    setBusy(true);
    try {
      return await command();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      throw reason;
    } finally {
      setBusy(false);
    }
  }

  async function sendQuestion(event: FormEvent) {
    event.preventDefault();
    const message = question.trim();
    if (!message || busy) return;
    const startedAt = performance.now();
    setQuestion("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    try {
      setChatProgress({ phase: "starting", message: "Preparing your question…" });
      const result = await run(() => socket.send("chat", { message }, setChatProgress));
      setMessages((current) => [...current, { role: "assistant", content: result.answer, evidence: result.evidence, warnings: result.warnings, startedAt }]);
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Unknown error";
      setMessages((current) => [...current, { role: "assistant", content: `I could not generate an answer: ${detail}`, startedAt }]);
    } finally {
      setChatProgress(null);
    }
  }

  async function clearChat() {
    await run(() => socket.send("clear_chat"));
    setMessages([]);
  }

  function exportConversation() {
    const renderedMessages = Array.from(document.querySelectorAll<HTMLElement>(".transcript .message"));
    if (renderedMessages.length === 0) return;
    const exportedAt = new Date();
    const darkExport = document.documentElement.dataset.theme === "dark";
    const exportColors = darkExport
      ? { background: "#151515", surface: "#202020", soft: "#292929", text: "#e8e8e8", muted: "#a8a8a8", border: "#3b3b3b", link: "#74c7ec" }
      : { background: "#ffffff", surface: "#ffffff", soft: "#f4f4f4", text: "#242424", muted: "#666666", border: "#dddddd", link: "#086a98" };
    const sections = renderedMessages.map((rendered) => {
      const clone = rendered.cloneNode(true) as HTMLElement;
      clone.querySelector(".avatar")?.remove();
      clone.querySelectorAll(".mermaid-toolbar").forEach((toolbar) => toolbar.remove());
      clone.querySelectorAll("details").forEach((details) => details.setAttribute("open", ""));
      clone.querySelectorAll<HTMLElement>(".evidence").forEach((evidence) => {
        const button = evidence.querySelector<HTMLButtonElement>(".evidence-back");
        const citation = evidence.id ? clone.querySelector<HTMLAnchorElement>(`.evidence-citation[href="#${evidence.id}"]`) : null;
        if (button && citation) {
          const back = document.createElement("a");
          back.className = "evidence-back";
          back.href = `#${citation.id}`;
          back.textContent = "Back to citation";
          button.replaceWith(back);
        } else {
          button?.remove();
        }
        evidence.removeAttribute("data-return-to");
      });
      const body = clone.querySelector<HTMLElement>(".message-body");
      const role = rendered.classList.contains("user") ? "User" : "VirtualMate";
      return `<section class="export-message ${rendered.classList.contains("user") ? "user" : "assistant"}"><h2>${role}</h2>${body?.innerHTML || ""}</section>`;
    }).join("\n");
    const documentHtml = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VirtualMate conversation</title><style>
*{box-sizing:border-box}:root{color-scheme:${darkExport ? "dark" : "light"};--bg:${exportColors.background};--surface:${exportColors.surface};--soft:${exportColors.soft};--text:${exportColors.text};--muted:${exportColors.muted};--border:${exportColors.border};--link:${exportColors.link}}body{margin:0;color:var(--text);background:var(--bg);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{width:min(900px,calc(100% - 32px));margin:40px auto 80px}.export-header{padding-bottom:22px;border-bottom:1px solid var(--border)}.export-header h1{margin:0 0 8px;font-size:28px}.meta{color:var(--muted);font-size:12px}.export-message{padding:25px 0;border-bottom:1px solid var(--border)}.export-message>h2{margin:0 0 14px;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.export-message.user .message-content{width:max-content;max-width:80%;margin-left:auto;padding:10px 16px;border-radius:18px;background:var(--soft);white-space:pre-wrap}.message-content{font-size:15px;line-height:1.7;overflow-wrap:anywhere}.markdown-body>:first-child{margin-top:0}.markdown-body>:last-child{margin-bottom:0}.markdown-body p{margin:0 0 14px}.markdown-body h1,.markdown-body h2,.markdown-body h3,.markdown-body h4{margin:24px 0 10px;line-height:1.3}.markdown-body h1{font-size:24px}.markdown-body h2{padding-bottom:6px;border-bottom:1px solid var(--border);font-size:20px}.markdown-body h3{font-size:17px}.markdown-body ul,.markdown-body ol{padding-left:25px}.markdown-body blockquote{margin:15px 0;padding:3px 16px;border-left:3px solid var(--muted);color:var(--muted)}.markdown-body a{color:var(--link)}.markdown-body .evidence-citation{padding:1px 5px;border:1px solid var(--link);border-radius:5px;background:var(--soft);font-size:.86em;font-weight:700;text-decoration:none}.markdown-body code{padding:2px 5px;border-radius:4px;color:${darkExport ? "#ffb4ab" : "#812b2b"};background:var(--soft);font:12px/1.5 Consolas,monospace}.markdown-body pre{padding:14px 16px;overflow:auto;border-radius:10px;color:#eee;background:#111}.markdown-body pre code{padding:0;color:inherit;background:transparent;white-space:pre}.markdown-body table{width:100%;display:block;overflow-x:auto;border-collapse:collapse}.markdown-body th,.markdown-body td{padding:8px 10px;border:1px solid var(--border);text-align:left}.markdown-body th{background:var(--soft)}.mermaid-diagram-shell{margin:16px 0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.mermaid-diagram{padding:18px;overflow:auto;text-align:center}.mermaid-diagram svg{width:auto;max-width:100%;height:auto}.response-metrics{width:max-content;margin-top:12px;padding:5px 8px;border-radius:7px;color:var(--muted);background:var(--soft);font-size:10px}.response-metrics svg{display:none}details{margin-top:14px}summary{cursor:pointer;font-size:12px;font-weight:600}.evidence-list{display:grid;gap:8px;margin-top:10px}.evidence{padding:13px 14px;border:1px solid var(--border);border-radius:10px;background:var(--soft)}.evidence>div{display:flex;justify-content:space-between;gap:12px}.evidence p{font-size:12px;line-height:1.5}.evidence span,.evidence small,.warning{color:var(--muted);font-size:10px}.evidence-footer{align-items:center}.evidence-back{color:var(--link);font-size:10px}.warning{display:block;margin-top:8px}footer{margin-top:28px;color:var(--muted);font-size:10px;text-align:center}@media print{main{width:100%;margin:0}.export-message{break-inside:avoid}.mermaid-diagram-shell{break-inside:avoid}}
</style></head><body><main><header class="export-header"><h1>Conversation with VirtualMate</h1><div class="meta">Exported ${escapeHtml(exportedAt.toLocaleString())} · ${renderedMessages.length} messages</div></header>${sections}<footer>Exported from VirtualMate · Developed by the VirtualMate team</footer></main></body></html>`;
    const blob = new Blob([documentHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `virtualmate-conversation-${exportedAt.toISOString().replace(/[:.]/g, "-")}.html`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function saveServer(event: FormEvent) {
    event.preventDefault();
    const server: Record<string, unknown> = { ...serverForm };
    if (!serverForm.api_key) delete server.api_key;
    const next = await run(() => socket.send("save_model_server", { server }));
    setState(next);
    setServerForm({ ...EMPTY_SERVER });
  }

  async function discover(server: Server) {
    const result = await run(() => socket.send("discover_models", { server_id: server.id }));
    setModels((current) => ({ ...current, [server.id]: result.models }));
  }

  async function deleteServer(id: string) {
    const next = await run(() => socket.send("delete_model_server", { server_id: id }));
    setState(next);
    setModels((current) => { const copy = { ...current }; delete copy[id]; return copy; });
    setChatRole(modelValue(next.roles.chat));
    setEmbeddingsRole(modelValue(next.roles.embeddings));
  }

  async function assignRoles() {
    const next = await run(() => socket.send("assign_roles", { chat: parseModelValue(chatRole), embeddings: parseModelValue(embeddingsRole) }));
    setState(next);
  }

  async function probeEmbeddings() {
    const ref = parseModelValue(embeddingsRole);
    if (!ref) throw new Error("Select an embeddings model first");
    const result = await run(() => socket.send("probe_embeddings", ref));
    setProgress({ phase: "probe", dimension: result.dimension });
  }

  async function reloadPersona() {
    const next = await run(() => socket.send("reload_persona"));
    setState(next);
  }

  async function refreshAvatar() {
    const next = await run(() => socket.send("refresh_avatar"));
    setState(next);
  }

  async function setModelTrafficLogging(enabled: boolean) {
    const next = await run(() => socket.send("set_model_traffic_logging", { enabled }));
    setState(next);
  }

  async function processKnowledge() {
    setProgress({ phase: "starting" });
    const result = await run(() => socket.send("process_knowledge", {}, setProgress));
    setProgress({ phase: "complete", ...result });
    setState(await socket.send("get_state"));
  }

  function editServer(server: Server) {
    setServerForm({
      ...server,
      http_proxy: server.http_proxy || "",
      https_proxy: server.https_proxy || "",
      no_proxy: server.no_proxy || "",
      proxy_username: server.proxy_username || "",
      api_key: "",
      proxy_password: "",
    });
  }

  if (!state) return <div className="center-card">{error || "Starting VirtualMate…"}</div>;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><AvatarImage revision={state?.avatar.revision || 0} /></span><strong>VirtualMate</strong></div>
        <button className="new-chat" aria-label="New chat" onClick={clearChat} disabled={busy || messages.length === 0}><Icon name="compose" /> <span>New chat</span></button>
        <button className="export-chat" aria-label="Export conversation" onClick={exportConversation} disabled={busy || messages.length === 0}><Icon name="export" /> <span>Export conversation</span></button>
        <nav className="side-nav" aria-label="Primary navigation">
          <button aria-label="Chat" className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}><Icon name="chat" /><span>Chat</span></button>
          <button aria-label="Administration" className={view === "admin" ? "active" : ""} onClick={() => setView("admin")}><Icon name="settings" /><span>Administration</span></button>
        </nav>
        <div className="sidebar-footer">
          <div className="mini-status"><span className={`status-dot ${state.knowledge.ready ? "ready" : ""}`} /><div><strong>{state.knowledge.ready ? "Knowledge ready" : "Knowledge empty"}</strong><small>{state.knowledge.documents} documents · {state.knowledge.chunks} chunks</small></div></div>
          <div className="profile-name"><span>RAG</span><div><strong>Personal knowledge</strong><small>{state.profile.id}</small></div></div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div><h1>{view === "chat" ? "VirtualMate" : "Administration"}</h1>{view === "chat" && <span className="model-caption">Grounded in your indexed knowledge</span>}</div>
          <div className="topbar-actions"><button className="icon-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"} title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}><Icon name={theme === "dark" ? "sun" : "moon"} /></button><button className="icon-button" onClick={() => setView(view === "chat" ? "admin" : "chat")} aria-label={view === "chat" ? "Open administration" : "Return to chat"}><Icon name={view === "chat" ? "settings" : "chat"} /></button></div>
        </header>
        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}

      {view === "chat" ? (
        <main className="chat-layout">
          <section className="chat-panel">
            <div className="transcript" aria-live="polite">
              {messages.length === 0 && <div className="empty"><span className="empty-mark"><AvatarImage revision={state.avatar.revision} /></span><h2>How can VirtualMate help you today?</h2><p>Ask anything about the project. Every answer will be grounded in your indexed documents.</p>{!state.knowledge.ready && <button className="setup-callout" onClick={() => setView("admin")}><Icon name="warning" /><span><strong>No knowledge index is ready</strong><small>Open Administration to process your documents</small></span><Icon name="arrow" /></button>}</div>}
              {messages.map((message, index) => <Message key={index} message={message} messageIndex={index} avatarRevision={state.avatar.revision} />)}
              {busy && <div className="thinking"><span className="assistant-symbol"><AvatarImage revision={state.avatar.revision} /></span><div><strong>{String(chatProgress?.message || "Working…")}</strong><span>{chatProgress?.phase === "evidence_ready" && typeof chatProgress.evidence_count === "number" ? `${chatProgress.evidence_count} evidence chunk${chatProgress.evidence_count === 1 ? "" : "s"} selected` : ""}</span><div className="thinking-dots"><i></i><i></i><i></i></div></div></div>}
              <div ref={transcriptEnd} />
            </div>
            <div className="composer-area"><form className="composer" onSubmit={sendQuestion}>
              <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Message VirtualMate" rows={1} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
              <button type="submit" disabled={busy || !question.trim()} aria-label="Send question"><Icon name="send" /></button>
            </form><small className="composer-note">VirtualMate answers from retrieved selected memories.</small></div>
          </section>
        </main>
      ) : (
        <main className="admin-layout">
          <section className="page-heading"><div><h1>Settings</h1><p>Manage your persona, knowledge and model connections.</p></div><span className="profile-pill">{state.profile.id}</span></section>

          <section className="grid two">
            <article className="card"><div className="card-title"><div><h2>Persona</h2><p>Trusted identity and response style.</p></div><Status ok={state.persona.loaded} /></div><dl className="paths"><dt>File</dt><dd>{state.paths.persona}</dd><dt>Estimated tokens</dt><dd>{state.persona.estimated_tokens}{state.persona.over_budget ? " — above recommended budget" : ""}</dd></dl><button onClick={reloadPersona} disabled={busy}>Reload persona.md</button></article>
            <article className="card"><div className="card-title"><div><h2>Knowledge</h2><p>Destructive rebuild of Markdown and DOCX sources.</p></div><Status ok={state.knowledge.ready} /></div><dl className="paths"><dt>Directory</dt><dd>{state.paths.knowledge}</dd><dt>Mode</dt><dd>Clean and process from zero</dd><dt>Indexed</dt><dd>{state.knowledge.documents} documents · {state.knowledge.chunks} chunks</dd></dl><button onClick={processKnowledge} disabled={busy}>Process knowledge</button>{progress && <Progress data={progress} />}</article>
          </section>

          <section className="card wide"><div className="card-title"><div><h2>Appearance</h2><p>Optional local avatar for this VirtualMate instance.</p></div><Status ok={state.avatar.configured} /></div><dl className="paths"><dt>Avatar path</dt><dd>{state.paths.avatar}</dd><dt>Format</dt><dd>PNG file named <code>avatar.png</code></dd><dt>Fallback</dt><dd>Built-in VirtualMate avatar</dd></dl><button onClick={refreshAvatar} disabled={busy}>Refresh avatar</button><p className="card-note">Replace the fixed file manually, then use Refresh avatar. No upload or arbitrary path is exposed in the interface.</p></section>

          <section className="card wide"><div className="card-title"><div><h2>Model servers</h2><p>OpenAI-compatible endpoints. Models are discovered with GET /models.</p></div><span>{state.model_servers.length} configured</span></div>
            <div className="ca-hint"><Icon name="certificate" /><div><strong>Corporate CA certificate</strong><span>Place the PEM bundle at <code>{state.paths.corporate_ca}</code> and enable “Use corporate-ca.pem” for the server that requires it.</span></div></div>
            <div className="server-list">{state.model_servers.map((server) => <div className="server-row" key={server.id}><div><strong>{server.alias}</strong><small>{server.base_url}</small><div className="badges"><span>{server.verify_ssl ? "TLS verified" : "TLS verification off"}</span>{server.use_corporate_ca && <span>Corporate CA</span>}{server.proxy_enabled && <span>Proxy enabled</span>}{server.has_api_key && <span>API key</span>}</div></div><div className="row-actions"><button className="secondary" onClick={() => discover(server)} disabled={busy}>Discover models</button><button className="secondary" onClick={() => editServer(server)} disabled={busy}>Edit</button><button className="danger" onClick={() => deleteServer(server.id)} disabled={busy}>Delete</button></div></div>)}</div>
            <form className="server-form" onSubmit={saveServer}><h3>{serverForm.id && state.model_servers.some((item) => item.id === serverForm.id) ? "Edit server" : "Add server"}</h3><div className="form-grid"><label>Identifier<input required value={serverForm.id} onChange={(e) => setServerForm({ ...serverForm, id: e.target.value })} /></label><label>Alias<input required value={serverForm.alias} onChange={(e) => setServerForm({ ...serverForm, alias: e.target.value })} /></label><label className="span-2">Base URL<input required placeholder="https://server.example/v1" value={serverForm.base_url} onChange={(e) => setServerForm({ ...serverForm, base_url: e.target.value })} /></label><label className="span-2">API key <small>{state.model_servers.find((item) => item.id === serverForm.id)?.has_api_key ? "Leave blank to keep the stored key" : "Optional"}</small><input type="password" value={serverForm.api_key} onChange={(e) => setServerForm({ ...serverForm, api_key: e.target.value })} /></label></div><div className="checks"><label><input type="checkbox" checked={serverForm.enabled} onChange={(e) => setServerForm({ ...serverForm, enabled: e.target.checked })} /> Enabled</label><label><input type="checkbox" checked={serverForm.verify_ssl} onChange={(e) => setServerForm({ ...serverForm, verify_ssl: e.target.checked })} /> Verify TLS</label><label><input type="checkbox" checked={serverForm.use_corporate_ca} onChange={(e) => setServerForm({ ...serverForm, use_corporate_ca: e.target.checked })} /> Use corporate-ca.pem</label><label><input type="checkbox" checked={serverForm.follow_redirects} onChange={(e) => setServerForm({ ...serverForm, follow_redirects: e.target.checked })} /> Follow redirects</label><label><input type="checkbox" checked={serverForm.proxy_enabled} onChange={(e) => setServerForm({ ...serverForm, proxy_enabled: e.target.checked })} /> Enable proxy</label></div>{serverForm.proxy_enabled && <div className="proxy-settings"><h4>Proxy settings</h4><p>Uses the same HTTPS-first proxy selection and no-proxy matching as Substrate.</p><div className="form-grid"><label>HTTPS proxy<input placeholder="http://proxy.company:8080" value={serverForm.https_proxy} onChange={(e) => setServerForm({ ...serverForm, https_proxy: e.target.value })} /></label><label>HTTP proxy<input placeholder="http://proxy.company:8080" value={serverForm.http_proxy} onChange={(e) => setServerForm({ ...serverForm, http_proxy: e.target.value })} /></label><label className="span-2">No proxy <small>Comma-separated host names; .company.com matches subdomains.</small><input placeholder="localhost,127.0.0.1,.company.com" value={serverForm.no_proxy} onChange={(e) => setServerForm({ ...serverForm, no_proxy: e.target.value })} /></label><label>Proxy username<input value={serverForm.proxy_username} onChange={(e) => setServerForm({ ...serverForm, proxy_username: e.target.value })} /></label><label>Proxy password <small>{state.model_servers.find((item) => item.id === serverForm.id)?.has_proxy_password ? "Leave blank to keep the stored password" : "Optional"}</small><input type="password" value={serverForm.proxy_password} onChange={(e) => setServerForm({ ...serverForm, proxy_password: e.target.value })} /></label></div></div>}<div className="form-actions"><button type="button" className="secondary" onClick={() => setServerForm({ ...EMPTY_SERVER })}>Reset</button><button type="submit" disabled={busy}>Save server</button></div></form>
          </section>

          <section className="card wide"><div className="card-title"><div><h2>Model traffic diagnostics</h2><p>Optional local trace for troubleshooting model-server communication.</p></div><Status ok={state.diagnostics.model_traffic_logging} /></div><div className="diagnostics-hint"><strong>Includes complete request and response bodies.</strong><span>Useful for diagnosing provider errors, but it may contain prompts, persona text and retrieved knowledge. API and proxy passwords are redacted.</span><code>{state.paths.model_traffic_log}</code></div><div className="checks"><label><input type="checkbox" checked={state.diagnostics.model_traffic_logging} onChange={(event) => setModelTrafficLogging(event.target.checked)} disabled={busy} /> Record model HTTP traffic</label></div></section>

          <section className="card wide"><div className="card-title"><div><h2>Model roles</h2><p>Chat and embeddings can use different servers.</p></div></div><div className="role-grid"><ModelCombobox label="Response model" value={chatRole} onChange={setChatRole} models={availableModels} /><ModelCombobox label="Embeddings model" value={embeddingsRole} onChange={setEmbeddingsRole} models={availableModels} /></div><div className="form-actions"><button className="secondary" onClick={probeEmbeddings} disabled={busy || !embeddingsRole}>Probe embeddings</button><button onClick={assignRoles} disabled={busy}>Save role assignments</button></div></section>
        </main>
      )}
      </div>
    </div>
  );
}

function Message({ message, messageIndex, avatarRevision }: { message: ChatMessage; messageIndex: number; avatarRevision: number }) {
  const evidence = Array.isArray(message.evidence) ? message.evidence : [];
  const warnings = Array.isArray(message.warnings) ? message.warnings : [];
  const content = String(message.content || "");
  const evidencePrefix = `message-${messageIndex}-evidence`;
  const [visibleLatency, setVisibleLatency] = useState<number | null>(null);

  useEffect(() => {
    if (message.role !== "assistant" || typeof message.startedAt !== "number") return;
    const frame = requestAnimationFrame(() => setVisibleLatency(Math.max(0, performance.now() - message.startedAt!)));
    return () => cancelAnimationFrame(frame);
  }, [message.role, message.startedAt]);

  return <article className={`message ${message.role}`}><div className="avatar">{message.role === "user" ? "You" : <AvatarImage revision={avatarRevision} />}</div><div className="message-body"><div className="message-content">{message.role === "assistant" ? <MarkdownAnswer content={content} evidencePrefix={evidencePrefix} evidenceIds={evidence.map((item) => item.evidence_id)} /> : content}</div>{message.role === "assistant" && visibleLatency != null && <div className="response-metrics"><Icon name="clock" /><span>End-to-end response time: {(visibleLatency / 1000).toFixed(2)} s</span></div>}{evidence.length > 0 && <details><summary><Icon name="sources" /> {evidence.length} source{evidence.length === 1 ? "" : "s"}</summary><div className="evidence-list">{evidence.map((item) => <div className="evidence" id={`${evidencePrefix}-${item.evidence_id}`} tabIndex={-1} key={item.evidence_id}><div><strong>[{item.evidence_id}] {item.filename}</strong><span>{item.heading || `Chunk ${item.chunk_index}`}</span></div><p>{item.text}</p><div className="evidence-footer"><small>{item.match_type} · score {Number.isFinite(Number(item.score)) ? Number(item.score).toFixed(4) : "n/a"}</small><button type="button" className="evidence-back" onClick={(event) => returnToCitation(event.currentTarget)}>Back to citation</button></div></div>)}</div></details>}{warnings.length > 0 && <small className="warning">{warnings.join(" · ")}</small>}</div></article>;
}

function MarkdownAnswer({ content, evidencePrefix, evidenceIds }: { content: string; evidencePrefix: string; evidenceIds: string[] }) {
  const evidenceLinkPlugin = useMemo(() => createEvidenceLinkPlugin(evidencePrefix, evidenceIds), [evidencePrefix, evidenceIds.join("|")]);
  return <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm, evidenceLinkPlugin]} components={{
    pre({ children }) {
      if (React.isValidElement(children) && children.type === MermaidDiagram) return <>{children}</>;
      return <pre>{children}</pre>;
    },
    code({ className, children, ...props }) {
      const language = /language-([^\s]+)/.exec(className || "")?.[1]?.toLowerCase();
      if (language === "mermaid") return <MermaidDiagram source={String(children).replace(/\n$/, "")} />;
      return <code className={className} {...props}>{children}</code>;
    },
    a({ children, ...props }) {
      if (props.href?.startsWith(`#${evidencePrefix}-`)) return <a {...props} onClick={(event) => { event.preventDefault(); navigateToEvidence(event.currentTarget); }}>{children}</a>;
      return <a {...props} target="_blank" rel="noreferrer">{children}</a>;
    },
  }}>{content}</ReactMarkdown></div>;
}

function createEvidenceLinkPlugin(evidencePrefix: string, evidenceIds: string[]) {
  const valid = new Set(evidenceIds.map((id) => String(id).toUpperCase()));
  return () => (tree: any) => {
    let occurrence = 0;
    function transform(node: any) {
      if (!node || !Array.isArray(node.children) || ["link", "code", "inlineCode"].includes(node.type)) return;
      const next: any[] = [];
      for (const child of node.children) {
        if (child?.type !== "text" || typeof child.value !== "string") {
          transform(child);
          next.push(child);
          continue;
        }
        const expression = /\[(E\d+)]/gi;
        let cursor = 0;
        let match: RegExpExecArray | null;
        while ((match = expression.exec(child.value)) !== null) {
          if (match.index > cursor) next.push({ type: "text", value: child.value.slice(cursor, match.index) });
          const evidenceId = match[1].toUpperCase();
          if (valid.has(evidenceId)) {
            occurrence += 1;
            next.push({
              type: "link",
              url: `#${evidencePrefix}-${evidenceId}`,
              data: { hProperties: { className: ["evidence-citation"], id: `${evidencePrefix}-citation-${evidenceId}-${occurrence}` } },
              children: [{ type: "text", value: `[${evidenceId}]` }],
            });
          } else {
            next.push({ type: "text", value: match[0] });
          }
          cursor = match.index + match[0].length;
        }
        if (cursor < child.value.length) next.push({ type: "text", value: child.value.slice(cursor) });
      }
      node.children = next;
    }
    transform(tree);
  };
}

function navigateToEvidence(link: HTMLAnchorElement) {
  const targetId = decodeURIComponent(link.hash.slice(1));
  const target = document.getElementById(targetId);
  if (!target) return;
  const details = target.closest("details");
  if (details instanceof HTMLDetailsElement) details.open = true;
  target.dataset.returnTo = link.id;
  target.classList.remove("citation-highlight");
  void target.offsetWidth;
  target.classList.add("citation-highlight");
  if (typeof target.scrollIntoView === "function") target.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => target.classList.remove("citation-highlight"), 2200);
}

function returnToCitation(button: HTMLButtonElement) {
  const evidence = button.closest<HTMLElement>(".evidence");
  const citation = evidence?.dataset.returnTo ? document.getElementById(evidence.dataset.returnTo) : null;
  if (citation && typeof citation.scrollIntoView === "function") citation.scrollIntoView({ behavior: "smooth", block: "center" });
}

function MermaidDiagram({ source }: { source: string }) {
  const diagramId = useRef(`virtualmate-mermaid-${++mermaidDiagramSequence}`).current;
  const container = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const [renderTheme, setRenderTheme] = useState<"light" | "dark">(() => document.documentElement.dataset.theme === "dark" ? "dark" : "light");

  useEffect(() => {
    let active = true;
    setSvg("");
    setError("");
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: renderTheme === "dark" ? "dark" : "neutral" });
    mermaid.render(`${diagramId}-${renderTheme}`, source)
      .then((result) => { if (active) setSvg(result.svg); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [diagramId, source, renderTheme]);

  useEffect(() => {
    const observer = new MutationObserver(() => setRenderTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const update = () => setFullscreen(document.fullscreenElement === container.current);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  async function toggleFullscreen() {
    if (document.fullscreenElement === container.current) {
      if (typeof document.exitFullscreen === "function") await document.exitFullscreen();
      return;
    }
    const target = container.current;
    if (target && typeof target.requestFullscreen === "function") await target.requestFullscreen();
  }

  function downloadSvg() {
    if (!svg) return;
    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${diagramId}.svg`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  if (error) return <div className="mermaid-error"><strong>Mermaid diagram could not be rendered.</strong><code>{source}</code></div>;
  if (!svg) return <div className="mermaid-loading">Rendering diagram…</div>;
  return <div className="mermaid-diagram-shell" ref={container}>
    <div className="mermaid-toolbar">
      <button type="button" onClick={toggleFullscreen} aria-label={fullscreen ? "Exit diagram fullscreen" : "View diagram fullscreen"}><Icon name={fullscreen ? "collapse" : "expand"} />{fullscreen ? "Exit fullscreen" : "Fullscreen"}</button>
      <button type="button" onClick={downloadSvg} aria-label="Download diagram as SVG"><Icon name="download" />Download SVG</button>
    </div>
    <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />
  </div>;
}

function AvatarImage({ revision }: { revision: number }) { return <img className="avatar-image" src={`/api/avatar?v=${revision}`} alt="" />; }

type ModelOption = { value: string; label: string };

function ModelCombobox({ label, value, onChange, models }: { label: string; value: string; onChange: (value: string) => void; models: ModelOption[] }) {
  const root = useRef<HTMLDivElement>(null);
  const selected = models.find((model) => model.value === value);
  const [query, setQuery] = useState(selected?.label || "");
  const [open, setOpen] = useState(false);

  useEffect(() => setQuery(selected?.label || ""), [selected?.label, value]);
  useEffect(() => {
    function close(event: MouseEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const filtered = models.filter((model) => model.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <div className="combobox" ref={root}>
    <label>{label}
      <div className="combobox-input-wrap">
        <input aria-label={label} role="combobox" aria-expanded={open} aria-controls={`${label}-models`} value={query} placeholder="Search discovered models…" onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); onChange(""); setOpen(true); }} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }} />
        <button type="button" className="combobox-toggle" aria-label={`Show ${label.toLowerCase()} options`} onMouseDown={(event) => event.preventDefault()} onClick={() => setOpen((current) => !current)}><Icon name="chevron" /></button>
      </div>
    </label>
    {open && <div className="combobox-menu" id={`${label}-models`} role="listbox">{filtered.length > 0 ? filtered.map((model) => <button type="button" role="option" aria-selected={model.value === value} key={model.value} onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(model.value); setQuery(model.label); setOpen(false); }}><strong>{model.label.split(" — ")[1] || model.label}</strong><small>{model.label.split(" — ")[0]}</small></button>) : <span className="combobox-empty">No discovered models match “{query}”.</span>}</div>}
  </div>;
}

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    chat: <path d="M5 6.8A2.8 2.8 0 0 1 7.8 4h8.4A2.8 2.8 0 0 1 19 6.8v5.4a2.8 2.8 0 0 1-2.8 2.8H11l-4.5 3v-3.4A2.8 2.8 0 0 1 5 12.2Z" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V20h-3v-.09a1.7 1.7 0 0 0-1.1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 14.7a1.7 1.7 0 0 0-1.55-1H5v-3h.1A1.7 1.7 0 0 0 6.64 9.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06A1.7 1.7 0 0 0 10.3 6a1.7 1.7 0 0 0 1-1.55V4h3v.1a1.7 1.7 0 0 0 1.1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06A1.7 1.7 0 0 0 19 9.3a1.7 1.7 0 0 0 1.55 1H21v3h-.1A1.7 1.7 0 0 0 19.4 15Z" /></>,
    compose: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" /></>,
    send: <><path d="m6 12 6-6 6 6" /><path d="M12 18V6" /></>,
    sources: <><path d="M4 7h16M4 12h16M4 17h10" /></>,
    warning: <><path d="M10.3 4.3 3.2 17a2 2 0 0 0 1.75 3h14.1a2 2 0 0 0 1.75-3L13.7 4.3a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 3h.01" /></>,
    arrow: <path d="m9 18 6-6-6-6" />,
    certificate: <><path d="M6 3h9l3 3v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v4h4M8 11h6M8 14h4" /><path d="m13 17 1.5 4 1.5-1 1.5 1 1.5-4" /></>,
    chevron: <path d="m7 9 5 5 5-5" />,
    expand: <><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" /><path d="m3 8 6-6m12 6-6-6M3 16l6 6m12-6-6 6" /></>,
    collapse: <><path d="M9 9H4V4M15 9h5V4M9 15H4v5M15 15h5v5" /><path d="M4 9 10 3m10 6-6-6M4 15l6 6m10-6-6 6" /></>,
    download: <><path d="M12 3v12m0 0 5-5m-5 5-5-5" /><path d="M5 20h14" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    export: <><path d="M12 3v12m0-12 4 4m-4-4L8 7" /><path d="M5 13v7h14v-7" /></>,
    moon: <path d="M20.2 15.1A8.5 8.5 0 0 1 8.9 3.8 8.6 8.6 0 1 0 20.2 15.1Z" />,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></>,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Status({ ok }: { ok: boolean }) { return <span className={`status ${ok ? "ok" : "bad"}`}>{ok ? "Ready" : "Not ready"}</span>; }
function escapeHtml(value: string) { return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!); }
function Progress({ data }: { data: Record<string, any> }) {
  const phase = String(data.phase || "working").replaceAll("_", " ");
  const vectorizing = data.phase === "vectorizing";
  return (
    <div className="progress">
      <strong>{phase}</strong>
      {data.document && <span className="progress-document">{data.document}</span>}
      {data.total > 0 && <><span>Documents: {data.current || 0} / {data.total}</span><progress value={data.current || 0} max={data.total} /></>}
      {data.document_chunks != null && <span>Chunks from this document: {data.document_chunks}</span>}
      {vectorizing && <><span>Vectorizing this document: {data.vectorization_current || 0} / {data.vectorization_total || 0} chunks</span><progress value={data.vectorization_current || 0} max={data.vectorization_total || 1} /></>}
      {data.vectorized_chunks != null && <span>Total vectors generated: {data.vectorized_chunks}</span>}
      {data.chunks_expected != null && <span>Total chunks after this document: {data.chunks_expected}</span>}
      {data.chunks_generated != null && <span>Indexed so far: {data.documents_processed || 0} documents · {data.chunks_generated} chunks</span>}
      {data.chunks_generated == null && data.chunks != null && <span>Indexed so far: {data.chunks} chunks</span>}
      {data.dimension && <span>Dimension: {data.dimension}</span>}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><AppErrorBoundary><App /></AppErrorBoundary></React.StrictMode>);

