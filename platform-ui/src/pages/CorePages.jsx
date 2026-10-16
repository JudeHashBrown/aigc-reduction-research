import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowCounterClockwise,
  ArrowRight,
  CaretDown,
  Check,
  CheckCircle,
  CircleNotch,
  ClockCounterClockwise,
  CloudArrowUp,
  DownloadSimple,
  FileDoc,
  FilePdf,
  FileText,
  FolderOpen,
  MagnifyingGlass,
  NotePencil,
  Plus,
  ShieldCheck,
  Sparkle,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";

import "@fontsource-variable/inter-tight";
import "@fontsource/noto-serif-sc/400.css";
import "@fontsource/noto-serif-sc/600.css";
import { useLocale } from "../locale.jsx";
import "./core-pages.css";

const projects = [
  {
    title: "教育公平研究.docx",
    meta: { zh: "12,841 字 · 今天 14:26", en: "12,841 chars · Today, 14:26" },
    status: "ready",
    statusLabel: { zh: "修改建议已就绪", en: "Suggestions ready" },
    tone: "blue",
    issues: 28,
    route: "/app/documents/rt-014",
  },
  {
    title: "Digital labor and platform governance",
    meta: { zh: "8,926 words · 昨天 21:08", en: "8,926 words · Yesterday, 21:08" },
    status: "review",
    statusLabel: { zh: "等待审阅", en: "Awaiting review" },
    tone: "peach",
    issues: 16,
    route: "/app/documents/rt-014",
  },
  {
    title: "智慧城市的数据伦理.pdf",
    meta: { zh: "6,402 字 · 10 月 8 日", en: "6,402 chars · Oct 8" },
    status: "exported",
    statusLabel: { zh: "已导出", en: "Exported" },
    tone: "green",
    issues: 11,
    route: "/app/documents/rt-014/versions",
  },
  {
    title: "农村教育数字化转型",
    meta: { zh: "3,718 字 · 10 月 6 日", en: "3,718 chars · Oct 6" },
    status: "draft",
    statusLabel: { zh: "草稿", en: "Draft" },
    tone: "plain",
    issues: 0,
    route: "/app/new",
  },
];

const findings = [
  {
    id: 1,
    title: { zh: "证据范围", en: "Evidence coverage" },
    count: { zh: "3 条提示", en: "3 notes" },
    body: {
      zh: "部分结论的证据范围较窄，建议补充中西部地区的最新数据或权威报告。",
      en: "Some conclusions draw on a narrow evidence base. Consider adding recent data or authoritative reports covering central and western China.",
    },
    refs: [
      ["OECD (2021). Education at a Glance.", "support"],
      ["陈等 (2019). 中国教育资源配置研究.", "partial"],
      ["教育部 (2022). 全国教育事业发展统计公报.", "support"],
    ],
  },
  {
    id: 2,
    title: { zh: "因果边界", en: "Causal boundaries" },
    count: { zh: "2 条提示", en: "2 notes" },
    body: {
      zh: "当前表述存在因果推断过度的风险，建议区分相关性与因果性。",
      en: "The current wording may overstate causal inference. Distinguish correlation from causation.",
    },
    refs: [],
  },
  {
    id: 3,
    title: { zh: "术语一致性", en: "Terminology consistency" },
    count: { zh: "3 条提示", en: "3 notes" },
    body: {
      zh: "“教育公平 / 教育机会公平 / 教育平等”等术语在全文中使用不一致。",
      en: "The terms “教育公平 / 教育机会公平 / 教育平等” are used inconsistently throughout the document.",
    },
    refs: [],
  },
];

const versionRows = [
  {
    id: "v4",
    name: { zh: "平衡改写", en: "Balanced rewrite" },
    time: { zh: "今天 14:26", en: "Today, 14:26" },
    detail: { zh: "28 处修改 · 16 个核心事实保留", en: "28 changes · 16 core facts preserved" },
    tone: "blue",
  },
  {
    id: "v3",
    name: { zh: "安全清理", en: "Safe cleanup" },
    time: { zh: "今天 14:19", en: "Today, 14:19" },
    detail: { zh: "9 处本地规则修复", en: "9 local-rule fixes" },
    tone: "yellow",
  },
  {
    id: "v2",
    name: { zh: "深度改写", en: "Deep rewrite" },
    time: { zh: "昨天 22:03", en: "Yesterday, 22:03" },
    detail: { zh: "41 处修改 · 未导出", en: "41 changes · Not exported" },
    tone: "peach",
  },
  {
    id: "v1",
    name: { zh: "原始导入", en: "Original import" },
    time: { zh: "昨天 21:54", en: "Yesterday, 21:54" },
    detail: { zh: "原始文档 · 12,841 字", en: "Original document · 12,841 chars" },
    tone: "plain",
  },
];

const rewriteStrategies = [
  {
    id: "conservative",
    label: { zh: "保守", en: "Conservative" },
    detail: { zh: "更稳定，改动较小", en: "More stable, fewer changes" },
    multiplier: 1,
  },
  {
    id: "balanced",
    label: { zh: "平衡", en: "Balanced" },
    detail: { zh: "推荐，兼顾表达与修改", en: "Recommended balance" },
    multiplier: 1.2,
  },
  {
    id: "deep",
    label: { zh: "深度", en: "Deep" },
    detail: { zh: "更充分的优化建议", en: "More extensive suggestions" },
    multiplier: 1.5,
  },
];

const projectFilters = [
  { id: "all", label: { zh: "全部", en: "All" } },
  { id: "active", label: { zh: "进行中", en: "In progress" } },
  { id: "completed", label: { zh: "已完成", en: "Completed" } },
];

const findingTabs = [
  { id: "findings", label: { zh: "关键发现", en: "Key findings" } },
  { id: "changes", label: { zh: "修改列表", en: "Change list" } },
  { id: "references", label: { zh: "参考文献", en: "References" } },
  { id: "checks", label: { zh: "全部检查项", en: "All checks" } },
];

const languageOptions = [
  { id: "auto", label: { zh: "自动识别", en: "Auto-detect" } },
  { id: "zh", label: { zh: "中文", en: "Chinese" } },
  { id: "en", label: { zh: "English", en: "English" } },
  { id: "mixed", label: { zh: "中英混排", en: "Chinese–English mixed" } },
];

