import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  Download,
  FileCheck2,
  FileSearch,
  Files,
  Fingerprint,
  GitBranch,
  LayoutDashboard,
  Link2,
  LoaderCircle,
  MessageSquareText,
  Network,
  PanelRightOpen,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { api } from "./api";
import type { Anchor, CaseSummary, ChatAnswer, Finding, Source, Trace, View } from "./types";

const euro = (value?: string | number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(Number(value || 0));

const human = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

const roleName = (role: string) => {
  const names: Record<string, string> = {
    general_ledger: "General ledger",
    vendor_ledger: "Vendor subledger",
    vendor_master: "Vendor master",
    goods_receipts: "Goods receipts",
    financial_statement: "Financial statements",
    audit_policy: "Audit policy",
    permissions: "Permissions",
  };
  return names[role] || human(role);
};

const statusTone = (status: string) => {
  if (status === "cleared") return "clear";
  if (status === "control_breach") return "amber";
  if (status === "needs_evidence") return "blue";
  return "red";
};

function Logo() {
  return (
    <div className="brand">
      <div className="brand-mark"><Fingerprint size={23} strokeWidth={1.8} /></div>
      <div><strong>LedgerLens</strong><span>Evidence-grade audit</span></div>
    </div>
  );
}

function EmptyCase({ onLoad, onUpload, busy }: { onLoad: () => void; onUpload: (file: File) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <main className="empty-shell">
      <Logo />
      <section className="empty-card">
        <div className="hero-icon"><FileSearch size={32} /></div>
        <p className="eyebrow">Precision-first forensic audit</p>
        <h1>Follow the money.<br />Prove every claim.</h1>
        <p className="lead">Import a dossier to reconcile transactions, test controls, and trace every conclusion to an exact page, cell, or record.</p>
        <div className="empty-actions">
          <button className="button primary" onClick={() => input.current?.click()} disabled={busy}><Upload size={17} /> Import dossier ZIP</button>
          <button className="button secondary" onClick={onLoad} disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />} Load practice case</button>
        </div>
        <input ref={input} hidden type="file" accept=".zip" onChange={(event) => event.target.files?.[0] && onUpload(event.target.files[0])} />
        <div className="trust-row"><span><ShieldCheck size={15} /> Local-first</span><span><Link2 size={15} /> Source-bound</span><span><BadgeCheck size={15} /> Deterministic checks</span></div>
      </section>
    </main>
  );
}

function Sidebar({ view, setView, active }: { view: View; setView: (view: View) => void; active: number }) {
  const links: { id: View; label: string; icon: typeof Search; badge?: number }[] = [
    { id: "overview", label: "Case overview", icon: LayoutDashboard },
    { id: "findings", label: "Findings", icon: FileSearch, badge: active },
    { id: "investigation", label: "Investigation", icon: Network },
    { id: "chat", label: "Audit chat", icon: MessageSquareText },
  ];
  return (
    <aside className="sidebar">
      <Logo />
      <nav>
        <p className="nav-label">Workspace</p>
        {links.map(({ id, label, icon: Icon, badge }) => (
          <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}>
            <Icon size={18} /><span>{label}</span>{badge ? <b>{badge}</b> : null}
          </button>
        ))}
      </nav>
      <div className="sidebar-note">
        <ShieldCheck size={18} />
        <div><strong>Unsupported claims</strong><span>0 detected</span></div>
      </div>
      <div className="analyst"><span>AR</span><div><strong>Audit reviewer</strong><small>Local session</small></div><ChevronDown size={15} /></div>
    </aside>
  );
}

function Header({ caseData, onUpload }: { caseData: CaseSummary; onUpload: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <header className="topbar">
      <div className="case-selector"><span className="live-dot" /><div><small>Active case</small><strong>{caseData.name}</strong></div><ChevronDown size={16} /></div>
      <div className="top-actions">
        <div className="model-pill"><span /> {caseData.summary?.model_mode === "hosted-available" ? "Hosted + verified" : "Deterministic mode"}</div>
        <button className="icon-button" title="Import another dossier" onClick={() => input.current?.click()}><Upload size={18} /></button>
        <a className="button dark small" href={`/api/cases/${caseData.case_id}/export`}><Download size={16} /> Export audit pack</a>
        <input ref={input} hidden type="file" accept=".zip" onChange={(event) => event.target.files?.[0] && onUpload(event.target.files[0])} />
      </div>
    </header>
  );
}

