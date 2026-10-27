import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  CircleNotch,
  ClockCounterClockwise,
  CloudArrowUp,
  Copy,
  DownloadSimple,
  FileDoc,
  FilePdf,
  FileText,
  FolderOpen,
  NotePencil,
  Plus,
  ShieldCheck,
  Sparkle,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { useLocale } from "../locale.jsx";
import { ChangeHighlights } from "../ChangeHighlights.jsx";
import { changedPassages, diffChange } from "../change-highlights.js";
import { reviewTargetFromFinding } from "../review-target.js";
import { canStartModification, deterministicCleanupCount, snapshotMatchesDraft, workbenchAction } from "../workbench-action.js";
import { billableUnitLabel } from "../billing-text.js";
import {
  billableChars,
  createWorkspace,
  downloadBase64,
  fileToBase64,
  getApi,
  getUnsavedDrafts,
  getWorkspace,
  getUnsavedLocalBackup,
  openWorkspace,
  postApi,
  requestId,
  restoreWorkspace,
  saveWorkspaceNow,
  updateWorkspace,
  usePlatform,
  useWorkspaceSaveStatus,
} from "../platform.jsx";
import "./live-core-pages.css";

const SAMPLE_ZH = `在数字化技术不断快速发展的时代背景下，人工智能写作工具逐渐进入高校学习场景。本文将深入探讨一个至关重要的问题：学生应当如何合理使用这些工具。

这不仅是一次工具更新，更是学习方式的深刻变革。系统可以提供资料整理、语句润色和格式检查。部分未具名的专家认为，这些功能可能在一定程度上或许能够提升写作效率。

本次调查共收到 126 份问卷，其中 18 份没有完成全部题目。数据只说明受访者的使用情况，不能代表所有高校学生。`;

const SAMPLE_EN = `It was found that AI writing tools may improve editing efficiency. This study delves into a pivotal realm and provides robust, comprehensive, and valuable insights.

The survey received 126 responses, but 18 respondents did not complete every question. These data describe only the participating students and should not be generalized to all universities.`;

const ANALYSIS_MAX_CODEPOINTS = 120000;

const strategies = [
  { id: "conservative", zh: "保守", en: "Conservative", zhHint: "每处最多 1 个候选", enHint: "Up to 1 candidate per issue", multiplier: 1 },
  { id: "balanced", zh: "平衡", en: "Balanced", zhHint: "每处最多 2 个候选", enHint: "Up to 2 candidates per issue", multiplier: 1 },
  { id: "deep", zh: "深度", en: "Deep", zhHint: "每处最多 3 个候选", enHint: "Up to 3 candidates per issue", multiplier: 1.5 },
];

const REWRITE_STEPS = [
  { key: "queued", zh: "安全排队", en: "Queued" },
  { key: "locating", zh: "定位可改段落", en: "Locate target passages" },
  { key: "rewriting", zh: "生成改写候选", en: "Generate alternatives" },
  { key: "checking", zh: "核验事实与引文", en: "Check facts and citations" },
  { key: "finalizing", zh: "复核表达风险", en: "Review expression risks" },
];

function rewriteProgressState(progress, isEnglish) {
  const steps = REWRITE_STEPS;
  const total = Math.max(0, Number(progress?.total || 0));
  const done = Math.max(0, Math.min(total, Number(progress?.done || 0)));
  const phase = progress?.phase || "preparing";
  const step = phase === "rewriting" && total && done >= total ? "checking"
    : phase === "preparing" ? "locating" : phase;
  const activeIndex = Math.max(0, steps.findIndex((item) => item.key === step));
  const title = ({
    queued: isEnglish ? "Queued safely; the rewrite will start when capacity is available" : "任务已安全排队，将在有处理名额时自动开始",
    locating: isEnglish ? "Reading the manuscript and locating editable passages" : "正在梳理文稿，定位可改写段落",
    rewriting: isEnglish ? "Generating and verifying paragraph-level rewrites" : "正在逐段生成并筛选改写候选",
    checking: isEnglish ? "Checking facts, citations, and argument boundaries" : "正在核对事实、引文与论证边界",
    finalizing: isEnglish ? "Re-running the expression-risk analysis on the revised text" : "正在重新分析改写稿，复核表达风险",
  })[step] || (isEnglish ? "Preparing the rewrite" : "正在准备改写任务");
  return { activeIndex, title, total, done, steps };
}

function StatusDot({ online = true }) {
  return <span className={`rt-status-dot ${online ? "is-green" : "is-red"}`} aria-hidden="true" />;
}

function noticeText(notice) {
  return typeof notice === "string" ? notice : notice?.text || "";
}

