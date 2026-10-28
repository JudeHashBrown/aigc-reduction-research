export const ONBOARDING_VERSION = 1;
const TOUR_PAGES = new Set(["documents", "import", "workbench", "empty-workbench"]);

export function onboardingOwner(session) {
  if (!session?.ready || session.authMode !== "accounts" || !session.authenticated
      || session.kind === "guest") return null;
  const accountId = session.user?.account_id || session.user?.id;
  return typeof accountId === "string" && accountId ? accountId : null;
}

export function onboardingPage(path, hasManuscript = false) {
  if (path === "/app") return "documents";
  if (path === "/app/new") return "import";
  if (path === "/app/workbench") return hasManuscript ? "workbench" : "empty-workbench";
  return null;
}

export function onboardingStorageKey(owner) {
  return `rightthesis-onboarding:v${ONBOARDING_VERSION}:${encodeURIComponent(owner)}`;
}

function validState(value) {
  return {
    version: ONBOARDING_VERSION,
    skipped: value?.version === ONBOARDING_VERSION && value.skipped === true,
    completed: value?.version === ONBOARDING_VERSION && Array.isArray(value.completed)
      ? [...new Set(value.completed.filter((page) => TOUR_PAGES.has(page)))] : [],
  };
}

// The fallback also remembers dismissals when browser storage is unavailable.
// Only tutorial progress is stored; manuscript contents and email are not used.
export function createOnboardingStore(storageProvider) {
  const memory = new Map();
  const read = (owner) => {
    if (memory.has(owner)) return memory.get(owner);
    try {
      const raw = storageProvider()?.getItem(onboardingStorageKey(owner));
      if (raw) {
        const state = validState(JSON.parse(raw));
        memory.set(owner, state);
        return state;
      }
    } catch { /* Keep the in-memory dismissal if storage is blocked or corrupt. */ }
    return memory.get(owner) || validState(null);
  };
  return {
    read,
    shouldStart(owner, page) {
      if (!owner || !TOUR_PAGES.has(page)) return false;
      const state = read(owner);
      return !state.skipped && !state.completed.includes(page);
    },
    finish(owner, page, reason) {
      if (!owner || !TOUR_PAGES.has(page)
          || !["completed", "skipped"].includes(reason)) return;
      const previous = read(owner);
      const next = {
        ...previous,
        skipped: previous.skipped || reason === "skipped",
        completed: reason === "completed"
          ? [...new Set([...previous.completed, page])] : previous.completed,
      };
      memory.set(owner, next);
      try { storageProvider()?.setItem(onboardingStorageKey(owner), JSON.stringify(next)); }
      catch { /* Tutorial progress never blocks the workspace. */ }
    },
  };
}

const step = (target, titleZh, titleEn, descriptionZh, descriptionEn, isEnglish) => ({
  target: `[data-tour="${target}"]`,
  title: isEnglish ? titleEn : titleZh,
  description: isEnglish ? descriptionEn : descriptionZh,
});