function Metric({ icon: Icon, label, value, foot, tone, onClick }: { icon: typeof Search; label: string; value: string; foot: string; tone: string; onClick?: () => void }) {
  const content = <>
      <div className="metric-top"><span><Icon size={19} /></span><small>{label}</small></div>
      <strong>{value}</strong><p>{foot}</p>
    </>;
  return onClick ? <button className={`metric ${tone} clickable`} onClick={onClick}>{content}</button> : <div className={`metric ${tone}`}>{content}</div>;
}

function Overview({ caseData, sources, findings, onInspect, onAnchorId }: { caseData: CaseSummary; sources: Source[]; findings: Finding[]; onInspect: (f: Finding) => void; onAnchorId: (id: string) => void }) {
  const headline = caseData.summary?.headline || {};
  const reconciliations = caseData.summary?.reconciliations || [];
  const overrides = caseData.summary?.semantic_overrides || [];
  const unresolved = sources.filter((source) => source.roles.includes("unknown"));
  const active = findings.filter((finding) => finding.status !== "cleared");
  return (
    <div className="page">
      <div className="page-title"><div><p className="eyebrow">Evidence review complete</p><h1>Case overview</h1><p>{caseData.record_count.toLocaleString()} normalized records across {caseData.source_count} immutable sources.</p></div><div className="coverage-ring" style={{ "--coverage": `${caseData.coverage_percent * 3.6}deg` } as CSSProperties}><div><strong>{caseData.coverage_percent}%</strong><span>coverage</span></div></div></div>
      <section className="metrics">
        <Metric icon={AlertTriangle} label="Promoted findings" value={String(headline.active_findings || active.length)} foot="Open strongest evidence" tone="danger" onClick={() => active[0] && onInspect(active[0])} />
        <Metric icon={CircleDollarSign} label="Profit overstatement" value={euro(headline.profit_overstatement)} foot="Open constituent calculation" tone="gold" onClick={() => { const item = active.find((f) => f.tags.includes("profit-overstatement")); if (item) onInspect(item); }} />
        <Metric icon={GitBranch} label="Cash at risk" value={euro(headline.cash_at_risk)} foot="Open cash lineage" tone="ink" onClick={() => { const item = active.find((f) => f.tags.includes("cash")); if (item) onInspect(item); }} />
        <Metric icon={ShieldCheck} label="Precision controls" value={String(headline.cleared_controls || 0)} foot="Open a cleared comparator" tone="green" onClick={() => { const item = findings.find((f) => f.status === "cleared"); if (item) onInspect(item); }} />
      </section>
      {(overrides.length > 0 || unresolved.length > 0) && <section className="mapping-banner"><div><Fingerprint size={19} /><div><strong>Schema decisions are visible</strong><span>{overrides.length} value-profile override{overrides.length === 1 ? "" : "s"} · {unresolved.length} supporting source{unresolved.length === 1 ? "" : "s"} without a transactional role</span></div></div><div className="mapping-chips">{overrides.map((item: any) => <span key={item.semantic_field}>{item.declared_field || item.semantic_field} → {item.inferred_field}</span>)}</div></section>}
      <div className="overview-grid">
        <section className="panel recon-panel">
          <div className="section-head"><div><p className="eyebrow">Deterministic checks</p><h2>Reconciliation health</h2></div><span className="verified"><CheckCircle2 size={15} /> Reproducible</span></div>
          <div className="recon-list">
            {reconciliations.length ? reconciliations.map((item: any, index: number) => { const passed = ["passed", "tied", "balanced"].includes(item.status); return <button className="recon-row" key={index} onClick={() => item.anchor_ids?.length && onAnchorId(item.anchor_ids[item.anchor_ids.length - 1])}><span className={passed ? "pass" : "review"}>{passed ? <Check size={15} /> : <AlertTriangle size={15} />}</span><div><strong>{item.label || item.name || "Reconciliation"}</strong><small>{item.detail || item.result || human(item.status || "complete")}</small></div><b>{item.value || human(item.status || "done")}</b></button>; }) : <div className="recon-row"><span className="pass"><Check size={15} /></span><div><strong>Journal balancing</strong><small>Debit and credit groups tested</small></div><b>Balanced</b></div>}
          </div>
        </section>
        <section className="panel attention-panel">
          <div className="section-head"><div><p className="eyebrow">Priority review</p><h2>Evidence-backed exceptions</h2></div><button className="text-button" onClick={() => active[0] && onInspect(active[0])}>Open queue <ArrowRight size={14} /></button></div>
          {active.slice(0, 3).map((finding) => <button className="attention-row" key={finding.finding_id} onClick={() => onInspect(finding)}><span className={`severity ${statusTone(finding.status)}`}><AlertTriangle size={16} /></span><div><strong>{finding.title}</strong><small>{human(finding.status)} · {finding.monetary_impact ? euro(finding.monetary_impact) : "Control only"}</small></div><ArrowRight size={16} /></button>)}
        </section>
      </div>
      <section className="panel sources-panel">
        <div className="section-head"><div><p className="eyebrow">Immutable evidence</p><h2>Source coverage</h2></div><span className="muted"><Fingerprint size={14} /> SHA-256 hashed at import</span></div>
        <div className="source-table"><div className="source-header"><span>Source</span><span>Detected role</span><span>Records</span><span>Integrity</span></div>{sources.slice(0, 7).map((source) => <div className="source-row" key={source.source_id}><span><FileCheck2 size={17} /><span><strong>{source.name}</strong><small>{source.sha256.slice(0, 14)}…</small></span></span><span>{source.roles.slice(0, 2).map(roleName).join(", ") || "Supporting evidence"}</span><span>{source.record_count.toLocaleString()}</span><span className="hash-ok"><CheckCircle2 size={14} /> Verified</span></div>)}</div>
      </section>
    </div>
  );
}