const versionStats = {
  v4: { changes: "28", facts: "16 / 16", terms: "03", citations: "00" },
  v3: { changes: "9", facts: "16 / 16", terms: "01", citations: "00" },
  v2: { changes: "41", facts: "16 / 16", terms: "03", citations: "00" },
};

const importFileRules = {
  extensions: ["doc", "docx", "pdf", "txt"],
  maxBytes: 20 * 1024 * 1024,
};

function formatFileSize(bytes = 0) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024)).toLocaleString()} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validateImportFile(file) {
  if (!file) return { ok: false, code: "missing" };
  const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
  if (!importFileRules.extensions.includes(extension)) {
    return { ok: false, code: "format" };
  }
  if (file.size > importFileRules.maxBytes) {
    return { ok: false, code: "size", size: formatFileSize(file.size) };
  }
  return { ok: true, extension };
}

function importErrorMessage(error, isEnglish) {
  if (!error) return "";
  if (error.code === "missing") {
    return isEnglish ? "No file was detected. Please choose a file again." : "未检测到文件，请重新选择。";
  }
  if (error.code === "format") {
    return isEnglish
      ? "This file type is not supported. Choose a DOC, DOCX, PDF, or TXT file."
      : "不支持该文件格式。请选择 DOC、DOCX、PDF 或 TXT 文件。";
  }
  if (error.code === "size") {
    return isEnglish
      ? `This file is ${error.size}, which exceeds the 20 MB limit.`
      : `文件大小为 ${error.size}，已超过 20 MB 上限。`;
  }
  if (error.code === "scan") {
    return isEnglish
      ? "Scanned PDF parsing failed: no editable text was detected. Run OCR first, or use a DOCX or TXT version."
      : "扫描型 PDF 解析失败：未识别到可编辑正文。请先进行 OCR，或改用 DOCX / TXT 版本。";
  }
  return "";
}