function formatExpiry(timestamp, isEnglish) {
  if (!timestamp) return isEnglish ? "No expiry" : "长期有效";
  return new Intl.DateTimeFormat(isEnglish ? "en" : "zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(new Date(timestamp * 1000));
}

function severityLabel(value, isEnglish) {
  const map = {
    high: isEnglish ? "High" : "重点",
    medium: isEnglish ? "Medium" : "中等",
    low: isEnglish ? "Low" : "提示",
  };
  return map[value] || (isEnglish ? "Review" : "复核");
}

const FINDING_NAMES_EN = {
  A1: "False contrast",
  A2: "Dramatic fragments",
  A3: "Aphoristic abstraction",
  A4: "Run-up introduction",
  A5: "Unprompted defense",
  B6: "Forced rule of three",
  B7: "Repeated sentence openings",
  B8: "Dash used as a catch-all link",
  B9: "Stacked qualifiers",
  B10: "Coined compound",
  B11: "Passive or missing agent",
  C12: "Vague high-frequency wording",
  C13: "Inflated significance",
  C14: "Vague relationship",
  C15: "Inflated closing clause",
  C16: "Promotional wording",
  C17: "Unverifiable authority claim",
  C18: "Avoiding plain copulas",
  D19: "Stray bold markup",
  D20: "Decorative heading",
  D21: "Inconsistent Chinese punctuation",
  E22: "Customer-service tone",
  E23: "Repeated disclaimers or filler",
  E24: "Opening repeats the title",
  E25: "Editing-process residue",
  F26: "Stacked attributive clauses",
  F27: "Nominalized verb phrase",
  F28: "Stacked passive constructions",
  F29: "Four-character parallelism",
  F30: "Generic background opener",
  F31: "Formulaic closing",
};

const FINDING_REASONS_EN = {
  A1: "The contrast may use emphasis in place of new information.",
  B6: "A three-part list is not inherently wrong; revise it only when the items are repetitive, vague, or present merely for rhythm.",
  B9: "Several qualifiers at the same level can blur the intended strength of the claim.",
  C12: "The phrase is not evidence of authorship, but it may be vague, repetitive, or more elaborate than the underlying claim.",
  C17: "The sentence invokes experts or research without a source the reader can verify.",
  F30: "A generic background opener may add no independent time or causal information.",
  "EN-S01": "A three-part list can be legitimate academic prose. A revision should preserve each listed item and its research meaning.",
  "EN-S11": "An agentless passive opener can obscure who made the finding.",
  "EN-V-T1": "This phrase is frequently overused in formulaic academic prose; prefer a more direct term when the meaning stays the same.",
  "EN-V-T2": "This phrase can sound generic or inflated. Replace it only when a more precise expression preserves the claim.",
};

const PLAN_NAMES_EN = {
  "免费体验": "Free experience",
  "小额包": "Small pack",
  "小字数包": "Small pack",
  "论文包": "Paper pack",
  "大论文包": "Large paper pack",
  "学生月卡": "Student 30-day pass",
  "高频月卡": "Frequent-use 30-day pass",
};

function hasCjk(value) {
  return /[\u3400-\u9fff]/.test(String(value || ""));
}

function findingName(finding, isEnglish) {
  const value = finding?.name || finding?.category_name || finding?.pattern_id || "";
  if (!isEnglish) return value;
  return FINDING_NAMES_EN[finding?.pattern_id] || value;
}

function findingReason(finding, isEnglish) {
  const value = finding?.reason || finding?.suggestion || "";
  if (!isEnglish || !hasCjk(value)) return value;
  return FINDING_REASONS_EN[finding?.pattern_id]
    || "This expression may benefit from a contextual revision that preserves facts, citations, technical terms, and the intended strength of the claim.";
}

function localizedPlanName(value, isEnglish) {
  return isEnglish ? (PLAN_NAMES_EN[value] || value) : value;
}

function localizedWorkspaceName(value, isEnglish) {
  if (isEnglish && value === "粘贴的文稿") return "Pasted manuscript";
  if (!isEnglish && value === "Pasted manuscript") return "粘贴的文稿";
  return value;
}

function localizedGuardDetail(value, isEnglish, status) {
  if (status === "review") {
    return isEnglish
      ? (value && !hasCjk(value) ? value : "Check the revised wording against facts, citations, terms, and intended meaning.")
      : (value || "请对照原稿，核对修改后的事实、引文、术语和原意。");
  }
  if (!isEnglish || !value) return value;
  if (value === "事实一致") return "Facts consistent";
  return hasCjk(value) ? "The fact, number, citation, and scope checks passed. Review the comparison before export." : value;
}

function localizedWorkbenchMessage(value, isEnglish) {
  if (!value) return value;
  if (isEnglish) {
    const rewrite = value.match(/^保真改写完成：采纳 (\d+) \/ (\d+) 个候选。请逐项复核后再导出。$/);
    if (rewrite) return `Rewrite complete: ${rewrite[1]} of ${rewrite[2]} candidates accepted. Review every change before export.`;
    const analysis = value.match(/^分析完成：发现 (\d+) 个可核对问题。$/);
    if (analysis) return `Analysis complete: ${analysis[1]} reviewable findings.`;
    if (value === "已完成安全清理，请在导出前复核当前稿。") return "Safe cleanup applied. Review the current manuscript before export.";
    if (value === "没有可安全自动修改的内容。") return "No deterministic cleanup was applicable.";
    if (value === "DOCX 已导出。") return "DOCX export created.";
  }
  return value;
}

function pollDelay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function codePointLength(value) {
  return Array.from(String(value || "")).length;
}

export function DashboardPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const { billing, config, loading, error } = usePlatform();
  const current = restoreWorkspace();
  const [documents, setDocuments] = useState([]);
  const [unsavedDrafts, setUnsavedDrafts] = useState([]);
  const [documentError, setDocumentError] = useState("");
  const hasDocument = Boolean(current.source);
  useEffect(() => {
    getApi("/api/documents").then((result) => setDocuments(result.documents || []))
      .catch((nextError) => setDocumentError(nextError.message));
    setUnsavedDrafts(getUnsavedDrafts());
  }, []);
  const openDocument = async (id) => {
    setDocumentError("");
    try { await openWorkspace(id); navigate("/app/workbench"); }
    catch (nextError) { setDocumentError(nextError.message); }
  };

  return (
    <div className="rt-page rt-dashboard-page">
      <section className="rt-dashboard-hero">
        <div>
          <span className="rt-kicker">{isEnglish ? "RIGHTTHESIS WORKSPACE" : "RIGHTTHESIS 写作工作台"}</span>
          <h1>{isEnglish ? "Reduce mechanical AI patterns without losing your argument." : "降低机械化 AI 表达，不牺牲你的论证。"}</h1>
          <p>{isEnglish
            ? "Diagnose Chinese, English, or mixed manuscripts, then review every proposed change against facts, citations, and intent."
            : "支持中文、英文与中英混排；从结构化诊断到逐项审阅，始终守住事实、引文和原意。"}</p>
        </div>
        <button className="rt-button rt-button-primary rt-hero-action" onClick={() => navigate("/app/new")}>
          <Plus weight="bold" /> {isEnglish ? "New document" : "新建文档"}
        </button>
      </section>

      {error && <div className="rt-live-banner is-warn"><WarningCircle weight="fill" /> {error}</div>}

      <section className="rt-metric-strip" aria-label={isEnglish ? "Live account overview" : "实时账户概览"}>
        <div className="rt-metric-cell is-yellow">
          <span>{isEnglish ? "Available quota" : "可用额度"}</span>
          <strong>{loading ? "—" : Number(billing?.balance || 0).toLocaleString()} <small>{isEnglish ? "credits" : "点额度"}</small></strong>
          <em>{localizedPlanName(billing?.plan_name, isEnglish) || (isEnglish ? "Loading entitlement" : "正在读取权益")}</em>
        </div>
        <div className="rt-metric-cell">
          <span>{isEnglish ? "Per-job limit" : "单次上限"}</span>
          <strong>{loading ? "—" : Number(billing?.max_chars_per_job || 0).toLocaleString()} <small>{isEnglish ? "text units" : "正文单位"}</small></strong>
          <em>{isEnglish ? "1 English word or Han character = 1 text unit; deep reserves credits at 1.5× that count. A separate 120,000-character text-size cap also applies." : "1 个英文词或汉字 = 1 正文单位；深度按正文单位数的 1.5 倍预占额度。正文另受 12 万字符上限约束。"}</em>
        </div>
        <div className="rt-metric-cell">
          <span>{isEnglish ? "Current manuscript" : "当前稿件"}</span>
          <strong>{hasDocument ? billableChars(current.current || current.source).toLocaleString() : "0"} <small>{hasDocument ? billableUnitLabel(current.current || current.source, isEnglish) : (isEnglish ? "text units" : "正文单位")}</small></strong>
          <em>{hasDocument ? current.name : (isEnglish ? "No document in this session" : "本次会话尚无文稿")}</em>
        </div>
        <div className="rt-metric-cell is-service">
          <span>{isEnglish ? "AI rewrite service" : "AI 改写服务"}</span>
          <strong><StatusDot online={Boolean(config?.llm_configured)} />{config?.llm_configured ? (isEnglish ? "Ready" : "已就绪") : (isEnglish ? "Unavailable" : "暂不可用")}</strong>
          <em>{isEnglish ? "Platform managed—no key setup" : "平台统一配置，无需用户提供 Key"}</em>
        </div>
      </section>

      <div className="rt-dashboard-grid">
        <section className="rt-board rt-project-board">
          <header className="rt-section-heading">
            <div><span className="rt-section-index">01</span><h2>{isEnglish ? "Saved manuscripts" : "已保存文稿"}</h2></div>
          </header>
          {documentError && <div className="rt-live-banner is-warn" role="alert">{documentError}</div>}
          {unsavedDrafts.length > 0 && <div className="rt-live-banner is-warn" role="status">{isEnglish ? "Unsynced browser drafts need attention:" : "以下浏览器待同步稿需要处理："} {unsavedDrafts.map((item) => <button key={item.id} className="rt-button" onClick={() => openDocument(item.id)}>{item.name}</button>)}</div>}
          {documents.length ? (
            documents.map((item) => <button key={item.id} className="rt-project-row" onClick={() => openDocument(item.id)}>
              <span className="rt-file-tile is-green">{item.kind === "pdf" ? <FilePdf weight="bold" /> : <FileDoc weight="bold" />}</span>
              <span className="rt-project-copy"><strong>{localizedWorkspaceName(item.name, isEnglish)}</strong><small>{Number(item.current_units ?? item.current_chars ?? 0).toLocaleString()} {item.current_units != null ? (isEnglish ? "text units" : "正文单位") : (isEnglish ? "non-whitespace characters" : "非空白字符")} · {new Date(item.updated_at * 1000).toLocaleString()}</small></span>
              <span className="rt-status-label is-green">{item.last_job_id ? (isEnglish ? "Has task" : "有改写任务") : (isEnglish ? "Saved" : "已保存")}</span>
              <ArrowRight weight="bold" />
            </button>)
          ) : (
            <div className="rt-live-empty">
              <FolderOpen size={34} />
              <strong>{isEnglish ? "No manuscript has been imported" : "还没有导入文稿"}</strong>
              <p>{isEnglish ? "Import a manuscript to save its source and edits to this account." : "导入后，原稿和修改稿会保存到当前账户。"}</p>
              <button className="rt-button" onClick={() => navigate("/app/new")}>{isEnglish ? "Import a manuscript" : "导入文稿"}</button>
            </div>
          )}
        </section>
        <aside className="rt-dashboard-aside">
          <section className="rt-note-card is-blue">
            <span className="rt-note-stamp">VERIFIABLE FLOW</span>
            <h2>{isEnglish ? <>A more human voice,<br />with evidence intact.</> : <>降低 AI 生成感，<br />同时保留证据。</>}</h2>
            <ol>
              <li><span>1</span>{isEnglish ? "Free bilingual diagnosis" : "免费中英文诊断"}</li>
              <li><span>2</span>{isEnglish ? "Fact-anchor guard" : "事实锚点守卫"}</li>
              <li><span>3</span>{isEnglish ? "Check revisions and evidence before export" : "导出前核对修改与证据"}</li>
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}

export function NewDocumentPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const { billing, config } = usePlatform();
  const [method, setMethod] = useState("paste");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const busy = status === "uploading" || status === "analyzing";
  const canContinue = method === "paste" ? Boolean(text.trim()) : Boolean(file);

  const selectFile = (nextFile) => {
    setError("");
    setStatus("idle");
    if (!nextFile) return;
    const extension = nextFile.name.split(".").pop()?.toLowerCase();
    if (!["txt", "docx", "pdf"].includes(extension)) {
      setFile(null);
      setError(isEnglish ? "Use TXT, DOCX, or PDF. Legacy .doc files are not supported." : "请选择 TXT、DOCX 或 PDF；暂不支持旧版 .doc。" );
      return;
    }
    if (nextFile.size > 20 * 1024 * 1024) {
      setFile(null);
      setError(isEnglish ? "The file exceeds the 20 MB limit." : "文件超过 20 MB 上限。" );
      return;
    }
    setFile(nextFile);
    setMethod("upload");
  };

  const startAnalysis = async () => {
    if (!canContinue || busy) return;
    setError("");
    try {
      let source = text;
      let document = null;
      const createdLabel = new Date().toLocaleString(isEnglish ? "en-GB" : "zh-CN", { hour12: false })
        .replaceAll("/", "-").replaceAll(":", "-");
      let name = `${isEnglish ? "Pasted manuscript" : "粘贴的文稿"} · ${createdLabel}`;
      let kind = "text";
      let notices = [];
      if (method === "upload" && file) {
        name = file.name;
        kind = file.name.split(".").pop().toLowerCase();
        if (kind === "txt") {
          setStatus("uploading");
          source = await file.text();
        } else {
          setStatus("uploading");
          const data = await fileToBase64(file);
          const extracted = await postApi(kind === "pdf" ? "/api/pdf/extract" : "/api/docx/extract", { file: data });
          source = extracted.text;
          notices = extracted.notices || [];
          document = { name, kind, data, meta: extracted.meta || {} };
        }
      }
      if (!source.trim()) throw new Error(isEnglish ? "The manuscript is empty." : "文稿内容为空。" );
      if (codePointLength(source) > ANALYSIS_MAX_CODEPOINTS) {
        throw new Error(isEnglish
          ? `This manuscript exceeds the ${ANALYSIS_MAX_CODEPOINTS.toLocaleString()}-character analysis limit. Split it by chapter; nothing was truncated or submitted.`
          : `正文超过 ${ANALYSIS_MAX_CODEPOINTS.toLocaleString()} 字诊断上限，请按章节拆分；本次未截断、未提交。`);
      }
      setStatus("analyzing");
      const report = await postApi("/api/v1/analyze", { text: source });
      report.notices = [...notices, ...(report.notices || [])];
      await createWorkspace({ name, kind, source, current: report.text || source, report, document, notices: report.notices });
      setStatus("done");
      navigate("/app/workbench");
    } catch (nextError) {
      setStatus("error");
      setError(nextError.message || (isEnglish ? "Import failed." : "导入失败。"));
    }
  };

  return (
    <div className="rt-page rt-new-page">
      <section className="rt-page-intro">
        <div>
          <button className="rt-back-link" onClick={() => navigate("/app")}>{isEnglish ? "← Back" : "← 返回"}</button>
          <span className="rt-kicker">NEW DOCUMENT / IMPORT</span>
          <h1>{isEnglish ? "Start with the complete original." : "先把原稿完整交给我们。"}</h1>
          <p>{isEnglish ? "Chinese, English, and mixed manuscripts are supported. Diagnosis never rewrites your text." : "支持中文、英文及中英混排；诊断不会改写原文。"}</p>
        </div>
        <div className="rt-import-credit">
          <span>{isEnglish ? "Available quota" : "可用额度"}</span>
          <strong>{Number(billing?.balance || 0).toLocaleString()} {isEnglish ? "credits" : "点额度"}</strong>
          <small>{config?.llm_configured ? (isEnglish ? "Rewrite service ready" : "改写服务已就绪") : (isEnglish ? "Free diagnosis is still available" : "仍可使用免费诊断")}</small>
        </div>
      </section>

      <div className="rt-import-layout">
        <section className="rt-board rt-import-board">
          <header className="rt-import-header">
            <div className="rt-import-tabs" role="group" aria-label={isEnglish ? "Import method" : "导入方式"}>
              <button type="button" aria-pressed={method === "paste"} className={method === "paste" ? "is-active" : ""} onClick={() => setMethod("paste")}><NotePencil weight="bold" /> {isEnglish ? "Paste text" : "粘贴文本"}</button>
              <button type="button" aria-pressed={method === "upload"} className={method === "upload" ? "is-active" : ""} onClick={() => setMethod("upload")}><UploadSimple weight="bold" /> {isEnglish ? "Upload file" : "上传文档"}</button>
            </div>
            <span className="rt-service-pill"><StatusDot online /> {isEnglish ? "Bilingual analysis ready" : "双语分析已就绪"}</span>
          </header>
          {method === "paste" ? (
            <div className="rt-paste-pane">
              <div className="rt-editor-ruler"><span>DOCUMENT / 01</span><span>{billableChars(text).toLocaleString()} {billableUnitLabel(text, isEnglish)}</span></div>
              <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={isEnglish ? "Paste a paper, chapter, or abstract…" : "粘贴论文、章节或研究摘要……"} />
              {!text && <div className="rt-live-samples">
                <button onClick={() => setText(SAMPLE_ZH)}>中文示例</button>
                <button onClick={() => setText(SAMPLE_EN)}>English sample</button>
              </div>}
            </div>
          ) : (
            <label className={`rt-drop-zone ${dragActive ? "is-dragging" : ""} ${error ? "has-error" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragActive(false)} onDrop={(event) => { event.preventDefault(); setDragActive(false); selectFile(event.dataTransfer.files?.[0]); }}>
              <input type="file" accept=".txt,.docx,.pdf" onChange={(event) => { selectFile(event.target.files?.[0]); event.target.value = ""; }} />
              <span className="rt-upload-icon">{file?.name.toLowerCase().endsWith(".pdf") ? <FilePdf weight="bold" /> : <CloudArrowUp weight="bold" />}</span>
              <h2>{file ? file.name : (isEnglish ? "Drag a manuscript here" : "拖拽文稿到这里")}</h2>
              <p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : (isEnglish ? "TXT / DOCX / PDF · Up to 20 MB" : "TXT / DOCX / PDF · 最大 20 MB")}</p>
              <span className="rt-button"><UploadSimple weight="bold" /> {isEnglish ? "Choose file" : "选择文件"}</span>
            </label>
          )}
        </section>
        <aside className="rt-import-settings">
          <section className="rt-board rt-settings-card">
            <span className="rt-section-index">02</span>
            <h2>{isEnglish ? "What gets checked" : "将检查什么"}</h2>
            <div className="rt-check-list">
              {(isEnglish ? ["Mechanical phrasing", "Terminology consistency", "Argument boundaries", "Fact anchors"] : ["机械化表达", "术语一致性", "论证边界", "事实锚点"]).map((item) => <span key={item}><Check weight="bold" /> {item}</span>)}
            </div>
          </section>
          <section className="rt-privacy-note"><ShieldCheck size={26} weight="bold" /><div><strong>{isEnglish ? "Saved to your account" : "保存到当前账户"}</strong><p>{isEnglish ? "Your original and revised text are saved to your account. Keep a separate copy of important manuscripts." : "原稿与修改稿会保存到你的账户；重要文稿也请自行保留副本。"}</p></div></section>
          {error && <div className="rt-live-banner is-error" role="alert"><WarningCircle weight="fill" /> {error}</div>}
          <button className="rt-button rt-button-primary rt-analyze-button" disabled={!canContinue || busy} onClick={startAnalysis} aria-busy={busy}>
            {busy ? <CircleNotch className="rt-spin" weight="bold" /> : <Sparkle weight="bold" />}
            {status === "uploading" ? (isEnglish ? "Extracting text…" : "正在提取正文…") : status === "analyzing" ? (isEnglish ? "Analyzing…" : "正在分析…") : (isEnglish ? "Start free analysis" : "开始免费分析")}
            {!busy && <ArrowRight weight="bold" />}
          </button>
        </aside>
      </div>
    </div>
  );
}

export function WorkbenchPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const { billing, config, refreshBilling } = usePlatform();
  const initial = restoreWorkspace();
  const [source] = useState(initial.source || "");
  const [current, setCurrent] = useState(initial.current || initial.source || "");
  const [report, setReport] = useState(initial.report || null);
  const [staleReport, setStaleReport] = useState(null);
  const [mode, setMode] = useState("conservative");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingFinding, setPendingFinding] = useState(null);
  const [jobProgress, setJobProgress] = useState(null);
  const [activeFinding, setActiveFinding] = useState(0);
  const [guard, setGuard] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [focusMode, setFocusMode] = useState(false);
  const saveStatus = useWorkspaceSaveStatus();
  const currentRef = useRef(current);
  const revisionRef = useRef(0);
  const currentEditorRef = useRef(null);
  const confirmDialogRef = useRef(null);
  const cancelConfirmRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => { currentRef.current = current; }, [current]);
  useEffect(() => {
    if (!confirmOpen) return undefined;
    previousFocusRef.current = document.activeElement;
    const appRoot = document.getElementById("root");
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden");
    const previouslyInert = appRoot?.hasAttribute("inert") ?? false;
    const previousBodyOverflow = document.body.style.overflow;
    cancelConfirmRef.current?.focus();
    appRoot?.setAttribute("inert", "");
    appRoot?.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "hidden";

    const handleKeydown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setConfirmOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = confirmDialogRef.current?.querySelectorAll(
        "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!confirmDialogRef.current?.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeydown);
    return () => {
      window.removeEventListener("keydown", handleKeydown);
      if (appRoot) {
        if (!previouslyInert) appRoot.removeAttribute("inert");
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      document.body.style.overflow = previousBodyOverflow;
      previousFocusRef.current?.focus?.();
    };
  }, [confirmOpen]);
  useEffect(() => {
    const jobId = initial.last_job_id;
    if (!jobId) return undefined;
    let cancelled = false;
    const reconnect = async () => {
      try {
        let job = await getApi(`/api/job/${encodeURIComponent(jobId)}`);
        if (job.state === "running" || job.state === "queued") {
          setBusy("rewrite");
          setMessage(isEnglish ? "Reconnected to the saved rewrite task." : "已重新连接到保存的改写任务。 ");
          while (!cancelled && (job.state === "running" || job.state === "queued")) {
            setJobProgress({ done: Number(job.done || 0), total: Number(job.total || 0), phase: job.phase || "rewriting" });
            await pollDelay(1200);
            job = await getApi(`/api/job/${encodeURIComponent(jobId)}`);
          }
        }
        if (cancelled) return;
        if (job.state === "error") {
          setError(job.error || (isEnglish ? "The saved task was interrupted." : "已保存任务中断。"));
          return;
        }
        if (job.state === "done" && job.result) {
          const result = job.result;
          const original = result.before?.text;
          if (result.text === currentRef.current) {
            const changed = typeof original === "string" && original !== result.text;
            setLastResult(changed ? { kind: "rewrite", beforeText: original, afterText: result.text, result } : null);
            setGuard(changed ? result.guard || null : null);
            if (changed) setMessage(isEnglish ? "Recovered the completed modification and current draft." : "已恢复完成的修改和当前稿。");
            else setError((isEnglish ? result.no_change_reason_en : result.no_change_reason)
              || (isEnglish ? "The saved task made no safe change to the current draft." : "已保存任务未能对当前稿完成安全修改。"));
          } else if (original && snapshotMatchesDraft(original, 0, currentRef.current, revisionRef.current)) {
            revisionRef.current += 1;
            setCurrent(result.text);
            setReport(result.after || null);
            setStaleReport(null);
            setLastResult({ kind: "rewrite", beforeText: original, afterText: result.text, result });
            setGuard(result.guard || null);
            updateWorkspace({ current: result.text, report: result.after || null });
            await saveWorkspaceNow();
            setMessage(isEnglish ? "Recovered and saved the completed rewrite." : "已恢复并保存完成的改写。 ");
          } else {
            setMessage(isEnglish ? "A completed result is in task history. Your newer draft was not overwritten." : "任务历史中可查看已完成结果；较新的当前稿没有被覆盖。 ");
          }
          await refreshBilling().catch(() => null);
        }
      } catch (nextError) {
        if (!cancelled) setError(nextError.message);
      } finally {
        if (!cancelled) { setBusy(""); setJobProgress(null); }
      }
    };
    reconnect();
    return () => { cancelled = true; };
  }, []);
  const selected = strategies.find((item) => item.id === mode);
  const chars = billableChars(current);
  const estimated = Math.ceil(chars * selected.multiplier);
  const findings = report?.findings || [];
  const visibleReport = report || staleReport;
  const visibleFindings = visibleReport?.findings || [];
  const reportIsStale = !report && Boolean(staleReport);
  const nextAction = workbenchAction(report);
  const safeCleanupCount = deterministicCleanupCount(report);
  const visibleCleanupCount = deterministicCleanupCount(visibleReport);
  const anchorCounts = visibleReport?.anchors?.counts || {};
  const anchorsTotal = Object.values(anchorCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  const allowed = billing?.allowed_strengths || ["conservative"];
  const jobLimit = Number(billing?.max_chars_per_job || 0);
  const overJobLimit = jobLimit ? Math.max(0, chars - jobLimit) : 0;
  const withinJobLimit = !overJobLimit;
  const hasEnoughBalance = billing?.balance == null || estimated <= Number(billing.balance);
  const canRewrite = canStartModification({
    report, llmConfigured: config?.llm_configured, allowedStrengths: allowed,
    mode, withinJobLimit, hasEnoughBalance,
  });
  const canReviewRewrite = (finding) => Boolean(canRewrite && report?.findings?.includes(finding)
    && reviewTargetFromFinding(finding));
  const changeRows = useMemo(() => lastResult
    ? changedPassages(lastResult.beforeText, lastResult.afterText)
    : [], [lastResult]);

  const commit = (nextCurrent, nextReport, extra = {}) => {
    currentRef.current = nextCurrent;
    setCurrent(nextCurrent);
    setReport(nextReport);
    setStaleReport(null);
    setActiveFinding(0);
    setPendingFinding(null);
    updateWorkspace({ current: nextCurrent, report: nextReport, ...extra });
  };

  const editCurrent = (nextCurrent) => {
    revisionRef.current += 1;
    currentRef.current = nextCurrent;
    setCurrent(nextCurrent);
    if (report) setStaleReport(report);
    setReport(null);
    setActiveFinding(0);
    setConfirmOpen(false);
    setPendingFinding(null);
    setGuard(null);
    setLastResult(null);
    setMessage("");
    setError("");
    updateWorkspace({ current: nextCurrent, report: null });
  };

  const analyze = async () => {
    if (!current.trim() || busy) return;
    if (codePointLength(current) > ANALYSIS_MAX_CODEPOINTS) {
      setError(isEnglish
        ? `This manuscript exceeds the ${ANALYSIS_MAX_CODEPOINTS.toLocaleString()}-character analysis limit. Split it by chapter; nothing was truncated or submitted.`
        : `正文超过 ${ANALYSIS_MAX_CODEPOINTS.toLocaleString()} 字诊断上限，请按章节拆分；本次未截断、未提交。`);
      return;
    }
    const snapshot = current;
    const revision = revisionRef.current;
    setBusy("analyze"); setError(""); setMessage("");
    try {
      const nextReport = await postApi("/api/v1/analyze", { text: snapshot });
      if (revision !== revisionRef.current || snapshot !== currentRef.current) {
        setMessage(isEnglish ? "The manuscript changed during analysis. Run it again for the current text." : "分析期间正文已变化，请对当前版本重新分析。" );
        return;
      }
      if ((nextReport.text || snapshot) !== snapshot) setLastResult(null);
      commit(nextReport.text || snapshot, nextReport);
      const analysisPassed = Number(nextReport.summary?.checks || 0) > 0
        && nextReport.summary?.status === "clear"
        && Number(nextReport.summary?.findings || 0) === 0;
      setMessage(analysisPassed
        ? (isEnglish ? "RightThesis in-app check found no obvious templated phrasing; no third-party test was run." : "RightThesis 站内复查未发现明显模板化表达；未进行第三方检测。")
        : (isEnglish ? `Analysis complete: ${nextReport.summary?.findings || 0} reviewable findings.` : `分析完成：发现 ${nextReport.summary?.findings || 0} 个可核对问题。`));
    } catch (nextError) { setError(nextError.message); }
    finally { setBusy(""); }
  };

  const safeFix = async () => {
    if (!report || !safeCleanupCount || busy) return;
    if (codePointLength(current) > ANALYSIS_MAX_CODEPOINTS) {
      setError(isEnglish
        ? `This manuscript exceeds the ${ANALYSIS_MAX_CODEPOINTS.toLocaleString()}-character cleanup limit. Split it by chapter; nothing was truncated or submitted.`
        : `正文超过 ${ANALYSIS_MAX_CODEPOINTS.toLocaleString()} 字清理上限，请按章节拆分；本次未截断、未提交。`);
      return;
    }
    const snapshot = current;
    const revision = revisionRef.current;
    setBusy("safe"); setError(""); setMessage("");
    try {
      const result = await postApi("/api/v1/autofix", { text: snapshot });
      if (revision !== revisionRef.current || snapshot !== currentRef.current) return;
      revisionRef.current += 1;
      setGuard(result.guard || null);
      commit(result.text, result.after || report);
      setLastResult(result.changed && result.text !== snapshot
        ? { kind: "safe", beforeText: snapshot, afterText: result.text, result }
        : null);
      setMessage(result.changed
        ? (isEnglish ? "Safe cleanup applied. Review the highlighted changes and verify the draft before export." : "已完成安全清理。请核对下方标亮的前后修改，并在导出前人工复核。")
        : (isEnglish ? "No deterministic cleanup was applicable; the draft is unchanged." : "没有可安全自动修改的内容，当前稿保持原样。"));
    } catch (nextError) { setError(nextError.message); }
    finally { setBusy(""); }
  };

  const runRewrite = async (reviewFinding = null) => {
    const reviewTarget = reviewTargetFromFinding(reviewFinding);
    if (busy || !canRewrite || (reviewFinding && !canReviewRewrite(reviewFinding))) return;
    const snapshot = current;
    const revision = revisionRef.current;
    setConfirmOpen(false); setBusy("rewrite"); setError(""); setMessage(""); setGuard(null); setLastResult(null); setJobProgress({ done: 0, total: 0, phase: "preparing" });
    try {
      await saveWorkspaceNow();
      if (!snapshotMatchesDraft(snapshot, revision, currentRef.current, revisionRef.current)) {
        setMessage(isEnglish
          ? "The draft changed while saving, so no rewrite job was submitted. Analyze the latest text before trying again."
          : "保存期间当前稿发生变化，本次未提交改写任务。请重新分析最新正文后再试。");
        return;
      }
      const started = await postApi("/api/v1/rewrite-jobs", {
        text: snapshot, strength: mode, request_id: requestId("rewrite"), manuscript_id: getWorkspace().id,
        ...(reviewTarget ? { review_target: reviewTarget } : {}),
      });
      const jobId = started.job || started.job_id;
      if (!jobId) throw new Error(isEnglish ? "The service did not return a job ID." : "服务未返回任务编号。" );
      updateWorkspace({ last_job_id: jobId });
      // A queued task must remain reconnectable if the tab closes mid-run.
      // Keep polling even if this save fails; the local backup still has ID.
      await saveWorkspaceNow().catch(() => null);
      let failures = 0;
      const pollingDeadline = Date.now() + 2 * 60 * 60 * 1000;
      for (;;) {
        if (Date.now() > pollingDeadline) {
          throw new Error(isEnglish
            ? "This rewrite is taking longer than two hours. The queued or running server job may still continue; check the task list and credit ledger before retrying."
            : "本次改写已超过两小时，服务端排队或运行中的任务可能仍会继续；重试前请先核对任务和额度账本。");
        }
        await pollDelay(850);
        let job;
        try { job = await getApi(`/api/job/${encodeURIComponent(jobId)}`); failures = 0; }
        catch (pollError) {
          failures += 1;
          if (failures > 6) throw pollError;
          await pollDelay(Math.min(4000, failures * 600));
          continue;
        }
        setJobProgress({ done: Number(job.done || 0), total: Number(job.total || 0), phase: job.phase || "rewriting" });
        if (job.state === "error") throw new Error(job.error || (isEnglish ? "Rewrite failed." : "改写失败。"));
        if (job.state !== "done") continue;
        // Keep the actual final analysis step perceptible even when it and
        // billing complete between two polling ticks.
        if (Number(job.result?.n_chunks || 0) > 0) {
          setJobProgress({ done: Number(job.total || 0), total: Number(job.total || 0), phase: "finalizing" });
          await pollDelay(1400);
        }
        const result = job.result;
        if (typeof result?.text !== "string") throw new Error(isEnglish ? "The task returned no revised text." : "任务没有返回修改后的正文。");
        if (!snapshotMatchesDraft(snapshot, revision, currentRef.current, revisionRef.current)) {
          setError(isEnglish
            ? "The manuscript changed while this task was running, so the result was not applied. Review task history before retrying."
            : "任务运行期间正文已变化，结果未覆盖当前稿；重试前请先核对任务历史。");
          await refreshBilling().catch(() => null);
          break;
        }
        const changed = result.text !== snapshot;
        revisionRef.current += 1;
        setGuard(changed ? result.guard || null : null);
        commit(result.text, result.after || report);
        setLastResult(changed
          ? { kind: "rewrite", beforeText: snapshot, afterText: result.text, result }
          : null);
        await saveWorkspaceNow();
        await refreshBilling().catch(() => null);
        const targeted = Number(result.n_chunks || 0);
        const accepted = Number(result.n_accepted || 0);
        const calls = Number(result.billing?.llm_requests || 0);
        const checkPassed = Number(result.after?.summary?.checks || 0) > 0
          && result.after?.summary?.status === "clear"
          && Number(result.after?.summary?.findings || 0) === 0
          && result.guard?.status === "passed";
        if (!changed) {
          const reason = reviewTarget
            ? (isEnglish ? result.review_target?.reason_en || result.review_target?.reason : result.review_target?.reason)
            : (isEnglish ? result.no_change_reason_en || result.no_change_reason : result.no_change_reason);
          setError(reviewTarget
            ? (isEnglish
              ? `No safe change was accepted for this finding. ${reason || "The current draft is unchanged; any reserved quota was returned."}`
              : `这条线索未能采纳安全修改。${reason || "当前稿未变化；已退回预占额度。"}`)
            : reason
              ? (isEnglish ? `The current draft is unchanged. ${reason}` : `当前稿未变化。${reason}`)
              : targeted === 0
              ? (isEnglish ? "No safe passage was revised. The current draft is unchanged; reserved quota was returned." : "没有段落完成安全修改，当前稿未变化；已退回预占额度。")
              : (isEnglish ? `All ${targeted} revision candidates were rejected by the safeguards. The current draft is unchanged; reserved quota was returned.` : `${targeted} 处修改候选均未通过守卫，当前稿未变化；已退回预占额度。`));
        } else if (reviewTarget && result.review_target?.status === "unchanged") {
          const reason = isEnglish ? result.review_target?.reason_en : result.review_target?.reason;
          setMessage(isEnglish
            ? `The draft changed, but the selected finding was preserved. ${reason || "Check the highlighted changes."}`
            : `当前稿已有修改，但选中的线索保留原文。${reason || "请核对标亮的改动。"}`);
        } else if (reviewTarget) {
          const reason = isEnglish ? result.review_target?.reason_en : result.review_target?.reason;
          setMessage(isEnglish
            ? `The selected finding was revised. ${reason || ""}`
            : `已修改选中的诊断线索。${reason || ""}`);
        } else if (checkPassed) {
          setMessage(isEnglish
            ? `Revised draft saved. The in-app check found no obvious templated phrasing and the fact guard passed. ${calls} model requests.`
            : `修改稿已保存。站内复查未发现明显模板化表达，事实守卫已通过。模型调用 ${calls} 次。`);
        } else if (accepted) {
          setMessage(isEnglish
            ? `Revised draft saved. ${accepted} of ${targeted} paragraph candidates accepted; ${calls} model requests.`
            : `修改稿已保存，采纳 ${accepted} / ${targeted} 处段落候选；模型调用 ${calls} 次。`);
        } else {
          setMessage(isEnglish ? `Revised draft saved. ${calls} model requests.` : `修改稿已保存；模型调用 ${calls} 次。`);
        }
        break;
      }
    } catch (nextError) {
      setError(isEnglish && nextError.data?.code === "text_density_limit"
        ? (nextError.data.error_en || nextError.message)
        : nextError.message);
      await refreshBilling().catch(() => null);
    } finally { setBusy(""); setJobProgress(null); }
  };

  const exportDocument = async () => {
    const doc = getWorkspace().document;
    if (!doc || doc.kind !== "docx") {
      setError(isEnglish ? "The original DOCX is unavailable. Download the final TXT instead." : "原始 DOCX 不可用；请下载最终 TXT。" );
      return;
    }
    const snapshot = current;
    const revision = revisionRef.current;
    setBusy("export"); setError(""); setMessage("");
    try {
      await saveWorkspaceNow();
      if (!snapshotMatchesDraft(snapshot, revision, currentRef.current, revisionRef.current)) {
        setMessage(isEnglish ? "The draft changed while saving. Export it again to include the latest edits." : "保存期间当前稿已修改，请重新导出以包含最新内容。");
        return;
      }
      const result = await postApi("/api/docx/export", { file: doc.data, text: snapshot });
      downloadBase64(result.file, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", doc.name.replace(/\.docx$/i, "") + "-RightThesis.docx");
      if (snapshotMatchesDraft(snapshot, revision, currentRef.current, revisionRef.current)) {
        setMessage(isEnglish ? "DOCX export created." : "DOCX 已导出。" );
      } else {
        setError(isEnglish ? "The downloaded DOCX contains the draft from when export started. Export again to include your latest edits." : "刚下载的 DOCX 是导出开始时的稿件；当前稿在导出期间已修改，请重新导出以包含最新内容。");
      }
    } catch (nextError) { setError(nextError.message); }
    finally { setBusy(""); }
  };

  const downloadText = (value = current, tag = "RightThesis") => {
    const name = (getWorkspace().name || "RightThesis").replace(/\.(docx|pdf|txt)$/i, "");
    const url = URL.createObjectURL(new Blob([value], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${name}-${tag}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage(isEnglish ? "Final text downloaded." : "已下载最终文本。 ");
  };

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(current);
      setMessage(isEnglish ? "Final text copied." : "已复制最终文本。 ");
    } catch {
      setError(isEnglish ? "Copy failed; download the TXT file instead." : "复制失败，请改用下载 TXT。 ");
    }
  };

  const selectFinding = (index) => {
    setActiveFinding(index);
    const item = findings[index];
    const editor = currentEditorRef.current;
    if (!item || !editor) return;
    const start = Array.from(current).slice(0, Number(item.start || 0)).join("").length;
    const end = Array.from(current).slice(0, Number(item.end || 0)).join("").length;
    editor.focus();
    editor.setSelectionRange(start, end);
    editor.scrollIntoView({ block: "nearest" });
  };

  if (!source) {
    return <div className="rt-page"><div className="rt-board rt-live-empty rt-live-empty--page"><FileText size={42} /><h1>{isEnglish ? "No manuscript is open" : "当前没有打开的文稿"}</h1><p>{isEnglish ? "Import or paste a manuscript to start a bilingual diagnosis." : "请先导入或粘贴文稿，再开始中英文诊断。"}</p><button className="rt-button rt-button-primary" onClick={() => navigate("/app/new")}>{isEnglish ? "New document" : "新建文档"}</button></div></div>;
  }

  const progressView = busy === "rewrite" ? rewriteProgressState(jobProgress, isEnglish) : null;

  return (
    <div className={`rt-page rt-workbench-page rt-live-workbench ${focusMode ? "is-focus-mode" : ""}`}>
      <div className="rt-document-bar">
        <div>
          <button type="button" className="rt-doc-back" onClick={() => navigate("/app")}>
            <ArrowLeft size={18} weight="bold" aria-hidden="true" />
            {isEnglish ? "Back to documents" : "返回文档"}
          </button>
          <span className="rt-doc-name">{localizedWorkspaceName(getWorkspace().name, isEnglish)}</span>
          <span className="rt-doc-meta">{chars.toLocaleString()} {billableUnitLabel(current, isEnglish)}</span>
        </div>
        <div className="rt-document-actions">
          <span className={`rt-save-status is-${saveStatus.state}`} role="status">{saveStatus.state === "saved" ? (isEnglish ? "Saved" : "已保存") : saveStatus.state === "saving" ? (isEnglish ? "Saving…" : "正在保存…") : (isEnglish ? "Save failed" : "保存失败")}</span>
          <button className="rt-button" onClick={() => setFocusMode((value) => !value)}>{focusMode ? (isEnglish ? "Compare view" : "对照视图") : (isEnglish ? "Focus view" : "专注阅读")}</button>
          <button className="rt-button" onClick={copyText}>{isEnglish ? "Copy text" : "复制全文"}</button>
          <button className="rt-button" onClick={() => downloadText()}><DownloadSimple weight="bold" />{isEnglish ? "Download TXT" : "下载 TXT"}</button>
          {getWorkspace().document?.data && <button className="rt-button" onClick={() => { const doc = getWorkspace().document; downloadBase64(doc.data, doc.kind === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document", doc.name); }}>{isEnglish ? "Original file" : "下载原文件"}</button>}
          {getWorkspace().document?.kind === "docx" && <button className="rt-button rt-button-primary" onClick={exportDocument} disabled={Boolean(busy)}><DownloadSimple weight="bold" />{isEnglish ? "Export DOCX" : "导出 DOCX"}</button>}
        </div>
      </div>
      {saveStatus.state === "error" && <div className="rt-live-banner is-error" role="alert">{saveStatus.error} <button className="rt-button" onClick={() => downloadText(getUnsavedLocalBackup() || current, isEnglish ? "unsaved-backup" : "未同步备份")}>{isEnglish ? "Download backup" : "下载备份"}</button></div>}

      {(message || error) && <div className={`rt-live-banner ${error ? "is-error" : "is-success"}`} role={error ? "alert" : "status"}>{error ? <WarningCircle weight="fill" /> : <CheckCircle weight="fill" />}{error || localizedWorkbenchMessage(message, isEnglish)}</div>}
      {lastResult && changeRows.length > 0 && <div className="rt-live-banner is-warn rt-post-modification-review" role="status"><WarningCircle weight="fill" /><span><strong>{isEnglish ? "Modification complete · human review required" : "修改已完成 · 请进行人工审核"}</strong>{isEnglish ? "Compare the highlighted before/after passages below, then check facts, citations, terms, and intended meaning before using the draft." : "请查看下方标亮的修改前后对照，并在使用修改稿前核对事实、引文、术语和原意。"}</span></div>}
      {report?.notices?.map((notice, index) => <div className="rt-live-banner is-warn" key={`${noticeText(notice)}-${index}`}><WarningCircle weight="fill" />{noticeText(notice)}</div>)}

      {progressView && <section className="rt-rewrite-progress" role="status" aria-live="polite" aria-label={isEnglish ? "Rewrite progress" : "改写进度"}>
        <div className="rt-rewrite-progress-head">
          <span className="rt-rewrite-progress-kicker"><StatusDot /> RIGHTTHESIS / {progressView.activeIndex === 3 ? (isEnglish ? "FINAL REVIEW" : "结果复核") : (isEnglish ? "LIVE EDITING" : "实时处理")}</span>
          <span className="rt-rewrite-progress-count">{progressView.total ? `${progressView.done.toLocaleString()} / ${progressView.total.toLocaleString()} ${isEnglish ? "passages" : "处段落"}` : (isEnglish ? "Locating passages" : "正在定位段落")}</span>
        </div>
        <h2>{progressView.title}</h2>
        <div className={`rt-rewrite-progress-track ${progressView.total ? "" : "is-indeterminate"}`} role="progressbar" aria-valuemin={0} aria-valuemax={progressView.total || undefined} aria-valuenow={progressView.total ? progressView.done : undefined} aria-label={isEnglish ? "Paragraphs processed" : "已处理段落"}>
          <span style={progressView.total ? { width: `${progressView.done / progressView.total * 100}%` } : undefined} />
        </div>
        <div className="rt-rewrite-progress-steps">{progressView.steps.map((step, index) => <div key={step.key} className={index < progressView.activeIndex ? "is-done" : index === progressView.activeIndex ? "is-active" : ""}><span>{index < progressView.activeIndex ? <Check weight="bold" /> : String(index + 1).padStart(2, "0")}</span><strong>{isEnglish ? step.en : step.zh}</strong></div>)}</div>
        <p>{isEnglish ? "RightThesis checks the revised text again and updates its in-app findings. Third-party detector results are not included." : "RightThesis 会重新诊断改写稿并更新站内问题结果；此处不包含第三方检测结果。"}</p>
      </section>}

      <div className="rt-live-editor-grid">
        <section className="rt-paper-panel rt-live-editor-panel">
          <header><div><strong>{isEnglish ? "Original manuscript" : "原始稿件"}</strong><span>{isEnglish ? "Read-only source" : "只读原稿"}</span></div><small>{billableChars(source).toLocaleString()} {billableUnitLabel(source, isEnglish)}</small></header>
          <textarea value={source} readOnly aria-label={isEnglish ? "Original manuscript" : "原始稿件"} />
        </section>
        <section className="rt-paper-panel is-current rt-live-editor-panel">
          <header><div><strong>{isEnglish ? "Current manuscript" : "当前稿件"}</strong><span>{busy === "rewrite" ? (isEnglish ? "Rewrite in progress; editing resumes when it finishes" : "改写进行中，完成后可继续编辑") : (isEnglish ? "Editable—changes require a new analysis" : "可编辑；修改后需重新分析")}</span></div><small className={overJobLimit ? "is-over-limit" : ""}>{chars.toLocaleString()}{jobLimit ? ` / ${jobLimit.toLocaleString()}` : ""} {billableUnitLabel(current, isEnglish)}</small></header>
          <div id="rt-current-edit-hint" className={`rt-live-edit-hint ${overJobLimit ? "is-over-limit" : ""}`} role={overJobLimit ? "status" : undefined}>
            <span>{isEnglish ? "Each English word, number group, or Chinese character counts as one text unit. Spaces and punctuation do not count; other visible characters count individually. Deep rewrite reserves credits at 1.5× the text-unit count. A separate 120,000-character text-size cap applies." : "每个英文词、数字组或汉字各计 1 个正文单位；空白和标点不计，其他可见字符逐个计数。深度改写按正文单位数的 1.5 倍预占额度；正文另受 12 万字符上限约束。"}</span>
            {overJobLimit > 0 && <strong>{isEnglish ? `${overJobLimit.toLocaleString()} text units over the per-task rewrite limit. Edit or trim the current draft below; the original stays available.` : `超出单次改写上限 ${overJobLimit.toLocaleString()} 正文单位。可在下方直接删减当前稿，原稿仍保留。`}</strong>}
          </div>
          <textarea ref={currentEditorRef} value={current} readOnly={busy === "rewrite"} onChange={(event) => editCurrent(event.target.value)} aria-label={isEnglish ? "Current manuscript editor" : "当前稿件编辑器"} aria-describedby="rt-current-edit-hint" />
        </section>
        <aside className="rt-findings-panel rt-live-findings">
          <header><div><strong>{isEnglish ? "Diagnosis and evidence" : "诊断与证据"}</strong><small>{reportIsStale ? (isEnglish ? "Previous report · outdated" : "上次报告 · 已过期") : report ? (isEnglish ? `${report.summary?.checks || 0} checks completed` : `已完成 ${report.summary?.checks || 0} 项检查`) : (isEnglish ? "Run analysis for current text" : "请分析当前正文")}</small></div></header>
          {reportIsStale && <div className="rt-live-stale-report" role="status"><WarningCircle weight="fill" />{isEnglish ? "The draft changed. These findings are for reference only; analyze again to refresh locations and rewrite options." : "当前稿已修改。旧线索仅供参考；重新分析后才能更新定位及改写选项。"}</div>}
          <div className="rt-finding-metrics">
            <div><strong>{visibleReport?.summary?.findings || 0}</strong><span>{isEnglish ? "Findings" : "诊断线索"}</span></div>
            <div className="is-peach"><strong>{visibleReport?.summary?.review_items || 0}</strong><span>{isEnglish ? "Contextual findings" : "上下文线索"}</span></div>
            <div className="is-yellow"><strong>{visibleCleanupCount}</strong><span>{isEnglish ? "Safe fixes" : "安全清理"}</span></div>
            <div className="is-green"><strong>{anchorsTotal}</strong><span>{isEnglish ? "Fact anchors" : "事实锚点"}</span></div>
          </div>
          <div className="rt-live-finding-list">
            {visibleFindings.length ? visibleFindings.map((finding, index) => {
              const key = `${finding.pattern_id}-${finding.start}-${index}`;
              const canTargetFinding = Boolean(reviewTargetFromFinding(finding));
              const contents = <>
                <span className={`rt-live-severity is-${finding.severity || "medium"}`}>{severityLabel(finding.severity, isEnglish)}</span>
                <strong>{findingName(finding, isEnglish)}</strong>
                <p>{findingReason(finding, isEnglish)}</p>
                {finding.handling === "review" && <small className="rt-live-review-tag">{reportIsStale ? (isEnglish ? "Previous report · location unavailable" : "上次报告 · 需重新定位") : (isEnglish ? "The revision will preserve verified facts and citations" : "修改时会核对事实与引文")}</small>}
                {finding.matched && <code>{finding.matched}</code>}
              </>;
              return reportIsStale
                ? <article key={key} className="is-stale">{contents}</article>
                : canTargetFinding
                  ? <article key={key} className={`rt-finding-actionable ${activeFinding === index ? "is-active" : ""}`}>
                    <button type="button" className="rt-finding-select" onClick={() => selectFinding(index)}>{contents}</button>
                    <button type="button" className="rt-finding-auto" disabled={!canReviewRewrite(finding) || Boolean(busy)} onClick={() => { setActiveFinding(index); setPendingFinding(finding); setConfirmOpen(true); }}><Sparkle weight="bold" />{isEnglish ? "Modify this finding" : "修改此项"}</button>
                  </article>
                : <button key={key} className={activeFinding === index ? "is-active" : ""} onClick={() => selectFinding(index)}>{contents}</button>;
            }) : <div className="rt-live-empty is-compact"><ShieldCheck size={30} /><strong>{visibleReport ? (isEnglish ? "No obvious templated phrasing found" : "未发现明显模板化表达") : (isEnglish ? "Analysis is free" : "分析不消耗改写额度")}</strong></div>}
          </div>
          {guard && <div className={`rt-guard-note ${guard.status === "passed" ? "is-passed" : ""}`}><ShieldCheck weight="fill" /><span><strong>{guard.status === "review" ? (isEnglish ? "Human review required" : "需人工审核") : (isEnglish ? "Fact guard" : "事实守卫")}</strong><small>{localizedGuardDetail(guard.detail, isEnglish, guard.status) || (isEnglish ? "Review the comparison before export." : "请在导出前复核对照。")}</small></span></div>}
        </aside>
      </div>

      {lastResult && changeRows.length > 0 && <section className="rt-review-changes rt-board" aria-label={isEnglish ? "Highlighted before and after comparison" : "前后标亮对照"}>
        <header><div><span className="rt-kicker">CHANGE REVIEW</span><h2>{lastResult.kind === "safe" ? (isEnglish ? "Review safe-cleanup changes" : "核对安全清理的修改") : (isEnglish ? "Review each accepted change" : "逐处核对采纳的修改")}</h2><p>{isEnglish ? "Removed text is marked red; added text is marked green. Review facts, citations, and meaning yourself." : "浅红标出删去的文字，浅绿标出新增的文字；请人工复核事实、引文和原意。"}</p></div><button className="rt-button" onClick={() => downloadText(lastResult.afterText, isEnglish ? "compared-result" : "对照结果")}>{isEnglish ? "Download compared result" : "下载对照结果"}</button></header>
        <div className="rt-review-change-list">
          {changeRows.map((item, index) => {
            const compared = diffChange(item.original, item.rewritten);
            return <article key={`${index}-${item.original.slice(0, 12)}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div><small>{isEnglish ? "Before" : "修改前"}</small><p><ChangeHighlights segments={compared.before} /></p></div>
              <div><small>{isEnglish ? "After" : "修改后"}</small><p><ChangeHighlights segments={compared.after} /></p></div>
            </article>;
          })}
        </div>
      </section>}

      <section className="rt-action-dock rt-live-action-dock">
        {!withinJobLimit && <div className="rt-live-limit-note"><WarningCircle weight="fill" /><span>{isEnglish ? `The current draft is ${overJobLimit.toLocaleString()} text units over your ${jobLimit.toLocaleString()}-unit rewrite limit. Trim it in the editor to continue.` : `当前稿超出 ${jobLimit.toLocaleString()} 正文单位的单次改写上限 ${overJobLimit.toLocaleString()} 单位，请在当前稿中删减后再改写。`}</span><button type="button" onClick={() => currentEditorRef.current?.focus()}>{isEnglish ? "Edit current draft" : "编辑当前稿"}</button></div>}
        {nextAction === "rewrite" && !hasEnoughBalance && <div className="rt-live-limit-note"><WarningCircle weight="fill" />{isEnglish ? `This strategy needs about ${estimated.toLocaleString()} credits, but the current balance is ${Number(billing?.balance || 0).toLocaleString()} credits.` : `当前策略预计预占 ${estimated.toLocaleString()} 点额度，当前可用 ${Number(billing?.balance || 0).toLocaleString()} 点额度。`}</div>}
        <button className="rt-button" onClick={analyze} disabled={Boolean(busy)}>{busy === "analyze" ? <CircleNotch className="rt-spin" /> : <Sparkle weight="bold" />}{isEnglish ? "Analyze current text" : "分析当前正文"}</button>
        <button className="rt-safe-clean" onClick={safeFix} disabled={!report || !safeCleanupCount || Boolean(busy)}><ShieldCheck weight="bold" /><span><strong>{isEnglish ? "Safe cleanup" : "安全清理"}</strong><small>{isEnglish ? "Deterministic fixes only" : "仅确定性修改"}</small></span></button>
        <div className="rt-mode-switch" role="group" aria-label={isEnglish ? "Rewrite mode" : "改写模式"}>
          {strategies.map((item) => <button key={item.id} type="button" className={mode === item.id ? "is-active" : ""} aria-pressed={mode === item.id} disabled={Boolean(busy) || !allowed.includes(item.id)} onClick={() => setMode(item.id)}><strong>{isEnglish ? `${item.en} rewrite` : `${item.zh}改写`}</strong><small>{isEnglish ? item.enHint : item.zhHint}</small></button>)}
        </div>
        <button className="rt-rewrite-action" disabled={!canRewrite || Boolean(busy)} onClick={() => { setPendingFinding(null); setConfirmOpen(true); }}>
          {busy === "rewrite" ? <CircleNotch className="rt-spin" weight="bold" /> : <FileText weight="bold" />}
          <span><strong>{busy === "rewrite" ? (isEnglish ? "Modifying…" : "正在修改…") : (isEnglish ? "Modify current draft" : "修改当前稿")}</strong><small>{jobProgress?.total ? `${jobProgress.done} / ${jobProgress.total}` : nextAction === "analyze" ? (isEnglish ? "Analyze the current draft first" : "请先分析当前稿") : (isEnglish ? `${estimated.toLocaleString()} credits estimated` : `预计预占 ${estimated.toLocaleString()} 点额度`)}</small></span><ArrowRight weight="bold" />
        </button>
      </section>

      {confirmOpen && createPortal(<div className="rt-confirm-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setConfirmOpen(false); }}><section ref={confirmDialogRef} className="rt-rewrite-confirm" role="dialog" aria-modal="true" aria-labelledby="rt-live-confirm-title" aria-describedby="rt-live-confirm-description">
        <span className="rt-confirm-kicker">RUN CHECK / {isEnglish ? "USAGE PREVIEW" : "扣减预览"}</span>
        <h2 id="rt-live-confirm-title">{pendingFinding ? (isEnglish ? "Modify this finding?" : "确认修改这条线索？") : (isEnglish ? `Run a ${selected.en.toLowerCase()} modification?` : `确认按${selected.zh}策略修改当前稿？`)}</h2>
        <p id="rt-live-confirm-description">{pendingFinding
          ? (isEnglish ? "The service will revise the selected finding with fact and citation safeguards. Deterministic edits may be free; model edits reserve quota." : "服务会针对所选线索尝试修改，并核对事实与引文。确定性修改可能免费，模型修改会预占额度。")
          : (isEnglish ? "The service will revise the current draft regardless of the diagnosis outcome. Changes that fail fact and citation safeguards will not be accepted; unused reserved quota is returned." : "服务会根据当前稿进行修改，不受诊断结果类型限制。未通过事实与引文守卫的候选不会采纳；未使用的预占额度会退回。")}</p>
        <div className="rt-confirm-metrics"><div><span>{isEnglish ? "Billable text" : "计费文本"}</span><strong>{chars.toLocaleString()} {billableUnitLabel(current, isEnglish)}</strong></div><div><span>{isEnglish ? "Rewrite mode" : "改写模式"}</span><strong>{isEnglish ? selected.en : `${selected.zh}改写`}</strong></div><div className="is-highlight"><span>{isEnglish ? "Maximum reservation" : "最多预占额度"}</span><strong>{estimated.toLocaleString()} {isEnglish ? "credits" : "点额度"}</strong></div></div>
        <div className="rt-confirm-balance"><span>{isEnglish ? "Available now" : "当前可用"}</span><strong>{Number(billing?.balance || 0).toLocaleString()} {isEnglish ? "credits" : "点额度"}</strong></div>
        <div className="rt-confirm-actions"><button ref={cancelConfirmRef} className="rt-button" onClick={() => setConfirmOpen(false)}>{isEnglish ? "Cancel" : "取消"}</button><button className="rt-button rt-button-primary" onClick={() => runRewrite(pendingFinding)} disabled={!canRewrite || Boolean(busy)}>{isEnglish ? "Confirm and start" : "确认并开始"}<ArrowRight weight="bold" /></button></div>
      </section></div>, document.body)}
    </div>
  );
}