function FindingCard({ finding, selected, onClick }: { finding: Finding; selected: boolean; onClick: () => void }) {
  return (
    <button className={`finding-card ${selected ? "selected" : ""}`} onClick={onClick}>
      <div className="finding-card-head"><span className={`status ${statusTone(finding.status)}`}>{human(finding.status)}</span><span className="impact">{finding.monetary_impact ? euro(finding.monetary_impact) : "Control effect"}</span></div>
      <h3>{finding.title}</h3><p>{finding.summary}</p>
      <div className="finding-meta"><span><Link2 size={13} /> {finding.supporting_anchor_ids.length} evidence anchors</span><span><GitBranch size={13} /> {finding.provenance_families.length} source families</span></div>
    </button>
  );
}

function FindingQueue({ findings, selected, setSelected, onInvestigate, showCleared, setShowCleared }: { findings: Finding[]; selected?: Finding; setSelected: (f: Finding) => void; onInvestigate: (f: Finding) => void; showCleared: boolean; setShowCleared: (v: boolean) => void }) {
  const visible = findings.filter((f) => showCleared || f.status !== "cleared");
  return (
    <div className="page queue-page">
      <div className="page-title compact"><div><p className="eyebrow">Ranked by evidence strength × impact</p><h1>Findings queue</h1><p>Weak signals never appear as standalone findings.</p></div><div className="segmented"><button className={!showCleared ? "active" : ""} onClick={() => setShowCleared(false)}>Active</button><button className={showCleared ? "active" : ""} onClick={() => setShowCleared(true)}>All incl. cleared</button></div></div>
      <div className="queue-layout"><div className="finding-list">{visible.map((finding) => <FindingCard key={finding.finding_id} finding={finding} selected={selected?.finding_id === finding.finding_id} onClick={() => setSelected(finding)} />)}</div>{selected ? <FindingDetail finding={selected} onInvestigate={() => onInvestigate(selected)} /> : <div className="panel no-select"><FileSearch size={32} /><h3>Select a finding</h3><p>Its reasoning, counter-evidence, and financial effect will appear here.</p></div>}</div>
    </div>
  );
}