export function workspaceTourSteps(page, isEnglish) {
  const make = (...args) => step(...args, isEnglish);
  if (page === "documents") return [
    make("new-document", "从一份文稿开始", "Start with a manuscript",
      "点击这里新建文档，粘贴正文或上传 TXT、DOCX、PDF。导入后会先进行免费诊断。",
      "Create a document here by pasting text or uploading TXT, DOCX, or PDF. Import starts with free analysis."),
    make("saved-documents", "继续之前的文稿", "Continue a saved manuscript",
      "文稿会保存在这里。点击任一文稿，就能继续编辑、查看诊断或核对修改。",
      "Your saved manuscripts appear here. Open one to continue editing, review its diagnosis, or check changes."),
    make("account-overview", "了解额度与单次上限", "Check your credits and limits",
      "分析和安全清理不消耗改写额度。AI 改写受余额和单次上限约束；免费账户开放保守模式，有效付费套餐可使用平衡和深度模式。",
      "Analysis and safe cleanup use no rewrite credits. AI rewrites depend on your balance and per-task limit. Free accounts have conservative mode; active paid plans also unlock balanced and deep modes."),
    make("user-menu", "随时重新查看教程", "Replay the tutorial anytime",
      "点击右上角头像，在用户菜单里选择“新手教程”，就能重新查看当前页面的引导。完成本页后，首次进入导入页和编辑工作台时还会介绍相应操作。",
      "Open your user menu and choose “Getting started” to replay the current page’s tour. Your first visits to import and the editor also introduce their controls."),
  ];
  if (page === "import") return [
    make("import-method", "选择导入方式", "Choose how to import",
      "可以直接粘贴中英文正文，也可以上传 TXT、DOCX 或 PDF 文件。上传文件最大为 20 MB。",
      "Paste Chinese or English text, or upload a TXT, DOCX, or PDF file up to 20 MB."),
    make("import-content", "放入要处理的正文", "Add your manuscript",
      "在这里粘贴文字或选择文件。先确认正文完整；进入工作台后，仍可直接编辑和删减当前稿。",
      "Paste text or choose a file here. Check that the manuscript is complete. You can still edit or trim the current draft in the workspace."),
    make("import-analyze", "免费生成诊断", "Run free analysis",
      "准备好正文后点击这里。分析会生成表达线索与事实锚点，再打开编辑工作台；不会进行段落改写，也不消耗改写额度。",
      "Once your text is ready, start here. Analysis produces expression findings and fact anchors, then opens the editor. It does not rewrite passages or use rewrite credits."),
  ];
  if (page === "empty-workbench") return [
    make("empty-import", "先打开一份文稿", "Open a manuscript first",
      "当前还没有打开的文稿。点击“新建文档”粘贴或上传正文；进入编辑工作台后，会继续介绍编辑和修改功能。",
      "No manuscript is open yet. Create a document by pasting or uploading text. The editor tour will then introduce editing and revision controls."),
  ];
  if (page === "workbench") return [
    make("current-draft", "这里可以直接编辑", "Edit the current draft here",
      "在当前稿里直接增删和修改正文。编辑后旧诊断会过期，需要重新分析；超过单次上限时，也可以先在这里删减。",
      "Add, remove, or edit text directly in the current draft. Changes make its diagnosis outdated, so analyze again. If you exceed the per-task limit, trim the text here."),
    make("diagnosis", "查看诊断与证据", "Review findings and evidence",
      "这里列出表达线索、可安全清理项目和事实锚点。点击线索可以定位正文；有“修改此项”按钮时，也能针对这条线索修改。",
      "Find expression issues, eligible cleanup items, and fact anchors here. Select a finding to locate it in the text, or use “Modify this finding” when available."),
    make("analyze-current", "修改正文后重新分析", "Analyze after editing",
      "这个按钮检查当前版本并更新右侧报告。分析免费，不进行段落改写；手动编辑后请先重新分析，再开始改写。",
      "This checks the current version and refreshes the report. Analysis is free and does not rewrite passages. After manual edits, analyze again before rewriting."),
    make("safe-cleanup", "免费清理明确的格式问题", "Clean up eligible formatting",
      "安全清理处理可以确定的格式修改，例如移除粗体标记或标题装饰符号。只有报告存在适用项时才能使用，不消耗改写额度。",
      "Safe cleanup handles eligible formatting, such as bold markers or decorative heading symbols. It is available when the report has suitable items and uses no rewrite credits."),
    make("rewrite-modes", "选择改写策略", "Choose a rewrite mode",
      "保守、平衡和深度会提供不同数量的修改候选。免费账户仅开放保守模式；有效付费套餐解锁平衡和深度。深度最多预占正文单位数的 1.5 倍额度。",
      "Conservative, balanced, and deep modes offer different numbers of revision candidates. Free accounts have conservative mode; active paid plans unlock the others. Deep reserves up to 1.5× the text-unit count in credits."),
    make("modify-draft", "确认后开始修改", "Confirm before revising",
      "点击这里先查看预占额度，再确认开始。正文需在单次上限内，且余额足够；若按钮不可用，请查看上方的原因提示。",
      "Use this button to review the credit reservation and confirm before starting. Your draft must fit the per-task limit and your balance. If unavailable, check the notice above it."),
    make("document-actions", "核对修改后再导出", "Review changes, then export",
      "修改完成后，下方会用浅红标出删除、浅绿标出新增。核对事实、引文和原意后，可以复制全文或下载 TXT；导入的 DOCX 还可导出 DOCX。原稿可从版本历史恢复。",
      "After a revision, red highlights show removals and green highlights show additions below. Check facts, citations, and meaning, then copy or download TXT. DOCX imports also support DOCX export. Version history keeps the original."),
  ];
  return [];
}