export function VersionsPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const current = restoreWorkspace();
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getApi("/api/jobs").then((data) => setJobs((data.jobs || []).filter((job) => job.manuscript_id === current.id)))
      .catch((nextError) => setError(nextError.message));
    if (current.id) getApi(`/api/documents/${encodeURIComponent(current.id)}/versions`)
      .then((data) => setVersions(data.versions || []))
      .catch((nextError) => setError(nextError.message));
  }, [current.id]);
  const restoreOriginal = async () => {
    try {
      updateWorkspace({ current: current.source, report: null });
      await saveWorkspaceNow();
      navigate("/app/workbench");
    } catch (nextError) { setError(nextError.message); }
  };
  const openJob = async (id) => {
    try {
      const result = await getApi(`/api/job/${encodeURIComponent(id)}`);
      setSelectedJob({ ...result, id });
      setError("");
    } catch (nextError) { setError(nextError.message); }
  };
  const openVersion = async (revision) => {
    try {
      const data = await getApi(`/api/documents/${encodeURIComponent(current.id)}/versions/${revision}`);
      setSelectedVersion(data.version);
      setError("");
    } catch (nextError) { setError(nextError.message); }
  };
  const restoreVersion = async () => {
    if (!selectedVersion || !current.id) return;
    try {
      updateWorkspace({ current: selectedVersion.text, report: null });
      await saveWorkspaceNow();
      navigate("/app/workbench");
    } catch (nextError) { setError(nextError.message); }
  };
  const downloadJob = () => {
    if (!selectedJob?.result?.text) return;
    const url = URL.createObjectURL(new Blob([selectedJob.result.text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(current.name || "RightThesis").replace(/\.(docx|pdf|txt)$/i, "")}-任务结果.txt`;
    document.body.appendChild(link);
    link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="rt-page rt-versions-page">
    <section className="rt-page-intro"><div><button className="rt-back-link" onClick={() => navigate("/app/workbench")}>{isEnglish ? "← Back to manuscript" : "← 返回文稿"}</button><span className="rt-kicker">VERSIONS / SAVED</span><h1>{isEnglish ? "Review saved drafts." : "查看已保存的稿件版本。"}</h1><p>{isEnglish ? "Text changes saved to your account create recoverable snapshots. Older manuscripts include the source and last saved draft; intermediate edits before this feature cannot be recovered." : "之后每次保存正文修改都会留存可恢复快照。旧文稿仅补录原稿和当时的当前稿；此前中间修改无法补回。"}</p></div></section>
    <section className="rt-board rt-live-version-board">
      {error && <div className="rt-live-banner is-error" role="alert">{error}</div>}
      {current.source ? <>
        <div className="rt-live-version-row"><span>V1</span><div><strong>{isEnglish ? "Original import" : "原始导入"}</strong><small>{billableChars(current.source).toLocaleString()} {billableUnitLabel(current.source, isEnglish)}</small></div><button className="rt-button" onClick={restoreOriginal}>{isEnglish ? "Restore original" : "恢复原稿"}</button></div>
        {versions.map((version) => <div className="rt-live-version-row" key={version.revision}><span>V{version.revision}</span><div><strong>{isEnglish ? "Saved draft" : "已保存稿"}</strong><small>{new Date(version.created_at * 1000).toLocaleString()} · {Number(version.units ?? version.chars ?? 0).toLocaleString()} {version.units != null ? (isEnglish ? "text units" : "正文单位") : (isEnglish ? "non-whitespace characters" : "非空白字符")}</small></div><button className="rt-button" onClick={() => openVersion(version.revision)}>{isEnglish ? "Review" : "查看"}</button></div>)}
        {selectedVersion && <div className="rt-job-result-detail"><strong>V{selectedVersion.revision} · {isEnglish ? "Saved text" : "已保存正文"}</strong><p className="rt-version-preview">{selectedVersion.text.slice(0, 1200)}{selectedVersion.text.length > 1200 ? "…" : ""}</p><button className="rt-button rt-button-primary" onClick={restoreVersion}>{isEnglish ? "Restore this version" : "恢复此版本"}</button></div>}
      </> : <div className="rt-live-empty"><FolderOpen size={34} /><strong>{isEnglish ? "No saved versions" : "暂无已保存版本"}</strong></div>}
    </section>
    <section className="rt-board rt-live-version-board rt-job-history">
      <header className="rt-section-heading"><h2>{isEnglish ? "Saved rewrite tasks" : "已保存改写任务"}</h2></header>
      {jobs.length ? jobs.map((job) => <button key={job.id} className="rt-project-row" onClick={() => openJob(job.id)}>
        <span className="rt-file-tile is-green"><ClockCounterClockwise weight="bold" /></span>
        <span className="rt-project-copy"><strong>{job.state === "done" ? (isEnglish ? "Completed rewrite" : "已完成改写") : job.state === "running" ? (isEnglish ? "Running" : "正在改写") : (isEnglish ? "Interrupted or failed" : "已中断或失败")}</strong><small>{new Date(job.t0 * 1000).toLocaleString()} · {job.id}</small></span>
        <ArrowRight weight="bold" />
      </button>) : <div className="rt-live-empty is-compact">{isEnglish ? "No rewrite task for this manuscript yet." : "这篇文稿暂无改写任务。"}</div>}
      {selectedJob && <div className="rt-job-result-detail">
        <strong>{selectedJob.state === "done" ? (isEnglish ? "Usable result saved" : "可用结果已保存") : selectedJob.error || (isEnglish ? "Task in progress" : "任务正在进行")}</strong>
        {selectedJob.result?.text && <><p>{isEnglish ? "The complete result is available even after a server restart." : "服务重启后仍可下载这份完整结果。"}</p><button className="rt-button rt-button-primary" onClick={downloadJob}><DownloadSimple weight="bold" />{isEnglish ? "Download task result" : "下载任务结果"}</button></>}
      </div>}
    </section>
  </div>;
}