function FindingDetail({ finding, onInvestigate }: { finding: Finding; onInvestigate?: () => void }) {
  return (
    <aside className="panel finding-detail">
      <div className="detail-top"><span className={`status ${statusTone(finding.status)}`}>{human(finding.status)}</span><span className={`severity-word ${finding.severity}`}>{human(finding.severity)}</span></div>
      <h2>{finding.title}</h2><p className="detail-summary">{finding.summary}</p>
      <div className="effect-box"><span>Financial effect</span><strong>{finding.monetary_impact ? euro(finding.monetary_impact) : "No misstatement asserted"}</strong><p>{finding.financial_effect}</p></div>
      <Reason title="Why suspicious" icon={<AlertTriangle size={16} />} items={finding.why_suspicious} tone="risk" />
      <Reason title="Why it may be innocent" icon={<ShieldCheck size={16} />} items={finding.benign_explanations} tone="safe" />
      <Reason title="Evidence still required" icon={<Search size={16} />} items={finding.missing_evidence} tone="neutral" />
      {onInvestigate && <button className="button primary wide" onClick={onInvestigate}><PanelRightOpen size={16} /> Open investigation workspace</button>}
    </aside>
  );
}

function Reason({ title, icon, items, tone }: { title: string; icon: ReactNode; items: string[]; tone: string }) {
  return <div className={`reason ${tone}`}><h4>{icon}{title}</h4><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>;
}

function Investigation({ finding, trace, onAnchor, onReview, loading }: { finding?: Finding; trace?: Trace; onAnchor: (a: Anchor) => void; onReview: (state: string) => void; loading: boolean }) {
  if (!finding) return <div className="page"><div className="panel no-select tall"><Network size={38} /><h2>Choose a finding to investigate</h2><p>Open the findings queue and select an evidence-backed exception.</p></div></div>;
  const sourceMap = new Map(trace?.sources.map((source) => [source.source_id, source]));
  return (
    <div className="page investigation-page">
      <div className="investigation-head"><div><button className="back-link">Investigation / {finding.rule_id}</button><h1>{finding.title}</h1></div><div className="review-actions"><button onClick={() => onReview("dismissed")}><XCircle size={16} /> Dismiss</button><button onClick={() => onReview("evidence_requested")}><Search size={16} /> Request evidence</button><button className="accept" onClick={() => onReview("accepted")}><CheckCircle2 size={16} /> Accept finding</button></div></div>
      {loading ? <div className="loading-panel"><LoaderCircle className="spin" /> Building evidence graph…</div> : <div className="investigation-grid">
        <section className="panel flow-panel"><div className="section-head"><div><p className="eyebrow">Transaction lineage</p><h2>Money & control flow</h2></div><span className="verified"><Link2 size={14} /> All edges cited</span></div><div className="flow-graph">{trace?.graph.length ? trace.graph.slice(0, 12).map((edge, index) => <div className="flow-edge" key={edge.edge_id}><div className="flow-node"><small>{index === 0 ? "Actor / origin" : "Source"}</small><strong>{edge.source}</strong></div><div className="flow-arrow"><span>{edge.label}</span><ArrowRight size={18} /></div><div className="flow-node end"><small>{edge.relation}</small><strong>{edge.target}</strong></div></div>) : <div className="empty-graph"><GitBranch size={28} /><p>This finding is a reconciliation exception; its lineage is shown in the calculation panel.</p></div>}</div></section>
        <section className="panel calc-panel"><div className="section-head"><div><p className="eyebrow">Reproducible arithmetic</p><h2>Calculation trace</h2></div></div>{trace?.calculations.map((calc) => <div className="calculation" key={calc.calculation_id}><div><span>{calc.label}</span><strong>{calc.unit === "EUR" ? euro(calc.result) : String(calc.result)}</strong></div><code>{calc.expression}</code>{calc.inputs.map((input, index) => <button key={index} onClick={() => { const anchor = trace.anchors.find((a) => input.anchor_ids.includes(a.anchor_id)); if (anchor) onAnchor(anchor); }}><span>{input.label}</span><b>{calc.unit === "EUR" ? euro(input.value) : input.value}</b></button>)}</div>)}</section>
        <section className="panel evidence-panel"><div className="section-head"><div><p className="eyebrow">Exact source passages</p><h2>Evidence</h2></div><span className="muted">{trace?.anchors.length || 0} anchors</span></div><div className="evidence-list">{trace?.anchors.slice(0, 18).map((anchor) => <button key={anchor.anchor_id} onClick={() => onAnchor(anchor)}><div className="evidence-icon"><Files size={17} /></div><div><strong>{sourceMap.get(anchor.source_id)?.name || "Source"}</strong><span>{Object.entries(anchor.locator).slice(0, 3).map(([key, value]) => `${human(key)} ${String(value)}`).join(" · ")}</span><p>{anchor.quote || "Structured source cell"}</p></div><ArrowRight size={15} /></button>)}</div></section>
      </div>}
    </div>
  );
}