function SoftToast({ children }) {
  return (
    <div className="rt-toast" role="status">
      <CheckCircle weight="fill" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

function StatusDot({ color = "green" }) {
  return <span className={`rt-status-dot is-${color}`} aria-hidden="true" />;
}

export function DashboardPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const languageKey = isEnglish ? "en" : "zh";
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  const visibleProjects = useMemo(() => {
    return projects.filter((project) => {
      const matchesQuery = project.title.toLowerCase().includes(query.toLowerCase());
      const matchesFilter =
        filter === "all" ||
        (filter === "active" && project.status !== "exported") ||
        (filter === "completed" && project.status === "exported");
      return matchesQuery && matchesFilter;
    });
  }, [filter, query]);

  return (
    <div className="rt-page rt-dashboard-page">
      <section className="rt-dashboard-hero">
        <div>
          <span className="rt-kicker">{isEnglish ? "TODAY’S WRITING DESK" : "今天的写作工作台"}</span>
          <h1>{isEnglish ? "Make your next paper sound more credible." : "下一篇论文，从更可信的表达开始。"}</h1>
          <p>{isEnglish
            ? "Go beyond sentence-level polish with transparent fact anchors, terminology, and reasons for every change."
            : "不仅优化句子，还会把事实锚点、术语和修改原因交代清楚。"}</p>
        </div>
        <button className="rt-button rt-button-primary rt-hero-action" onClick={() => navigate("/app/new")}>
          <Plus weight="bold" aria-hidden="true" />
          {isEnglish ? "New document" : "新建文档"}
        </button>
      </section>

      <section className="rt-metric-strip" aria-label={isEnglish ? "Account overview" : "账户概览"}>
        <div className="rt-metric-cell is-yellow">
          <span>{isEnglish ? "Available quota" : "可用额度"}</span>
          <strong>56,420 <small>{isEnglish ? "chars" : "字"}</small></strong>
          <em>{isEnglish ? "21 days left on monthly plan" : "月卡剩余 21 天"}</em>
        </div>
        <div className="rt-metric-cell">
          <span>{isEnglish ? "Documents this month" : "本月文档"}</span>
          <strong>06</strong>
          <em>{isEnglish ? "38,280 chars processed" : "共处理 38,280 字"}</em>
        </div>
        <div className="rt-metric-cell">
          <span>{isEnglish ? "Suggestions" : "修改建议"}</span>
          <strong>124</strong>
          <em>{isEnglish ? "91 accepted" : "91 条已采用"}</em>
        </div>
        <div className="rt-metric-cell is-service">
          <span>{isEnglish ? "AI service" : "AI 服务"}</span>
          <strong><StatusDot />{isEnglish ? "Online" : "正常"}</strong>
          <em>{isEnglish ? "Ready to use—no setup required" : "系统已配置，无需额外设置"}</em>
        </div>
      </section>

      <div className="rt-dashboard-grid">
        <section className="rt-board rt-project-board">
          <header className="rt-section-heading">
            <div>
              <span className="rt-section-index">01</span>
              <h2>{isEnglish ? "Recent documents" : "最近文档"}</h2>
            </div>
            <div className="rt-list-tools">
              <label className="rt-search-field">
                <MagnifyingGlass weight="bold" aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={isEnglish ? "Search titles" : "搜索标题"}
                  aria-label={isEnglish ? "Search documents" : "搜索文档"}
                />
              </label>
              <div className="rt-mini-tabs" role="group" aria-label={isEnglish ? "Filter documents" : "文档筛选"}>
                {projectFilters.map((item) => (
                  <button
                    key={item.id}
                    className={filter === item.id ? "is-active" : ""}
                    aria-pressed={filter === item.id}
                    onClick={() => setFilter(item.id)}
                  >
                    {item.label[languageKey]}
                  </button>
                ))}
              </div>
            </div>
          </header>

          <div className="rt-project-list">
            {visibleProjects.map((project) => (
              <button
                className="rt-project-row"
                key={project.title}
                onClick={() => navigate(project.route)}
                aria-label={isEnglish
                  ? `Open ${project.title}, ${project.statusLabel.en}`
                  : `打开${project.title}，${project.statusLabel.zh}`}
              >
                <span className={`rt-file-tile is-${project.tone}`}>
                  {project.title.endsWith(".pdf") ? <FilePdf weight="bold" /> : <FileDoc weight="bold" />}
                </span>
                <span className="rt-project-copy">
                  <strong>{project.title}</strong>
                  <small>{project.meta[languageKey]}</small>
                </span>
                <span className={`rt-status-label is-${project.tone}`}>{project.statusLabel[languageKey]}</span>
                <span className="rt-project-issue">
                  {project.issues
                    ? (isEnglish ? `${project.issues} items` : `${project.issues} 项`)
                    : (isEnglish ? "Continue editing" : "继续编辑")}
                </span>
                <ArrowRight weight="bold" aria-hidden="true" />
              </button>
            ))}
            {visibleProjects.length === 0 && (
              <div className="rt-empty-row">
                <FolderOpen size={28} />
                <span>{isEnglish ? "No matching documents found" : "没有找到匹配文档"}</span>
              </div>
            )}
          </div>
        </section>

        <aside className="rt-dashboard-aside">
          <section className="rt-note-card is-blue">
            <span className="rt-note-stamp">QUICK START</span>
            <h2>{isEnglish ? <>A complete<br />faithful rewrite</> : <>一次完整的<br />保真改写</>}</h2>
            <ol>
              <li><span>1</span>{isEnglish ? "Import a document or paste text" : "导入文档或粘贴文本"}</li>
              <li><span>2</span>{isEnglish ? "Check facts, terms, and logic" : "检查事实、术语与逻辑"}</li>
              <li><span>3</span>{isEnglish ? "Review changes and export" : "对照审阅并导出"}</li>
            </ol>
            <button className="rt-text-button" onClick={() => navigate("/app/new")}>
              {isEnglish ? "Start your first document" : "开始第一篇"} <ArrowRight weight="bold" />
            </button>
          </section>
          <button className="rt-history-card" onClick={() => navigate("/app/documents/rt-014/versions")}>
            <ClockCounterClockwise size={27} weight="bold" />
            <span>
              <strong>{isEnglish ? "Version history" : "版本历史"}</strong>
              <small>{isEnglish ? "View and restore every change" : "查看与恢复所有修改"}</small>
            </span>
            <ArrowRight weight="bold" />
          </button>
        </aside>
      </div>
    </div>
  );
}

export function NewDocumentPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const languageKey = isEnglish ? "en" : "zh";
  const [method, setMethod] = useState("paste");
  const [text, setText] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [fileName, setFileName] = useState("");
  const [fileMeta, setFileMeta] = useState("");
  const [fileError, setFileError] = useState(null);
  const [status, setStatus] = useState("idle");
  const [language, setLanguage] = useState("auto");

  const canContinue = method === "paste" ? Boolean(text.trim()) : Boolean(fileName && !fileError);
  const localizedFileMeta = fileMeta === "scan"
    ? (isEnglish ? "PDF · Scanned image" : "PDF · 扫描图像")
    : fileMeta;
  const localizedFileError = importErrorMessage(fileError, isEnglish);

  const acceptFile = (file) => {
    if (!file) return;
    setMethod("upload");
    setStatus("idle");
    setFileName(file.name);
    const validation = validateImportFile(file);
    if (!validation.ok) {
      setFileMeta("");
      setFileError(validation);
      return;
    }
    setFileMeta(`${validation.extension.toUpperCase()} · ${formatFileSize(file.size)}`);
    setFileError(null);
  };

  const simulateParseFailure = () => {
    setMethod("upload");
    setStatus("idle");
    setFileName("扫描版研究论文.pdf");
    setFileMeta("scan");
    setFileError({ code: "scan" });
  };

  const startAnalysis = () => {
    if (!canContinue || status === "working") return;
    setStatus("working");
    window.setTimeout(() => setStatus("done"), 1100);
  };

  return (
    <div className="rt-page rt-new-page">
      <section className="rt-page-intro">
        <div>
          <button className="rt-back-link" onClick={() => navigate("/app")}>
            {isEnglish ? "← Back to dashboard" : "← 返回工作台"}
          </button>
          <span className="rt-kicker">{isEnglish ? "NEW DOCUMENT / IMPORT" : "新文档 / IMPORT"}</span>
          <h1>{isEnglish ? "Start with the complete original." : "先把原稿完整交给我们。"}</h1>
          <p>{isEnglish
            ? "Supports Chinese, English, and mixed-language documents. Your text will not be rewritten before analysis."
            : "支持中文、英文及中英混排；分析前不会改写原文。"}</p>
        </div>
        <div className="rt-import-credit">
          <span>{isEnglish ? "Available quota" : "可用额度"}</span>
          <strong>56,420 {isEnglish ? "chars" : "字"}</strong>
          <small>{isEnglish ? "Usage is estimated before analysis" : "本次会在分析前估算用量"}</small>
        </div>
      </section>

      <div className="rt-import-layout">
        <section className="rt-board rt-import-board">
          <header className="rt-import-header">
            <div className="rt-import-tabs" role="tablist" aria-label={isEnglish ? "Import method" : "导入方式"}>
              <button
                id="rt-import-paste-tab"
                role="tab"
                aria-selected={method === "paste"}
                aria-controls="rt-import-paste-panel"
                className={method === "paste" ? "is-active" : ""}
                onClick={() => setMethod("paste")}
              >
                <NotePencil weight="bold" /> {isEnglish ? "Paste text" : "粘贴文本"}
              </button>
              <button
                id="rt-import-upload-tab"
                role="tab"
                aria-selected={method === "upload"}
                aria-controls="rt-import-upload-panel"
                className={method === "upload" ? "is-active" : ""}
                onClick={() => setMethod("upload")}
              >
                <UploadSimple weight="bold" /> {isEnglish ? "Upload document" : "上传文档"}
              </button>
            </div>
            <span className="rt-service-pill"><StatusDot /> {isEnglish ? "AI service online" : "AI 服务正常"}</span>
          </header>

          {method === "paste" ? (
            <div
              className="rt-paste-pane"
              id="rt-import-paste-panel"
              role="tabpanel"
              aria-labelledby="rt-import-paste-tab"
            >
              <div className="rt-editor-ruler">
                <span>DOCUMENT / 01</span>
                <span>{text.length.toLocaleString()} {isEnglish ? "chars" : "字"}</span>
              </div>
              <label className="rt-sr-only" htmlFor="rt-document-text">
                {isEnglish ? "Original manuscript text" : "论文原稿内容"}
              </label>
              <textarea
                id="rt-document-text"
                aria-label={isEnglish ? "Original manuscript text" : "论文原稿内容"}
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder={isEnglish
                  ? "Paste your paper, chapter, or research abstract…\n\nWe’ll check phrasing, terminology, logical boundaries, and fact anchors without changing your conclusions."
                  : "粘贴你的论文、章节或研究摘要…\n\n我们会检查表达、术语、逻辑边界与事实锚点，但不会自行改变你的研究结论。"}
              />
              {!text && (
                <button
                  className="rt-sample-fill"
                  onClick={() => setText("教育公平是社会公平的重要基础，也是实现共同富裕的内在要求。近年来，随着我国高等教育规模的快速扩张，城乡之间、地区之间的教育资源差距依然显著。")}
                >
                  {isEnglish ? "Insert sample text" : "填入示例文本"}
                </button>
              )}
            </div>
          ) : (
            <div
              className="rt-upload-pane"
              id="rt-import-upload-panel"
              role="tabpanel"
              aria-labelledby="rt-import-upload-tab"
            >
              <label
                className={`rt-drop-zone ${dragActive ? "is-dragging" : ""} ${fileName && !fileError ? "has-file" : ""} ${fileError ? "has-error" : ""}`}
                onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragActive(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragActive(false);
                  acceptFile(event.dataTransfer.files?.[0]);
                }}
              >
                <input
                  type="file"
                  accept=".doc,.docx,.pdf,.txt"
                  aria-label={isEnglish ? "Choose a paper to import" : "选择要导入的论文文档"}
                  onChange={(event) => {
                    acceptFile(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                {fileError ? (
                  <>
                    <span className="rt-upload-icon is-error"><WarningCircle weight="bold" /></span>
                    <h2>{fileName || (isEnglish ? "File validation failed" : "文件未通过校验")}</h2>
                    {localizedFileMeta && <p>{localizedFileMeta}</p>}
                    <div className="rt-file-error" role="alert">
                      <strong>{isEnglish ? "Import failed" : "导入失败"}</strong>
                      <span>{localizedFileError}</span>
                    </div>
                    <span className="rt-button rt-button-plain">
                      <UploadSimple weight="bold" /> {isEnglish ? "Choose another file" : "重新选择"}
                    </span>
                  </>
                ) : fileName ? (
                  <>
                    <span className="rt-upload-icon is-success"><FileDoc weight="bold" /></span>
                    <h2>{fileName}</h2>
                    <p>{fileMeta} · {isEnglish ? "Ready to analyze." : "文档已就位，可以开始分析。"}</p>
                    <span className="rt-file-ready">
                      <Check weight="bold" /> {isEnglish ? "Format and size checks passed" : "格式与大小校验通过"}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="rt-upload-icon"><CloudArrowUp weight="bold" /></span>
                    <h2>{dragActive
                      ? (isEnglish ? "Drop it here to import" : "放在这里即可导入")
                      : (isEnglish ? "Drag a document here" : "拖拽文档到这里")}</h2>
                    <p>{isEnglish
                      ? "or click to choose · DOC / DOCX / PDF / TXT · Up to 20 MB"
                      : "或点击选择文件 · DOC / DOCX / PDF / TXT · 最大 20 MB"}</p>
                    <span className="rt-button rt-button-plain">
                      <UploadSimple weight="bold" /> {isEnglish ? "Choose file" : "选择文件"}
                    </span>
                  </>
                )}
              </label>
              <button className="rt-upload-simulator" type="button" onClick={simulateParseFailure}>
                <WarningCircle weight="bold" /> {isEnglish ? "Simulate scanned PDF / parse failure" : "模拟扫描 PDF / 解析失败"}
              </button>
            </div>
          )}
        </section>

        <aside className="rt-import-settings">
          <section className="rt-board rt-settings-card">
            <span className="rt-section-index">02</span>
            <h2>{isEnglish ? "Analysis settings" : "分析设置"}</h2>
            <label>
              <span>{isEnglish ? "Document language" : "文档语言"}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                {languageOptions.map((option) => (
                  <option key={option.id} value={option.id}>{option.label[languageKey]}</option>
                ))}
              </select>
            </label>
            <div className="rt-check-list">
              {(isEnglish
                ? ["Phrasing and sentence structure", "Terminology consistency", "Causal and argumentative boundaries", "Fact-anchor preservation"]
                : ["表达和句式检查", "术语一致性", "因果与论证边界", "事实锚点保留"]).map((item) => (
                <span key={item}><Check weight="bold" /> {item}</span>
              ))}
            </div>
          </section>
          <section className="rt-privacy-note">
            <ShieldCheck weight="bold" size={26} />
            <div>
              <strong>{isEnglish ? "Your original is protected" : "原稿受保护"}</strong>
              <p>{isEnglish ? "You can delete the document and its version history at any time." : "你可随时删除文档和其版本记录。"}</p>
            </div>
          </section>
          <button
            className="rt-button rt-button-primary rt-analyze-button"
            disabled={!canContinue || status === "working"}
            aria-busy={status === "working"}
            onClick={status === "done" ? () => navigate("/app/documents/rt-014") : startAnalysis}
          >
            {status === "working" && <CircleNotch className="rt-spin" weight="bold" />}
            {status === "idle" && <Sparkle weight="bold" />}
            {status === "done" && <CheckCircle weight="fill" />}
            {status === "idle"
              ? (isEnglish ? "Start analysis" : "开始分析")
              : status === "working"
                ? (isEnglish ? "Parsing structure…" : "正在解析结构…")
                : (isEnglish ? "View analysis" : "查看分析结果")}
            {status !== "working" && <ArrowRight weight="bold" />}
          </button>
          <small className="rt-cost-hint">
            {isEnglish ? "Final usage is recorded when processing completes" : "实际使用量以完成后记录为准"}
          </small>
        </aside>
      </div>
    </div>
  );
}

function StageRail({ active = 3 }) {
  const { isEnglish } = useLocale();
  const stages = isEnglish
    ? [
        ["Import", "Upload and parse document"],
        ["Analyze", "Complete · 31 checks"],
        ["Optimize", active >= 4 ? "Suggestions generated" : "Generating suggestions"],
        ["Review", active >= 4 ? "Ready to compare and export" : "Confirm and export"],
      ]
    : [
        ["导入", "上传文档并解析"],
        ["分析", "完成 · 31 项检查"],
        ["优化", active >= 4 ? "已生成修改建议" : "正在进行修改建议"],
        ["审阅", active >= 4 ? "可对照与导出" : "确认并导出"],
      ];

  return (
    <div className="rt-stage-rail" aria-label={isEnglish ? "Document processing progress" : "文档处理进度"}>
      {stages.map(([label, detail], index) => {
        const step = index + 1;
        const complete = step < active;
        const selected = step === active;
        return (
          <div
            className={`rt-stage ${complete ? "is-complete" : ""} ${selected ? "is-active" : ""}`}
            key={label}
            aria-current={selected ? "step" : undefined}
          >
            <span className="rt-stage-number">{complete ? <Check weight="bold" /> : step}</span>
            <span><strong>{label}</strong><small>{detail}</small></span>
          </div>
        );
      })}
    </div>
  );
}

function PaperLines({ revised = false }) {
  return (
    <div className="rt-paper-copy">
      <p><i>101</i>教育公平是社会公平的重要基础，也是实现</p>
      <p><i>102</i>共同富裕的内在要求。近年来，随着我国高等教</p>
      <p><i>103</i>育规模的快速扩张，城乡之间、地区之间的教育</p>
      <p><i>104</i>资源差距依然显著，{revised ? <><mark className="rt-mark-blue">尤其是</mark>在中西部地区，<mark className="rt-mark-blue">优质教</mark></> : "特别是在中西部地区，高质"}</p>
      <p className={revised ? "" : "rt-paper-highlight"}><i>105</i>{revised ? <>现有<mark className="rt-mark-blue">研究表明</mark>，家庭社会经济地位（SES）对</> : "量教育资源的可及性仍然不足。"}</p>
      <p><i>106</i>{revised ? "个体的高等教育机会具有显著影响（李明，" : "已有研究表明，家庭社会经济地位（SES）对"}</p>
      <p><i>107</i>{revised ? "2021; Zhang, 2020）。" : "个体的高等教育机会具有显著影响（李明，"}</p>
      <p><i>108</i>{revised ? <>例如，王芳（2022）通过对三省的实证研究发</> : "2021; Zhang, 2020）。"}</p>
      <p><i>109</i>{revised ? "现，家庭收入、父母受教育程度与大学入学概率" : "例如，王芳（2022）通过对三省的实证研究发"}</p>
      <p><i>110</i>{revised ? <>呈显著正相关。此外，教育资源的空间分布不均</> : "现，家庭收入、父母受教育程度与大学入学概率"}</p>
      <p><i>111</i>{revised ? <> 也会<mark className="rt-mark-blue">加剧区域间的</mark>不平等（Chen et al., 2019）。</> : "呈显著正相关。此外，教育资源的空间分布不均"}</p>
      <div className="rt-english-copy">
        <p><i>112</i>These findings suggest that improving the equitable allocation of</p>
        <p><i>113</i>educational resources is essential for promoting social mobility</p>
        <p><i>114</i>and long-term economic growth (OECD, 2021). However,</p>
        <p><i>115</i>existing policies still face {revised && <mark className="rt-mark-blue">significant</mark>} implementation challenges.</p>
      </div>
    </div>
  );
}

export function WorkbenchPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const languageKey = isEnglish ? "en" : "zh";
  const [mode, setMode] = useState("balanced");
  const [openFinding, setOpenFinding] = useState(1);
  const [findingTab, setFindingTab] = useState("findings");
  const [runState, setRunState] = useState("idle");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cleaned, setCleaned] = useState(false);
  const [exported, setExported] = useState(false);
  const rewriteTriggerRef = useRef(null);
  const confirmDialogRef = useRef(null);
  const cancelConfirmRef = useRef(null);
  const previousFocusRef = useRef(null);

  const selectedStrategy = rewriteStrategies.find((strategy) => strategy.id === mode);
  const billableCharacters = 1284;
  const estimatedDeduction = Math.ceil(billableCharacters * selectedStrategy.multiplier);
  const remainingAfterRewrite = 56420 - estimatedDeduction;

  useEffect(() => {
    if (!confirmOpen) return undefined;

    previousFocusRef.current = document.activeElement;
    const appRoot = document.getElementById("root");
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden");
    const previouslyInert = appRoot?.hasAttribute("inert") ?? false;

    cancelConfirmRef.current?.focus();
    appRoot?.setAttribute("inert", "");
    appRoot?.setAttribute("aria-hidden", "true");

    function handleModalKeydown(event) {
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
    }

    window.addEventListener("keydown", handleModalKeydown);
    return () => {
      window.removeEventListener("keydown", handleModalKeydown);
      if (appRoot) {
        if (!previouslyInert) appRoot.removeAttribute("inert");
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      (previousFocusRef.current || rewriteTriggerRef.current)?.focus?.();
    };
  }, [confirmOpen]);

  const runRewrite = () => {
    if (runState === "working") return;
    setConfirmOpen(false);
    setRunState("working");
    window.setTimeout(() => setRunState("done"), 1250);
  };

  return (
    <div className="rt-page rt-workbench-page">
      <h1 className="rt-sr-only">
        {isEnglish ? "教育公平研究 · Faithful optimization workbench" : "教育公平研究 · 保真优化工作台"}
      </h1>
      <div className="rt-document-bar">
        <div>
          <button className="rt-doc-back" onClick={() => navigate("/app")}>
            {isEnglish ? "← Documents" : "← 文档"}
          </button>
          <span className="rt-doc-name">教育公平研究.docx <NotePencil size={16} weight="bold" /></span>
          <span className="rt-doc-meta">
            {isEnglish ? "Last saved: Today, 14:26" : "最后保存：今天 14:26"} <b /> 12,841 {isEnglish ? "chars" : "字"}
          </span>
        </div>
        <div className="rt-document-actions">
          <button className="rt-quiet-button" onClick={() => navigate("/app/documents/rt-014/versions")}>
            <ClockCounterClockwise weight="bold" /> {isEnglish ? "Version history" : "版本历史"}
          </button>
          <span className="rt-service-pill"><StatusDot /> {isEnglish ? "AI service online" : "AI 服务正常"}</span>
          <button className="rt-button rt-button-primary rt-export-top" onClick={() => setExported(true)}>
            <DownloadSimple weight="bold" /> {isEnglish ? "Export document" : "导出文档"}
          </button>
        </div>
      </div>

      <StageRail active={runState === "done" ? 4 : 3} />

      <div className="rt-editor-grid">
        <section className="rt-paper-panel">
          <header>
            <div>
              <strong>{isEnglish ? "Original manuscript" : "原始稿件"}</strong>
              <span>第 3.2 节 · 教育机会的地区差异</span>
            </div>
            <small>{isEnglish ? "1,284 chars" : "共 1,284 字"}</small>
          </header>
          <PaperLines />
        </section>

        <section className="rt-paper-panel is-current">
          <header>
            <div>
              <strong>{isEnglish ? "Current manuscript (editing)" : "当前稿件（修改中）"}</strong>
              <span>{isEnglish ? "Phrasing optimized with fact anchors preserved" : "保留事实锚点的表达优化"}</span>
            </div>
            <small>{isEnglish ? "1,312 chars" : "共 1,312 字"} <b>+28</b></small>
          </header>
          <PaperLines revised />
        </section>

        <aside className="rt-findings-panel">
          <header>
            <div>
              <strong>{isEnglish ? "Analysis and evidence" : "分析结果与证据"}</strong>
              <small>{isEnglish ? "Based on 31 checks · Generated at 14:26" : "基于 31 项检查 · 生成于 14:26"}</small>
            </div>
          </header>
          <div className="rt-finding-metrics">
            <div><strong>28</strong><span>{isEnglish ? "Suggestions" : "修改建议"}</span></div>
            <div className="is-peach"><strong>6</strong><span>{isEnglish ? "Need review" : "需审阅"}</span></div>
            <div className="is-yellow"><strong>3</strong><span>{isEnglish ? "Inconsistent terms" : "术语不一致"}</span></div>
            <div className="is-green"><strong>16 / 16</strong><span>{isEnglish ? "Core facts preserved" : "核心事实保留"}</span></div>
          </div>
          <div className="rt-findings-tabs" role="tablist" aria-label={isEnglish ? "Analysis views" : "分析结果视图"}>
            {findingTabs.map((tab, index) => (
              <button
                key={tab.id}
                id={`rt-finding-tab-${index}`}
                role="tab"
                aria-selected={findingTab === tab.id}
                aria-controls="rt-finding-panel"
                className={findingTab === tab.id ? "is-active" : ""}
                onClick={() => setFindingTab(tab.id)}
              >{tab.label[languageKey]}</button>
            ))}
          </div>
          <div
            className="rt-finding-list"
            id="rt-finding-panel"
            role="tabpanel"
            aria-labelledby={`rt-finding-tab-${findingTabs.findIndex((tab) => tab.id === findingTab)}`}
          >
            {findingTab === "findings" ? findings.map((finding) => {
              const isOpen = openFinding === finding.id;
              return (
                <article className={`rt-finding ${isOpen ? "is-open" : ""}`} key={finding.id}>
                  <button
                    aria-expanded={isOpen}
                    aria-controls={`rt-finding-body-${finding.id}`}
                    onClick={() => setOpenFinding(isOpen ? null : finding.id)}
                  >
                    <span className="rt-finding-number">{finding.id}</span>
                    <strong>{finding.title[languageKey]}</strong>
                    <small>{finding.count[languageKey]}</small>
                    <CaretDown weight="bold" />
                  </button>
                  {isOpen && (
                    <div className="rt-finding-body" id={`rt-finding-body-${finding.id}`}>
                      <p>{finding.body[languageKey]}</p>
                      {finding.refs.length > 0 && (
                        <strong className="rt-ref-title">{isEnglish ? "Related evidence" : "相关证据"}</strong>
                      )}
                      {finding.refs.map(([reference, tag]) => (
                        <div className="rt-reference" key={reference}>
                          <FileText weight="bold" />
                          <span>{reference}</span>
                          <em className={tag === "support" ? "is-support" : ""}>
                            {tag === "support"
                              ? (isEnglish ? "Supports" : "支撑")
                              : (isEnglish ? "Partially relevant" : "部分相关")}
                          </em>
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              );
            }) : (
              <div className="rt-tab-placeholder">
                <FileText size={29} weight="bold" />
                <strong>{findingTabs.find((tab) => tab.id === findingTab)?.label[languageKey]}</strong>
                <p>{isEnglish
                  ? "Organized for the current section and selected rewrite strategy."
                  : "已按照当前章节与选定改写策略整理完成。"}</p>
                <button onClick={() => setFindingTab("findings")}>
                  {isEnglish ? "Return to key findings" : "返回关键发现"}
                </button>
              </div>
            )}
          </div>
        </aside>
      </div>

      <section className="rt-action-dock">
        <div className="rt-mode-copy">
          <strong>{isEnglish ? "Rewrite strategy" : "改写策略"}</strong>
          <small>{isEnglish ? "Improve phrasing while preserving academic rigor" : "在保持学术严谨的前提下优化表达"}</small>
        </div>
        <div className="rt-mode-switch" role="group" aria-label={isEnglish ? "Rewrite intensity" : "改写强度"}>
          {rewriteStrategies.map((strategy) => (
            <button
              key={strategy.id}
              className={mode === strategy.id ? "is-active" : ""}
              aria-pressed={mode === strategy.id}
              onClick={() => setMode(strategy.id)}
            >
              <strong>{strategy.label[languageKey]}</strong><small>{strategy.detail[languageKey]}</small>
            </button>
          ))}
        </div>
        <span className="rt-dock-divider" />
        <button
          className={`rt-safe-clean ${cleaned ? "is-done" : ""}`}
          aria-pressed={cleaned}
          onClick={() => setCleaned(!cleaned)}
        >
          {cleaned ? <CheckCircle weight="fill" /> : <ShieldCheck weight="bold" />}
          <span>
            <strong>{cleaned
              ? (isEnglish ? "Safe cleanup complete" : "已安全清理")
              : (isEnglish ? "Safe cleanup" : "安全清理")}</strong>
            <small>{isEnglish ? "Local rules · Deterministic edits only" : "本地规则 · 仅确定性修改"}</small>
          </span>
        </button>
        <button
          ref={rewriteTriggerRef}
          className={`rt-rewrite-action ${runState === "done" ? "is-done" : ""}`}
          disabled={runState !== "idle"}
          aria-busy={runState === "working"}
          aria-haspopup="dialog"
          onClick={() => setConfirmOpen(true)}
        >
          {runState === "working" ? <CircleNotch className="rt-spin" weight="bold" /> : runState === "done" ? <CheckCircle weight="fill" /> : <FileText weight="bold" />}
          <span>
            <strong>{runState === "working"
              ? (isEnglish ? `Running ${selectedStrategy.label.en.toLowerCase()} rewrite…` : `正在执行${selectedStrategy.label.zh}改写…`)
              : runState === "done"
                ? (isEnglish ? "Rewrite complete—review now" : "改写完成，进入审阅")
                : (isEnglish ? "Faithful rewrite" : "保真改写")}</strong>
            <small>{runState === "done"
              ? (isEnglish ? "Original text and fact anchors preserved" : "原稿与事实锚点已保留")
              : (isEnglish ? "Preserve meaning · Improve expression" : "保持原意 · 提升表达质量")}</small>
          </span>
          <ArrowRight weight="bold" />
        </button>
      </section>

      {confirmOpen && createPortal(
        <div
          className="rt-confirm-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setConfirmOpen(false);
          }}
        >
          <section
            ref={confirmDialogRef}
            className="rt-rewrite-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rt-rewrite-confirm-title"
            aria-describedby="rt-rewrite-confirm-description"
          >
            <span className="rt-confirm-kicker">{isEnglish ? "RUN CHECK / USAGE PREVIEW" : "RUN CHECK / 扣减预览"}</span>
            <h2 id="rt-rewrite-confirm-title">
              {isEnglish ? `Run a ${selectedStrategy.label.en.toLowerCase()} rewrite?` : `确认执行${selectedStrategy.label.zh}改写？`}
            </h2>
            <p id="rt-rewrite-confirm-description">
              {isEnglish
                ? "The current section will be processed. AI rewriting starts and quota is reserved only after you confirm."
                : "将处理当前章节，确认后才会启动 AI 改写并预留字数额度。"}
            </p>
            <div className="rt-confirm-metrics" aria-label={isEnglish ? "Rewrite usage estimate" : "本次改写计费信息"}>
              <div>
                <span>{isEnglish ? "Billable text" : "计费文本"}</span>
                <strong>{billableCharacters.toLocaleString()} {isEnglish ? "chars" : "字"}</strong>
              </div>
              <div><span>{isEnglish ? "Strategy multiplier" : "当前策略倍率"}</span><strong>×{selectedStrategy.multiplier.toFixed(2)}</strong></div>
              <div className="is-highlight">
                <span>{isEnglish ? "Estimated deduction" : "预计扣减"}</span>
                <strong>{estimatedDeduction.toLocaleString()} {isEnglish ? "chars" : "字"}</strong>
              </div>
            </div>
            <div className="rt-confirm-balance">
              <span>{isEnglish ? "56,420 chars currently available" : "当前可用 56,420 字"}</span>
              <strong>{isEnglish
                ? `Estimated balance: ${remainingAfterRewrite.toLocaleString()} chars`
                : `预计完成后 ${remainingAfterRewrite.toLocaleString()} 字`}</strong>
            </div>
            <small>{isEnglish
              ? "This estimate is for confirmation only. Final usage is based on the text actually processed."
              : "预估仅供确认；最终扣减以实际处理的文本字数为准。"}</small>
            <div className="rt-confirm-actions">
              <button ref={cancelConfirmRef} className="rt-button" onClick={() => setConfirmOpen(false)}>
                {isEnglish ? "Cancel" : "取消"}
              </button>
              <button className="rt-button rt-button-primary" onClick={runRewrite}>
                {isEnglish ? "Confirm and start" : "确认并开始"} <ArrowRight weight="bold" aria-hidden="true" />
              </button>
            </div>
          </section>
        </div>,
        document.body,
      )}

      {exported && (
        <SoftToast>
          {isEnglish ? "Export created. The document will include the current changes." : "导出任务已创建，文档将包含当前修改结果。"}
        </SoftToast>
      )}
    </div>
  );
}

export function VersionsPage({ navigate = () => {} }) {
  const { isEnglish } = useLocale();
  const languageKey = isEnglish ? "en" : "zh";
  const [selected, setSelected] = useState("v4");
  const [compareMode, setCompareMode] = useState("split");
  const [restored, setRestored] = useState(false);
  const currentVersion = versionRows.find((item) => item.id === selected);
  const isOriginalVersion = selected === "v1";
  const currentStats = versionStats[selected];

  return (
    <div className="rt-page rt-versions-page">
      <section className="rt-page-intro rt-versions-intro">
        <div>
          <button className="rt-back-link" onClick={() => navigate("/app/documents/rt-014")}>
            {isEnglish ? "← Back to workbench" : "← 返回编辑台"}
          </button>
          <span className="rt-kicker">VERSION LEDGER / 教育公平研究.docx</span>
          <h1>{isEnglish ? "Every change leaves a trace." : "每一次修改，都有迹可循。"}</h1>
          <p>{isEnglish
            ? "Compare phrasing and fact anchors across versions, and restore any point whenever needed."
            : "对照不同版本的表达与事实锚点，必要时可恢复到任何节点。"}</p>
        </div>
        <button className="rt-button rt-button-primary" onClick={() => navigate("/app/documents/rt-014")}>
          <NotePencil weight="bold" /> {isEnglish ? "Continue editing" : "继续编辑"}
        </button>
      </section>

      <div className="rt-versions-layout">
        <aside className="rt-board rt-version-list">
          <header>
            <span className="rt-section-index">01</span>
            <div>
              <h2>{isEnglish ? "Version history" : "版本记录"}</h2>
              <small>{isEnglish ? "4 checkpoints saved automatically" : "自动保存 4 个节点"}</small>
            </div>
          </header>
          <div
            className="rt-version-timeline"
            role="tablist"
            aria-label={isEnglish ? "Document versions" : "文档版本"}
            aria-orientation="vertical"
          >
            {versionRows.map((version) => (
              <button
                key={version.id}
                id={`rt-version-tab-${version.id}`}
                role="tab"
                aria-selected={selected === version.id}
                aria-controls="rt-version-panel"
                className={selected === version.id ? "is-active" : ""}
                onClick={() => { setSelected(version.id); setRestored(false); }}
              >
                <span className={`rt-version-node is-${version.tone}`} />
                <span className="rt-version-copy">
                  <strong>{version.name[languageKey]}</strong>
                  <small>{version.time[languageKey]}</small>
                  <em>{version.detail[languageKey]}</em>
                </span>
                {version.id === "v4" && (
                  <span className="rt-current-badge">{isEnglish ? "Current" : "当前"}</span>
                )}
              </button>
            ))}
          </div>
          <div className="rt-version-guard">
            <ShieldCheck size={24} weight="bold" />
            <p>
              <strong>{isEnglish ? "Versions never overwrite the original" : "版本不会覆盖原稿"}</strong><br />
              {isEnglish ? "A restored version is saved as a new checkpoint." : "恢复时会另存为新节点。"}
            </p>
          </div>
        </aside>

        <section
          className="rt-board rt-diff-board"
          id="rt-version-panel"
          role="tabpanel"
          aria-labelledby={`rt-version-tab-${selected}`}
        >
          <header className="rt-diff-header">
            <div>
              <span className="rt-section-index">02</span>
              <div>
                <h2>{currentVersion.name[languageKey]}</h2>
                <small>
                  {currentVersion.time[languageKey]} · {isOriginalVersion
                    ? (isEnglish ? "Original baseline details" : "原始基线详情")
                    : (isEnglish ? "Compared with original import" : "与原始导入对照")}
                </small>
              </div>
            </div>
            <div className="rt-diff-tools">
              {!isOriginalVersion && (
                <div className="rt-compare-tabs" role="tablist" aria-label={isEnglish ? "Version comparison view" : "版本对照方式"}>
                  <button role="tab" aria-selected={compareMode === "split"} className={compareMode === "split" ? "is-active" : ""} onClick={() => setCompareMode("split")}>
                    {isEnglish ? "Side by side" : "左右对照"}
                  </button>
                  <button role="tab" aria-selected={compareMode === "inline"} className={compareMode === "inline" ? "is-active" : ""} onClick={() => setCompareMode("inline")}>
                    {isEnglish ? "Inline" : "行内标记"}
                  </button>
                </div>
              )}
              <button className="rt-restore-button" onClick={() => setRestored(true)}>
                <ArrowCounterClockwise weight="bold" /> {isEnglish ? "Restore this version" : "恢复此版本"}
              </button>
            </div>
          </header>

          {isOriginalVersion ? (
            <div className="rt-no-diff-state" role="status">
              <span className="rt-no-diff-icon"><ShieldCheck weight="bold" /></span>
              <span className="rt-kicker">ORIGINAL BASELINE</span>
              <h3>{isEnglish ? "This is the immutable original-import baseline." : "这是不可变的原始导入基线。"}</h3>
              <p>{isEnglish
                ? "This checkpoint preserves everything from the first import, so there are no differences to compare."
                : "此节点保留了首次导入时的全部内容，当前没有可供对照的差异。"}</p>
              <div className="rt-original-facts" aria-label={isEnglish ? "Original import details" : "原始导入信息"}>
                <div><span>{isEnglish ? "Full length" : "全文长度"}</span><strong>12,841 {isEnglish ? "chars" : "字"}</strong></div>
                <div><span>{isEnglish ? "Current excerpt" : "当前节选"}</span><strong>1,284 {isEnglish ? "chars" : "字"}</strong></div>
                <div><span>{isEnglish ? "Imported" : "导入时间"}</span><strong>{isEnglish ? "Yesterday, 21:54" : "昨天 21:54"}</strong></div>
              </div>
            </div>
          ) : (
            <>
              <div
                className="rt-diff-summary"
                aria-label={isEnglish
                  ? `${currentVersion.name.en} comparison summary`
                  : `${currentVersion.name.zh}对照摘要`}
              >
                <div><strong>{currentStats.changes}</strong><span>{isEnglish ? "Text changes" : "处文本变更"}</span></div>
                <div><strong>{currentStats.facts}</strong><span>{isEnglish ? "Core facts preserved" : "核心事实保留"}</span></div>
                <div><strong>{currentStats.terms}</strong><span>{isEnglish ? "Terms standardized" : "术语已统一"}</span></div>
                <div><strong>{currentStats.citations}</strong><span>{isEnglish ? "Citations lost" : "引文遗失"}</span></div>
              </div>

              {compareMode === "split" ? (
            <div className="rt-diff-columns">
              <article>
                <header><span>{isEnglish ? "Original import" : "原始导入"}</span><small>1,284 {isEnglish ? "chars" : "字"}</small></header>
                <div className="rt-diff-paper">
                  <p>教育公平是社会公平的重要基础，也是实现共同富裕的内在要求。近年来，随着我国高等教育规模的快速扩张，城乡之间、地区之间的教育资源差距依然显著。</p>
                  <p className="rt-delete-line">特别是在中西部地区，高质量教育资源的可及性仍然不足。</p>
                  <p>已有研究表明，家庭社会经济地位（SES）对个体的高等教育机会具有显著影响。</p>
                </div>
              </article>
              <article>
                <header><span>{currentVersion.name[languageKey]}</span><small>1,312 {isEnglish ? "chars" : "字"}</small></header>
                <div className="rt-diff-paper">
                  <p>教育公平是社会公平的重要基础，也是实现共同富裕的内在要求。近年来，随着我国高等教育规模的快速扩张，城乡之间、地区之间的教育资源差距依然显著。</p>
                  <p className="rt-add-line">尤其是在中西部地区，优质教育资源的可及性仍显不足。</p>
                  <p>现有研究表明，家庭社会经济地位（SES）对个体的高等教育机会具有显著影响。</p>
                </div>
              </article>
            </div>
              ) : (
                <article className="rt-inline-diff">
              <span className="rt-line-number">104</span>
              <p><del>特别是在中西部地区，高质量</del> <ins>尤其是在中西部地区，优质</ins> 教育资源的可及性仍然不足。</p>
              <span className="rt-line-number">105</span>
              <p><del>已有研究表明</del> <ins>现有研究表明</ins>，家庭社会经济地位对个体的高等教育机会具有显著影响。</p>
              <div className="rt-diff-reason">
                <Sparkle weight="bold" /> {isEnglish
                  ? "Reason: Standardize academic terminology and soften unnecessary absolutes without changing the original argument."
                  : "修改原因：统一学术用词，弱化不必要的绝对表述，不改变原论点。"}
              </div>
                </article>
              )}
            </>
          )}
        </section>
      </div>
      {restored && (
        <SoftToast>
          {isEnglish
            ? `“${currentVersion.name.en}” was saved as the new current version.`
            : `已将“${currentVersion.name.zh}”另存为新的当前版本。`}
        </SoftToast>
      )}
    </div>
  );
}