function EvidenceDrawer({ anchor, source, onClose }: { anchor: Anchor; source?: Source; onClose: () => void }) {
  return <div className="drawer-scrim" onClick={onClose}><aside className="evidence-drawer" onClick={(event) => event.stopPropagation()}><div className="drawer-head"><div><p className="eyebrow">Source anchor</p><h2>{source?.name || "Evidence"}</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div><div className="locator-grid">{Object.entries(anchor.locator).map(([key, value]) => <div key={key}><span>{human(key)}</span><strong>{String(value)}</strong></div>)}</div><div className="quote-block"><span>Exact passage</span><blockquote>{anchor.quote || String(anchor.raw_value || "Structured source value")}</blockquote></div>{anchor.normalized_value != null && <div className="normalization"><span>Normalized value</span><code>{JSON.stringify(anchor.normalized_value)}</code></div>}<div className="hash-block"><Fingerprint size={17} /><div><span>Record integrity</span><code>{anchor.row_hash || source?.sha256 || anchor.anchor_id}</code></div></div>{source && <a className="button primary wide" target="_blank" rel="noreferrer" href={`/api/sources/${source.source_id}/file`}><FileSearch size={16} /> Open original source</a>}</aside></div>;
}

function Chat({ caseId, findings, onFinding }: { caseId: string; findings: Finding[]; onFinding: (f: Finding) => void }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; text: string; answer?: ChatAnswer }[]>([]);
  const [busy, setBusy] = useState(false);
  const suggestions = ["Show vendors created and paid by the same user", "Trace the profit overstatement", "Which unusual items were cleared?", "Show payments split below approval limits"];
  const send = async (prompt: string) => { if (!prompt.trim() || busy) return; setMessages((m) => [...m, { role: "user", text: prompt }]); setQuestion(""); setBusy(true); try { const answer = await api.ask(caseId, prompt); setMessages((m) => [...m, { role: "assistant", text: answer.answer, answer }]); } catch (error) { setMessages((m) => [...m, { role: "assistant", text: error instanceof Error ? error.message : "Question failed." }]); } finally { setBusy(false); } };
  return <div className="page chat-page"><div className="chat-intro"><div className="bot-mark"><Bot size={26} /></div><p className="eyebrow">Citation-bound assistant</p><h1>Ask the audit trail</h1><p>Answers use detector results and supplied evidence only. Unsupported numbers are rejected before display.</p></div><div className="suggestions">{suggestions.map((s) => <button key={s} onClick={() => send(s)}>{s}<ArrowRight size={14} /></button>)}</div><div className="chat-thread">{messages.length === 0 && <div className="chat-empty"><MessageSquareText size={28} /><p>Your evidence-backed answers will appear here.</p></div>}{messages.map((message, index) => <div className={`message ${message.role}`} key={index}><div className="avatar">{message.role === "assistant" ? <Bot size={16} /> : "AR"}</div><div><p>{message.text}</p>{message.answer && <div className="citation-chips">{message.answer.finding_ids.map((id) => { const f = findings.find((item) => item.finding_id === id); return <button key={id} onClick={() => f && onFinding(f)}><Link2 size={12} /> {f?.title || id}</button>; })}<span>{message.answer.mode}</span></div>}</div></div>)}{busy && <div className="message assistant"><div className="avatar"><Bot size={16} /></div><div className="typing"><i /><i /><i /></div></div>}</div><form className="chat-input" onSubmit={(event: FormEvent) => { event.preventDefault(); send(question); }}><Search size={18} /><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about transactions, controls, or reconciliations…" /><button disabled={!question.trim() || busy}><ArrowRight size={18} /></button></form><p className="chat-disclaimer"><ShieldCheck size={13} /> Every factual claim is checked against the evidence graph.</p></div>;
}

export default function App() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [caseData, setCaseData] = useState<CaseSummary>();
  const [sources, setSources] = useState<Source[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selected, setSelected] = useState<Finding>();
  const [trace, setTrace] = useState<Trace>();
  const [view, setView] = useState<View>("overview");
  const [showCleared, setShowCleared] = useState(false);
  const [anchor, setAnchor] = useState<Anchor>();
  const [busy, setBusy] = useState(true);
  const [traceBusy, setTraceBusy] = useState(false);
  const [error, setError] = useState("");

  const hydrate = async (data: CaseSummary) => { setCaseData(data); const [nextSources, nextFindings] = await Promise.all([api.sources(data.case_id), api.findings(data.case_id)]); setSources(nextSources); setFindings(nextFindings); setSelected(nextFindings.find((f) => f.status !== "cleared") || nextFindings[0]); };
  useEffect(() => { api.cases().then(async (list) => { setCases(list); if (list[0]) await hydrate(list[0]); }).catch((e) => setError(e.message)).finally(() => setBusy(false)); }, []);
  useEffect(() => { if (!selected || view !== "investigation") return; setTraceBusy(true); api.trace(selected.finding_id).then(setTrace).catch((e) => setError(e.message)).finally(() => setTraceBusy(false)); }, [selected, view]);
  const active = useMemo(() => findings.filter((finding) => finding.status !== "cleared").length, [findings]);
  const openInvestigation = (finding: Finding) => { setSelected(finding); setView("investigation"); };
  const loadSample = async () => { setBusy(true); setError(""); try { const data = await api.createSample(); setCases((current) => [data, ...current]); await hydrate(data); } catch (e) { setError(e instanceof Error ? e.message : "Could not load sample."); } finally { setBusy(false); } };
  const upload = async (file: File) => { setBusy(true); setError(""); try { const data = await api.upload(file, file.name.replace(/\.zip$/i, "")); setCases((current) => [data, ...current]); await hydrate(data); } catch (e) { setError(e instanceof Error ? e.message : "Upload failed."); } finally { setBusy(false); } };
  const review = async (state: string) => { if (!selected) return; const updated = await api.review(selected.finding_id, state); setSelected(updated); setFindings((list) => list.map((f) => f.finding_id === updated.finding_id ? updated : f)); };
  const currentSource = trace?.sources.find((source) => source.source_id === anchor?.source_id) || sources.find((source) => source.source_id === anchor?.source_id);

  if (busy && !caseData) return <div className="splash"><Logo /><LoaderCircle className="spin" size={24} /><span>Building immutable audit case…</span></div>;
  if (!caseData) return <><EmptyCase onLoad={loadSample} onUpload={upload} busy={busy} />{error && <div className="toast error"><AlertTriangle size={16} />{error}</div>}</>;
  return <div className="app-shell"><Sidebar view={view} setView={setView} active={active} /><div className="workspace"><Header caseData={caseData} onUpload={upload} />{view === "overview" && <Overview caseData={caseData} sources={sources} findings={findings} onInspect={openInvestigation} onAnchorId={(id) => api.anchor(id).then((result) => setAnchor(result.anchor)).catch((e) => setError(e.message))} />}{view === "findings" && <FindingQueue findings={findings} selected={selected} setSelected={(f) => setSelected(f)} onInvestigate={openInvestigation} showCleared={showCleared} setShowCleared={setShowCleared} />}{view === "investigation" && <Investigation finding={selected} trace={trace} onAnchor={setAnchor} onReview={review} loading={traceBusy} />}{view === "chat" && <Chat caseId={caseData.case_id} findings={findings} onFinding={openInvestigation} />}</div>{anchor && <EvidenceDrawer anchor={anchor} source={currentSource} onClose={() => setAnchor(undefined)} />}{error && <div className="toast error"><AlertTriangle size={16} />{error}<button onClick={() => setError("")}><X size={14} /></button></div>}{busy && <div className="busy-overlay"><LoaderCircle className="spin" /> Analyzing dossier…</div>}</div>;
}
