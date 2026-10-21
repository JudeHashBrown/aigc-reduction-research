import { useMemo, useState } from 'react';
import {
  ArrowRight,
  ArrowSquareOut,
  Article,
  BookOpenText,
  CaretDown,
  Check,
  CheckCircle,
  ClockCounterClockwise,
  Export,
  FileText,
  GlobeHemisphereWest,
  Lightning,
  List,
  LockKey,
  MagnifyingGlass,
  PencilSimpleLine,
  Scan,
  SealCheck,
  ShieldCheck,
  Sparkle,
  UploadSimple,
  Warning,
  X,
} from '@phosphor-icons/react';
import './public-pages.css';
import { LanguageToggle, useLocale } from '../locale.jsx';
import { localizedPlanDescription as planDescription, localizedPlanName as planName } from '../plan-copy.js';
import { useOptionalPlatform, usePlatform } from '../platform.jsx';
import { AuthPage as AccountAuthPage } from './AuthPage.jsx';

const go = (navigate, path) => () => navigate(path);

function moveTabFocus(event, tabs, current, onChange, idPrefix) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const currentIndex = tabs.indexOf(current);
  const nextIndex = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? tabs.length - 1
      : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  const next = tabs[nextIndex];
  onChange(next);
  window.requestAnimationFrame(() => document.getElementById(`${idPrefix}-${next}`)?.focus());
}

function Brand({ navigate }) {
  const { isEnglish } = useLocale();
  return (
    <button className="rtp-brand-wrap" onClick={go(navigate, '/')} aria-label={isEnglish ? 'Return to RightThesis home' : '返回 RightThesis 首页'}>
      <span className="rtp-brand">RightThesis</span>
      <span className="rtp-brand-line">{isEnglish ? 'Let good research speak more clearly' : '让好的研究被更好地表达'}</span>
    </button>
  );
}

function PublicHeader({ navigate, active }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { isEnglish } = useLocale();
  const session = useOptionalPlatform()?.session;
  const signedIn = session?.authMode === 'accounts' && session?.authenticated && session?.kind !== 'guest';
  const items = [
    ['首页', 'Home', '/'],
    ['产品', 'Product', 'section:product'],
    ['定价', 'Pricing', '/pricing'],
    ['帮助', 'Help', '/help'],
  ];

  const jump = (path) => {
    setMenuOpen(false);
    if (path.startsWith('section:')) {
      const sectionId = path.split(':')[1];
      const target = document.getElementById(sectionId);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      else navigate('/');
      return;
    }
    navigate(path);
  };

  return (
    <header className="rtp-header">
      <div className="rtp-header-inner">
        <Brand navigate={navigate} />
        <nav id="rtp-public-navigation" className={`rtp-nav ${menuOpen ? 'is-open' : ''}`} aria-label={isEnglish ? 'Primary navigation' : '主要导航'}>
          {items.map(([label, englishLabel, path]) => (
            <button
              key={label}
              onClick={() => jump(path)}
              className={active === label ? 'is-active' : ''}
              aria-current={active === label ? 'page' : undefined}
            >
              {isEnglish ? englishLabel : label}
            </button>
          ))}
          <div className="rtp-nav-actions">
            {signedIn ? (
              <button className="rtp-btn rtp-btn-blue rtp-btn-sm" onClick={() => jump('/app')}>
                {isEnglish ? 'My workspace' : '我的工作台'} <ArrowRight weight="bold" />
              </button>
            ) : (
              <>
                <button className="rtp-btn rtp-btn-ghost" onClick={() => jump('/auth')}>{isEnglish ? 'Sign in' : '登录'}</button>
                <button className="rtp-btn rtp-btn-blue rtp-btn-sm" onClick={() => jump('/auth')}>
                  {isEnglish ? 'Start free' : '免费开始'} <ArrowRight weight="bold" />
                </button>
              </>
            )}
          </div>
        </nav>
        <LanguageToggle className="rtp-language-toggle" />
        <button
          className="rtp-menu-button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-controls="rtp-public-navigation"
          aria-expanded={menuOpen}
          aria-label={menuOpen ? (isEnglish ? 'Close menu' : '关闭菜单') : (isEnglish ? 'Open menu' : '打开菜单')}
        >
          {menuOpen ? <X weight="bold" /> : <List weight="bold" />}
        </button>
      </div>
    </header>
  );
}

function PublicFooter({ navigate }) {
  const { isEnglish } = useLocale();
  return (
    <footer className="rtp-footer">
      <div className="rtp-footer-lead">
        <Brand navigate={navigate} />
        <p>{isEnglish ? 'Revise with rigor. Express with confidence.' : '更严谨地修改，更可信地表达。'}</p>
      </div>
      <div className="rtp-footer-links">
        <div>
          <strong>{isEnglish ? 'Product' : '产品'}</strong>
          <button onClick={go(navigate, '/app')}>{isEnglish ? 'Workspace' : '工作台'}</button>
          <button onClick={go(navigate, '/pricing')}>{isEnglish ? 'Plans & usage' : '套餐与用量'}</button>
          <button onClick={go(navigate, '/help')}>{isEnglish ? 'Help center' : '帮助中心'}</button>
        </div>
        <div>
          <strong>{isEnglish ? 'Policies' : '规则'}</strong>
          <a href="/legal/privacy">{isEnglish ? 'Privacy policy' : '隐私政策'}</a>
          <a href="/legal/terms">{isEnglish ? 'Terms of service' : '服务条款'}</a>
        </div>
      </div>
      <div className="rtp-footer-bottom">
        <span>© 2026 RightThesis</span>
        <span className="rtp-service-dot"><i /> {isEnglish ? 'Service status is shown in the workspace' : '服务状态以工作台为准'}</span>
      </div>
    </footer>
  );
}

function Shell({ children, navigate, active }) {
  return (
    <div className="rtp-page-shell">
      <PublicHeader navigate={navigate} active={active} />
      {children}
      <PublicFooter navigate={navigate} />
    </div>
  );
}

function TinyStatus({ children, tone = 'green' }) {
  return <span className={`rtp-status rtp-status-${tone}`}><i /> {children}</span>;
}

function WorkbenchPreview({ navigate }) {
  const { isEnglish } = useLocale();
  const [previewTab, setPreviewTab] = useState('发现');
  const previewTabs = [
    { value: '发现', label: isEnglish ? 'Findings' : '发现' },
    { value: '修改', label: isEnglish ? 'Revisions' : '修改' },
    { value: '参考', label: isEnglish ? 'Sources' : '参考' },
  ];
  return (
    <section className="rtp-workbench" aria-label={isEnglish ? 'RightThesis workspace preview' : 'RightThesis 工作台预览'}>
      <div className="rtp-window-bar">
        <div className="rtp-window-title">
          <span className="rtp-mini-mark">RT</span>
          <div><b>教育公平研究.docx</b><small>{isEnglish ? 'Last saved: Today, 14:26' : '最后保存：今天 14:26'}</small></div>
        </div>
        <TinyStatus>{isEnglish ? 'Reviewable example' : '可审阅示例'}</TinyStatus>
          <button className="rtp-btn rtp-btn-blue rtp-btn-sm" onClick={go(navigate, '/auth')}>
          {isEnglish ? 'Open workspace' : '打开工作台'} <ArrowSquareOut weight="bold" />
        </button>
      </div>
      <div className="rtp-progress-strip">
        <span className="is-done"><b><Check weight="bold" /></b> {isEnglish ? 'Import' : '导入'}</span>
        <span className="is-done"><b><Check weight="bold" /></b> {isEnglish ? 'Analyze' : '分析'}</span>
        <span className="is-current"><b>3</b> {isEnglish ? 'Rewriting' : '优化中'}</span>
        <span><b>4</b> {isEnglish ? 'Review' : '审阅'}</span>
      </div>
      <div className="rtp-preview-grid">
        <article className="rtp-paper-panel">
          <div className="rtp-panel-head"><b>{isEnglish ? 'Original draft' : '原始稿件'}</b><span>{isEnglish ? '1,284 characters' : '共 1,284 字'}</span></div>
          <div className="rtp-paper-copy">
            <p><i>101</i>教育公平是社会公平的重要基础，也是实现共同富裕的内在要求。近年来，随着我国高等教育规模的快速扩张，城乡之间、地区之间的教育资源差距依然显著。</p>
            <p className="is-source"><i>105</i>已有研究表明，家庭社会经济地位对个体的高等教育机会具有显著影响（李明，2021；Zhang, 2020）。</p>
            <p><i>109</i>These findings suggest that improving the equitable allocation of educational resources remains essential for long-term social mobility.</p>
          </div>
        </article>
        <article className="rtp-paper-panel">
          <div className="rtp-panel-head"><b>{isEnglish ? 'Current draft' : '当前稿件'}</b><span className="rtp-positive">{isEnglish ? 'Wording refined' : '表达已精简'}</span></div>
          <div className="rtp-paper-copy">
            <p><i>101</i>教育公平是社会公平的重要基础，也是实现共同富裕的内在要求。近年来，随着我国高等教育规模快速扩张，城乡和地区之间的教育资源差距<mark>仍然显著</mark>。</p>
            <p className="is-rewrite"><i>105</i>现有研究亦表明，家庭社会经济地位与个体获得高等教育机会之间存在显著关联（李明，2021；Zhang, 2020）。</p>
            <p><i>109</i>These findings <mark>also</mark> suggest that equitable allocation is essential for promoting long-term social mobility.</p>
          </div>
        </article>
        <aside className="rtp-evidence-panel">
          <div className="rtp-panel-head"><b>{isEnglish ? 'Analysis & evidence' : '分析结果与证据'}</b><span>{isEnglish ? '31 checks' : '31 项检查'}</span></div>
          <div className="rtp-result-counters">
            <span><b>28</b>{isEnglish ? 'suggestions' : '修改建议'}</span>
            <span className="is-coral"><b>6</b>{isEnglish ? 'to review' : '需审阅'}</span>
            <span className="is-yellow"><b>3</b>{isEnglish ? 'term mismatches' : '术语不一致'}</span>
            <span className="is-green"><b>16/16</b>{isEnglish ? 'fact anchors kept' : '事实锚点保留'}</span>
          </div>
          <div className="rtp-preview-tabs" role="tablist" aria-label={isEnglish ? 'Workspace analysis views' : '工作台分析视图'}>
            {previewTabs.map((tab) => (
              <button
                key={tab.value}
                id={`rtp-preview-tab-${tab.value}`}
                type="button"
                role="tab"
                aria-selected={previewTab === tab.value}
                aria-controls="rtp-preview-panel"
                tabIndex={previewTab === tab.value ? 0 : -1}
                className={previewTab === tab.value ? 'is-active' : ''}
                onClick={() => setPreviewTab(tab.value)}
                onKeyDown={(event) => moveTabFocus(event, ['发现', '修改', '参考'], previewTab, setPreviewTab, 'rtp-preview-tab')}
              >{tab.label}</button>
            ))}
          </div>
          <div id="rtp-preview-panel" role="tabpanel" aria-labelledby={`rtp-preview-tab-${previewTab}`}>
            <div className="rtp-finding-card">
              <span className="rtp-finding-no">1</span>
              <div><b>{previewTab === '参考' ? (isEnglish ? 'Related evidence' : '相关证据') : previewTab === '修改' ? (isEnglish ? 'Reason for revision' : '修改理由') : (isEnglish ? 'Evidence scope' : '证据范围')}</b><p>{previewTab === '参考' ? 'OECD (2021). Education at a Glance.' : previewTab === '修改' ? (isEnglish ? 'Soften the causal claim that the source cannot support while preserving the citation position.' : '弱化无法由原文支持的因果关系，并保持引文位置。') : (isEnglish ? 'The conclusion concerns regional differences; add recent data or an authoritative report.' : '结论涉及地区差异，建议补充最新数据或权威报告。')}</p></div>
              <CaretDown weight="bold" />
            </div>
            <div className="rtp-finding-card">
              <span className="rtp-finding-no">2</span>
              <div><b>{isEnglish ? 'Causal boundaries' : '因果边界'}</b><p>{isEnglish ? 'This wording may overstate the inference. Distinguish correlation from causation.' : '当前表述存在推断过度风险，建议区分相关性与因果性。'}</p></div>
              <CaretDown weight="bold" />
            </div>
          </div>
        </aside>
      </div>
      <div className="rtp-preview-dock">
        <div><span>{isEnglish ? 'Rewrite strategy' : '改写策略'}</span><b>{isEnglish ? 'Balanced' : '平衡'}</b><small>{isEnglish ? 'Balance meaning and writing quality' : '兼顾原意与表达质量'}</small></div>
        <button className="rtp-btn rtp-btn-yellow" onClick={go(navigate, '/auth')}><ShieldCheck weight="bold" /> {isEnglish ? 'Safe cleanup' : '安全清理'}</button>
        <button className="rtp-btn rtp-btn-blue" onClick={go(navigate, '/auth')}><FileText weight="bold" /> {isEnglish ? 'Faithful rewrite' : '保真改写'} <ArrowRight weight="bold" /></button>
      </div>
    </section>
  );
}

export function LandingPage({ navigate }) {
  const { isEnglish } = useLocale();
  const { plans, config } = usePlatform();
  const paymentLive = config?.payment?.checkout_enabled === true && config.payment.live === true;
  const featuredMonth = plans.find((plan) => plan.kind === 'subscription');
  const featuredPack = plans.find((plan) => plan.kind === 'pack');
  return (
    <Shell navigate={navigate} active="首页">
      <main>
        <section className="rtp-hero">
          <div className="rtp-hero-copy">
            <span className="rtp-kicker"><Sparkle weight="fill" /> {isEnglish ? 'Bilingual academic writing workspace' : '中英文学术写作工作台'}</span>
            <h1>{isEnglish ? <>Keep your research.<br /><em>Rewrite the expression.</em></> : <>保留你的研究，<br /><em>重写表达方式。</em></>}</h1>
            <p>{isEnglish ? 'From structured diagnosis to item-by-item review, RightThesis refines mechanical phrasing, terminology drift, and argumentative boundaries—helping lower the AI-generation rate reported by common detectors and improve the chance of passing AI-generation checks while preserving facts, citations, and intent.' : '从结构化诊断到逐项审阅，RightThesis 帮你修改论文中的机械表达、术语漂移与论证边界，降低常见检测工具显示的 AI 生成率，提高通过 AI 生成检测的可能性，同时牢牢守住事实、引文与原意。'}</p>
            <div className="rtp-hero-actions">
              <button className="rtp-btn rtp-btn-blue rtp-btn-lg" onClick={go(navigate, '/auth')}>{isEnglish ? 'Analyze one for free' : '免费分析一篇'} <ArrowRight weight="bold" /></button>
              <button className="rtp-btn rtp-btn-paper rtp-btn-lg" onClick={() => document.getElementById('demo')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{isEnglish ? 'See how it works' : '看看怎么改'}</button>
            </div>
            <div className="rtp-hero-notes">
              <span><CheckCircle weight="fill" /> {isEnglish ? 'Chinese & English' : '中英双语'}</span>
              <span><CheckCircle weight="fill" /> {isEnglish ? 'Free analysis' : '分析免费'}</span>
              <span><CheckCircle weight="fill" /> {isEnglish ? 'Your conclusions stay yours' : '不改变研究结论'}</span>
            </div>
          </div>
          <img
            className="rtp-hero-stamp"
            src={isEnglish ? '/assets/rightthesis-facts-seal-en-green.png' : '/assets/rightthesis-facts-seal-green.png'}
            alt={isEnglish ? 'FACTS, not fluff: natural writing that stands up to review' : 'FACTS 不等于 FLUFF：写得自然，也经得起检查'}
          />
        </section>

        <div className="rtp-trust-ribbon">
          <span><ShieldCheck weight="bold" /> {isEnglish ? 'Fact-anchor protection' : '事实锚点守卫'}</span>
          <span><BookOpenText weight="bold" /> {isEnglish ? 'Citation-position tracking' : '引文位置追踪'}</span>
          <span><GlobeHemisphereWest weight="bold" /> {isEnglish ? 'Chinese / English' : '中文 / English'}</span>
          <span><SealCheck weight="bold" /> {isEnglish ? 'Every change has a reason' : '每一处修改有依据'}</span>
        </div>

        <section className="rtp-section" id="demo">
          <div className="rtp-section-heading rtp-heading-row">
            <div><span className="rtp-index-tag">{isEnglish ? '01 / WORKSPACE' : '01 / 工作台'}</span><h2>{isEnglish ? 'Not a one-click black box. A revision process you can review.' : '不是一键黑箱，是可审阅的修改现场。'}</h2></div>
            <p>{isEnglish ? 'Original text, revised text, and evidence appear side by side. See not only the result, but why it changed, what changed, and what still needs your confirmation.' : '原稿、改稿和证据并排呈现。你看到的不只是结果，还有为什么改、改了什么，以及哪些内容需要你亲自确认。'}</p>
          </div>
          <WorkbenchPreview navigate={navigate} />
        </section>

        <section className="rtp-section rtp-how" id="product">
          <div className="rtp-section-heading"><span className="rtp-index-tag">{isEnglish ? '02 / METHOD' : '02 / 方法'}</span><h2>{isEnglish ? 'Four steps from draft to final.' : '四步走完，从稿件到定稿。'}</h2></div>
          <div className="rtp-steps">
            {[
              [UploadSimple, '01', isEnglish ? 'Import your draft' : '导入稿件', isEnglish ? 'Paste text or upload a DOCX / PDF. Chapter and paragraph structure stays clear.' : '粘贴文本，或上传 DOCX / PDF。章节与段落结构保持清晰。'],
              [Scan, '02', isEnglish ? 'Diagnose issues' : '分析问题', isEnglish ? 'Flag mechanical phrasing, terminology drift, argumentative boundaries, and suspicious citation positions that may raise the reported AI-generation rate.' : '识别可能推高 AI 生成率的机械表达、术语漂移、论证边界与可疑引用位置。'],
              [PencilSimpleLine, '03', isEnglish ? 'Rewrite faithfully' : '保真改写', isEnglish ? 'Choose a conservative, balanced, or deep strategy while guards protect facts and key terms.' : '选择保守、平衡或深度策略；事实与关键术语受守卫保护。'],
              [Export, '04', isEnglish ? 'Review & export' : '审阅导出', isEnglish ? 'Review each diagnosed issue, compare the original and current drafts, then export an imported DOCX.' : '逐项复核诊断问题，对照原稿与当前稿，再导出已导入的 DOCX。'],
            ].map(([Icon, no, title, copy]) => (
              <article className="rtp-step" key={no}>
                <span className="rtp-step-no">{no}</span><Icon size={32} weight="bold" />
                <h3>{title}</h3><p>{copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="rtp-section rtp-values">
          <article className="rtp-value-card rtp-value-blue">
            <span>{isEnglish ? 'EXPLAINABLE' : '可解释'}</span><h3>{isEnglish ? <>Know where every<br />change comes from.</> : <>知道每个修改<br />从哪里来。</>}</h3>
            <p>{isEnglish ? 'Issue location, revision rationale, supporting evidence, and risk flags stay in one traceable chain.' : '问题定位、修改理由、相关证据和风险提示在同一条链路里。'}</p>
            <ListChecksArt />
          </article>
          <article className="rtp-value-card rtp-value-yellow">
            <span>{isEnglish ? 'BOUNDED' : '有边界'}</span><h3>{isEnglish ? <>Facts, numbers, citations:<br />protected by default.</> : <>事实、数字、引文，<br />默认不乱动。</>}</h3>
            <p>{isEnglish ? 'The goal is to reduce AI-detection risk, not decide authorship for you. The system presents only verifiable language and structural signals.' : '目标是降低 AI 生成检测风险，而不是替用户判定来源。系统只呈现可核查的语言与结构信号。'}</p>
            <ShieldCheck size={92} weight="duotone" />
          </article>
          <article className="rtp-value-card rtp-value-paper">
            <span>{isEnglish ? 'IN CONTROL' : '可控'}</span><h3>{isEnglish ? <>Your voice<br />stays in the lead.</> : <>你的声音，<br />仍然是主角。</>}</h3>
            <p>{isEnglish ? 'Three rewrite intensities, finding-by-finding diagnosis, and before/after comparison keep the result reviewable in the current workspace.' : '三档改写强度、逐项诊断与前后对照，让当前工作台中的结果保持可审阅。'}</p>
            <ClockCounterClockwise size={92} weight="duotone" />
          </article>
        </section>

        <section className="rtp-section rtp-price-preview">
          <div className="rtp-price-copy">
            <span className="rtp-index-tag">{isEnglish ? '03 / USAGE' : '03 / 用量'}</span>
            <h2>{isEnglish ? 'Choose credits at the pace you write.' : '按你的写作节奏选额度。'}</h2>
            <p>{isEnglish ? `The service catalog includes 30-day passes, standalone packs, and free access. ${paymentLive ? 'Secure checkout is available.' : 'Checkout is not enabled yet.'} The catalog below is the source of truth for configured limits.` : `服务端目录包含 30 天月卡、独立字数包与免费额度。${paymentLive ? '目前可通过安全收银台付款。' : '目前尚未开放收款。'}下方目录是当前配置上限的唯一来源。`}</p>
            <button className="rtp-text-link" onClick={go(navigate, '/pricing')}>{isEnglish ? 'See all plans' : '查看完整套餐'} <ArrowRight weight="bold" /></button>
          </div>
          <div className="rtp-mini-plans">
            <article><span>{isEnglish ? 'Current 30-day plan' : '当前 30 天月卡'}</span><b>{featuredMonth ? formatCredits(featuredMonth.credits, isEnglish) : '—'}</b><small>{featuredMonth ? (isEnglish ? 'characters · from the service catalog' : '字 · 来自服务端目录') : (isEnglish ? 'Loading service catalog' : '正在读取服务端目录')}</small></article>
            <span className="rtp-plus">+</span>
            <article><span>{isEnglish ? 'Current standalone pack' : '当前独立字数包'}</span><b>{featuredPack ? formatCredits(featuredPack.credits, isEnglish) : '—'}</b><small>{featuredPack ? (isEnglish ? `${featuredPack.valid_days} days · from the service catalog` : `${featuredPack.valid_days} 天 · 来自服务端目录`) : (isEnglish ? 'Loading service catalog' : '正在读取服务端目录')}</small></article>
          </div>
        </section>

        <section className="rtp-final-cta">
          <div><span>READY WHEN YOU ARE</span><h2>{isEnglish ? <>Bring in your paper.<br />Understand it before you edit.</> : <>把论文放进来，<br />先看清楚再动笔。</>}</h2></div>
          <button className="rtp-btn rtp-btn-blue rtp-btn-lg" onClick={go(navigate, '/auth')}>{isEnglish ? 'Sign in or register' : '登录或注册'} <ArrowRight weight="bold" /></button>
        </section>
      </main>
    </Shell>
  );
}

function ListChecksArt() {
  const { isEnglish } = useLocale();
  return (
    <div className="rtp-list-art" aria-hidden="true">
      <span><Check weight="bold" />{isEnglish ? 'Fact anchors preserved' : '事实锚点保留'}</span>
      <span><Check weight="bold" />{isEnglish ? 'Terminology stays consistent' : '术语前后一致'}</span>
      <span><Warning weight="bold" />{isEnglish ? 'Causal boundary needs review' : '因果边界待审阅'}</span>
    </div>
  );
}

function formatCredits(value, isEnglish) {
  return new Intl.NumberFormat(isEnglish ? 'en-US' : 'zh-CN').format(Number(value) || 0);
}

function formatPlanPrice(plan, isEnglish) {
  const price = Math.max(0, Number(plan.price_fen) || 0) / 100;
  return {
    currency: plan.currency === 'CNY' || !plan.currency ? '¥' : plan.currency,
    amount: new Intl.NumberFormat(isEnglish ? 'en-US' : 'zh-CN', {
      minimumFractionDigits: Number.isInteger(price) ? 0 : 1,
      maximumFractionDigits: 2,
    }).format(price),
  };
}

function planTone(plan) {
  if (plan.id === 'pro_month') return 'blue';
  if (plan.id === 'free' || plan.id === 'pack_10k') return 'yellow';
  return 'paper';
}

export function PricingPage({ navigate }) {
  const { isEnglish } = useLocale();
  const { plans, session, loading, error, refresh } = usePlatform();
  const [kind, setKind] = useState('month');
  const groupedPlans = useMemo(() => ({
    month: plans.filter((plan) => plan.kind === 'subscription'),
    pack: plans.filter((plan) => plan.kind !== 'subscription'),
  }), [plans]);
  const visiblePlans = groupedPlans[kind];
  const openPlan = (plan) => {
    if (plan.kind === 'free') return navigate('/app');
    const target = `/checkout/pro?plan=${encodeURIComponent(plan.id)}`;
    if (session?.authMode === 'accounts' && !session?.authenticated) {
      try {
        window.sessionStorage.setItem('rightthesis-auth-return', '/checkout/pro');
        window.sessionStorage.setItem('rightthesis-checkout-plan', plan.id);
      } catch {
        // Sign-in still works if browser storage is unavailable.
      }
      return navigate('/auth');
    }
    return navigate(target);
  };
  return (
    <Shell navigate={navigate} active="定价">
      <main className="rtp-inner-main">
        <section className="rtp-inner-hero rtp-pricing-hero">
          <span className="rtp-kicker"><Lightning weight="fill" /> {isEnglish ? 'Live service catalog' : '当前服务端目录'}</span>
          <h1>{isEnglish ? <>Current credits and limits,<br /><em>from one source.</em></> : <>当前额度与上限，<br /><em>直接来自服务端。</em></>}</h1>
          <p>{isEnglish ? 'Every price, credit amount, validity period, and per-document limit below is read from the connected backend. Analysis and deterministic safe cleanup do not use rewrite credits.' : '下方价格、额度、有效期和单篇上限均读取自当前后端。分析与确定性安全清理不消耗改写额度。'}</p>
          <div className="rtp-segmented" role="tablist" aria-label={isEnglish ? 'Choose plan type' : '切换套餐类型'}>
            <button id="rtp-pricing-tab-month" type="button" role="tab" aria-selected={kind === 'month'} aria-controls="rtp-pricing-panel" tabIndex={kind === 'month' ? 0 : -1} className={kind === 'month' ? 'is-active' : ''} onClick={() => setKind('month')} onKeyDown={(event) => moveTabFocus(event, ['month', 'pack'], kind, setKind, 'rtp-pricing-tab')}>{isEnglish ? '30-day plans' : '30 天套餐'}</button>
            <button id="rtp-pricing-tab-pack" type="button" role="tab" aria-selected={kind === 'pack'} aria-controls="rtp-pricing-panel" tabIndex={kind === 'pack' ? 0 : -1} className={kind === 'pack' ? 'is-active' : ''} onClick={() => setKind('pack')} onKeyDown={(event) => moveTabFocus(event, ['month', 'pack'], kind, setKind, 'rtp-pricing-tab')}>{isEnglish ? 'Packs & free access' : '字数包与免费额度'}</button>
          </div>
        </section>

        <section id="rtp-pricing-panel" role="tabpanel" aria-labelledby={`rtp-pricing-tab-${kind}`} className={`rtp-plan-grid ${visiblePlans.length === 2 ? 'is-two' : ''}`} aria-live="polite">
          {loading && !plans.length ? (
            <div className="rtp-plan-status"><Lightning size={30} weight="fill" /><h2>{isEnglish ? 'Loading the service catalog…' : '正在读取服务端套餐…'}</h2><p>{isEnglish ? 'No placeholder prices are shown while the backend responds.' : '后端返回前不显示任何占位价格。'}</p></div>
          ) : visiblePlans.length ? visiblePlans.map((plan) => {
            const price = formatPlanPrice(plan, isEnglish);
            const tone = planTone(plan);
            const isFree = plan.kind === 'free';
            return (
              <article className={`rtp-plan-card rtp-plan-${tone}`} key={plan.id}>
                <span className="rtp-plan-type">{plan.kind === 'subscription' ? '30-DAY PLAN' : isFree ? 'FREE ACCESS' : 'CREDIT PACK'}</span>
                <h2>{planName(plan, isEnglish)}</h2>
                <div className="rtp-plan-price"><small>{price.currency}</small>{price.amount}<span>{isFree ? (isEnglish ? ' / included' : ' / 当前免费额度') : plan.kind === 'subscription' ? (isEnglish ? ` / ${plan.valid_days} days` : ` / ${plan.valid_days} 天`) : (isEnglish ? ' / configured pack' : ' / 服务端字数包')}</span></div>
                <div className="rtp-plan-amount"><b>{formatCredits(plan.credits, isEnglish)}</b><span>{isEnglish ? 'rewrite characters' : '字改写额度'}</span></div>
                <ul>
                  <li><Check weight="bold" />{isEnglish ? `Up to ${formatCredits(plan.max_chars_per_job, true)} characters per task` : `单次上限 ${formatCredits(plan.max_chars_per_job, false)} 字`}</li>
                  <li><Check weight="bold" />{plan.valid_days ? (isEnglish ? `Configured validity: ${plan.valid_days} days` : `配置有效期：${plan.valid_days} 天`) : (isEnglish ? 'No configured expiry' : '当前未设置到期时间')}</li>
                  <li><Check weight="bold" />{isEnglish ? 'Works with Chinese and English' : '中英文均可使用'}</li>
                  <li><Check weight="bold" />{isFree ? (isEnglish ? 'Conservative rewrite mode' : '开放保守改写模式') : (isEnglish ? 'Conservative, balanced, and deep modes' : '保守、平衡与深度模式')}</li>
                </ul>
                <p>{planDescription(plan, isEnglish)}</p>
                <button className={`rtp-btn ${tone === 'blue' ? 'rtp-btn-yellow' : 'rtp-btn-blue'}`} onClick={() => openPlan(plan)} disabled={loading || !session?.ready}>
                  {isFree ? (isEnglish ? 'Open workspace' : '进入工作台') : session?.authMode === 'accounts' && !session?.authenticated ? (isEnglish ? 'Sign in to buy' : '登录后购买') : (isEnglish ? 'Pay' : '支付')} <ArrowRight weight="bold" />
                </button>
              </article>
            );
          }) : (
            <div className="rtp-plan-status rtp-plan-status-error"><Warning size={30} weight="fill" /><h2>{isEnglish ? 'This catalog is unavailable.' : '当前无法读取套餐目录。'}</h2><p>{error || (isEnglish ? 'The service returned no plans. No substitute prices are shown.' : '服务端未返回套餐，页面不会用模拟价格代替。')}</p><button className="rtp-btn rtp-btn-paper" type="button" onClick={refresh}>{isEnglish ? 'Retry' : '重新读取'}</button></div>
          )}
        </section>

        <section className="rtp-credit-rules">
          <div className="rtp-section-heading"><span className="rtp-index-tag">{isEnglish ? 'HOW CREDITS WORK' : '额度怎么用'}</span><h2>{isEnglish ? 'Clear accounting makes confident revision.' : '账算得明白，修改才安心。'}</h2></div>
          <div className="rtp-rule-grid">
            <article><b>01</b><h3>{isEnglish ? 'One server-side catalog' : '以服务端目录为准'}</h3><p>{isEnglish ? 'Plan names, prices, credits, validity, and per-task limits are rendered directly from the backend response.' : '套餐名称、价格、额度、有效期和单次上限均直接渲染后端返回值。'}</p></article>
            <article><b>02</b><h3>{isEnglish ? 'Count non-whitespace characters' : '按非空白字符计量'}</h3><p>{isEnglish ? 'Chinese and English are both measured by normalized non-whitespace characters, not file size or page count.' : '中英文统一按归一化后的非空白字符数计算，不按文件大小或页数。'}</p></article>
            <article><b>03</b><h3>{isEnglish ? 'Reserve credits before model work' : '模型处理前预占额度'}</h3><p>{isEnglish ? 'Estimated usage appears after you choose a strategy. Deep mode reserves 1.5× credits. Credits are usage units, not a live-payment event.' : '选择策略后展示预计消耗；深度模式预占 1.5 倍额度。额度是使用量单位，不代表真实支付。'}</p></article>
            <article><b>04</b><h3>{isEnglish ? 'Failed tasks release credits' : '失败任务释放额度'}</h3><p>{isEnglish ? 'If a task fails or no candidate is accepted, reserved credits are released back to the current service session.' : '任务失败或没有任何候选被采纳时，预占额度会释放回当前服务会话。'}</p></article>
          </div>
        </section>

        <section className="rtp-faq-strip">
          <div><h2>{isEnglish ? 'More credit questions?' : '还有额度问题？'}</h2><p>{isEnglish ? 'See details about configured credits, validity periods, and failed tasks.' : '查看服务端额度、有效期和任务失败的详细说明。'}</p></div>
          <button className="rtp-btn rtp-btn-paper" onClick={go(navigate, '/help')}>{isEnglish ? 'Go to help center' : '前往帮助中心'} <ArrowRight weight="bold" /></button>
        </section>
      </main>
    </Shell>
  );
}

export const AuthPage = AccountAuthPage;

function LegacyAuthPage({ navigate, statePath }) {
  const { isEnglish } = useLocale();
  const { session, loading, error, refresh } = usePlatform();
  const isVerifyRoute = statePath === '/auth/verify';
  const isTrial = Boolean(session?.trialMode);
  const trialReady = isTrial && Boolean(session?.authenticated);
  const statusTitle = loading
    ? (isEnglish ? 'Checking current access…' : '正在检查当前访问方式…')
    : error
      ? (isEnglish ? 'Service status is unavailable.' : '暂时无法获取服务状态。')
      : isTrial
        ? (trialReady ? (isEnglish ? 'Anonymous trial is ready.' : '匿名试用已就绪。') : (isEnglish ? 'Anonymous trial is not ready.' : '匿名试用尚未就绪。'))
        : (isEnglish ? 'Local workspace access is ready.' : '本地工作台可直接访问。');
  const statusCopy = error
    ? error
    : isTrial
      ? (isEnglish ? 'The service creates a browser-specific anonymous session. It is not an email account and does not sync across devices.' : '服务会为当前浏览器建立匿名会话。这不是邮箱账户，也不会跨设备同步。')
      : (isEnglish ? 'This build uses a local single-user workspace. Production identity, password recovery, and cross-device sync are still pending.' : '当前版本使用本地单用户工作台。生产级账户、密码找回与跨设备同步尚未接入。');

  return (
    <div className="rtp-auth-page">
      <div className="rtp-auth-brand"><Brand navigate={navigate} /></div>
      <section className="rtp-auth-aside">
        <span className="rtp-kicker"><SealCheck weight="fill" /> {isEnglish ? 'Current access, clearly stated' : '如实说明当前访问方式'}</span>
        <h1>{isEnglish ? <>Enter the workspace.<br /><em>No pretend account.</em></> : <>直接进入工作台，<br /><em>不模拟已上线的账户。</em></>}</h1>
        <p>{isEnglish ? 'Email/password registration and verification are not implemented in this build. Access is either local single-user mode or a browser-specific anonymous trial, as reported by the connected service.' : '当前版本尚未实现邮箱密码注册与验证。实际访问方式由已连接服务返回：本地单用户，或当前浏览器的匿名试用。'}</p>
        <div className="rtp-auth-paper">
          <span>{isEnglish ? 'CURRENT ACCESS BOUNDARY' : '当前访问边界 / CURRENT ACCESS'}</span>
          <p><Check weight="bold" /> {isEnglish ? 'No email or password is collected here' : '本页不收集邮箱或密码'}</p>
          <p><Check weight="bold" /> {isEnglish ? 'Workspace access comes from the current service session' : '工作台访问以当前服务会话为准'}</p>
          <p><Warning weight="bold" /> {isEnglish ? 'No production account or cross-device sync yet' : '尚无生产账户与跨设备同步'}</p>
        </div>
      </section>
      <main className="rtp-auth-main">
        <div className="rtp-auth-card rtp-access-card">
          <div className="rtp-auth-heading">
            <span>{isVerifyRoute ? 'IDENTITY STATUS' : 'ACCESS STATUS'}</span>
            <h2>{isVerifyRoute ? (isEnglish ? 'Email verification is not enabled.' : '邮箱验证尚未启用。') : statusTitle}</h2>
            <p>{isVerifyRoute ? (isEnglish ? 'This route is reserved for a future production identity system. No code has been sent or accepted in the current build.' : '该路由为未来的生产身份系统保留；当前版本不会发送或接受验证码。') : statusCopy}</p>
          </div>
          <div className={`rtp-access-status ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
            {error ? <Warning size={36} weight="fill" /> : <ShieldCheck size={36} weight="fill" />}
            <strong>{isVerifyRoute ? (isEnglish ? 'Production identity pending' : '生产身份系统待接入') : statusTitle}</strong>
            <span>{isVerifyRoute ? statusCopy : (isEnglish ? 'Continue with the access mode currently provided by the service.' : '请使用服务端当前提供的访问方式继续。')}</span>
            <ul>
              <li><Check weight="bold" /> {isEnglish ? 'No email, password, or verification code is submitted here' : '本页不提交邮箱、密码或验证码'}</li>
              <li><Check weight="bold" /> {isEnglish ? 'No claim of cross-device document or version sync' : '不承诺文档或版本的跨设备同步'}</li>
              <li><Check weight="bold" /> {isEnglish ? 'Live payment is not connected' : '真实支付尚未接入'}</li>
            </ul>
            <div className="rtp-access-actions">
              <button className="rtp-btn rtp-btn-blue rtp-btn-full" type="button" onClick={go(navigate, '/app')}>{isEnglish ? 'Enter workspace' : '进入工作台'} <ArrowRight weight="bold" /></button>
              {error && <button className="rtp-btn rtp-btn-paper rtp-btn-full" type="button" onClick={refresh}>{isEnglish ? 'Retry service status' : '重新读取服务状态'}</button>}
            </div>
          </div>
          <p className="rtp-access-note">{isEnglish ? 'Production identity can be added later without pretending it is already available today.' : '生产级身份可以在后续接入，但不会在今天被描述成已经上线。'}</p>
        </div>
        <button className="rtp-auth-back" onClick={go(navigate, '/')}>← {isEnglish ? 'Back to home' : '返回首页'}</button>
      </main>
    </div>
  );
}

const privacySections = [
  ['我们处理哪些信息', '注册与登录时，账户服务会处理邮箱、显示名称、邮箱验证状态、登录方式和会话安全信息；Google 登录会接收账户授权的基本身份信息。使用工作台时，服务还会处理文档内容、处理请求和额度使用。', 'Information we process', 'During registration and sign-in, the account service processes your email, display name, verification status, sign-in method, and session-security information. Google sign-in provides the basic identity information you authorize. The workspace also processes document content, processing requests, and credit usage.'],
  ['信息如何使用', '这些信息用于账户验证与恢复、会话安全、文档解析、分析、改写任务、额度核算和故障排查。已保存的文稿和任务与账户关联，可在同一账户中恢复；仍请自行保留原稿和导出成果。', 'How we use information', 'Information is used for account verification and recovery, session security, document parsing, analysis, rewrite jobs, credit accounting, and troubleshooting. Saved manuscripts and jobs are linked to your account and can be restored when you sign in again. Keep your own copies of originals and exports.'],
  ['文档与保留边界', '浏览器可能保留轻量工作台状态；已保存的文稿、导入文件内容、改写任务和额度记录存放在平台服务器的账户数据库中。文稿在账户使用期间保留；可在隐私设置提交删除申请，由人工核对运行任务、待确认付款和未用付费额度后处理。服务器会制作加密备份，已删除内容可能在备份轮换前继续存在；请勿提交不必要的敏感信息。', 'Documents and retention boundaries', 'The browser may keep lightweight workspace state. Saved manuscripts, imported content, rewrite jobs, and credit records are stored in an account-scoped server database. Manuscripts remain while the account is active. A deletion request can be submitted in privacy settings and is reviewed against running jobs, pending payments and unused paid credits. The server creates encrypted backups; deleted content may remain in backups until they rotate. Do not submit unnecessary sensitive information.'],
  ['第三方服务', 'Google 登录由 Google OAuth 提供，邮箱验证与恢复邮件由平台配置的邮件服务发送。只有在你主动启动模型改写时，相关文本才会发送给平台配置的模型服务。服务器由阿里云托管；在结账功能启用时，付款由 Stripe 收银台处理，平台保存订单、付款状态与额度记录，不接收完整银行卡号。', 'Third-party services', 'Google sign-in is provided through Google OAuth, while verification and recovery messages are sent through the configured email service. Relevant text is sent to the configured model service only when you actively start a rewrite. Our server is hosted by Alibaba Cloud. When checkout is enabled, Stripe processes payments and we retain orders, payment status, and credit records; we do not receive complete card numbers.'],
  ['你的选择', '登录后可在隐私设置下载账户数据或提交、取消账户删除申请。删除申请不是即时删除；完成后文稿、任务与登录身份会移除，财务记录仍以去身份化账户标识保留用于对账。', 'Your choices', 'After signing in, you can download account data or submit and cancel a deletion request in privacy settings. A request is not immediate deletion. Once fulfilled, manuscripts, jobs and sign-in identity are removed; financial records remain under a pseudonymous account ID for reconciliation.'],
  ['政策更新', '产品能力或适用规则变化时，本页面会标注最新生效日期；具体提示方式以当时产品实际提供的能力为准。', 'Policy updates', 'When product capabilities or applicable rules change, this page will show the latest effective date. The way we notify you will depend on the capabilities the product provides at that time.'],
];

const termsSections = [
  ['服务范围', 'RightThesis 提供文本分析、写作建议、保真改写和前后对照工具。输出仅用于辅助写作与编辑，不构成学术评价、法律意见或学校审核结论。', 'Scope of service', 'RightThesis provides text analysis, writing suggestions, faithful rewriting, and before/after review tools. Its output supports writing and editing only and does not constitute an academic assessment, legal advice, or a school’s review decision.'],
  ['当前访问资格', '平台可提供 Google 登录与经过验证的邮箱密码账户；在明确开启试用模式时，也可能提供当前浏览器的匿名会话。不得通过自动化攻击、绕过限额或干扰他人使用。', 'Current access and eligibility', 'The platform may provide Google sign-in and verified email/password accounts. When trial mode is explicitly enabled, it may also provide a browser-specific anonymous session. You may not conduct automated attacks, bypass limits, or interfere with other people’s use of the service.'],
  ['学术诚信', '你应遵守所在学校、期刊或机构的学术诚信与 AI 使用政策。平台不会代替作者完成事实核验、来源核查或署名判断。', 'Academic integrity', 'You must follow the academic-integrity and AI-use policies of your school, journal, or institution. The platform does not replace the author’s responsibility to verify facts, check sources, or make authorship decisions.'],
  ['内容责任', '你确认有权上传和处理相关文本。请在提交前移除不必要的敏感信息，并在导出前审阅所有修改、数字、引用和术语。', 'Responsibility for content', 'You confirm that you have the right to upload and process the relevant text. Remove unnecessary sensitive information before submitting it, and review every revision, number, citation, and term before exporting.'],
  ['套餐、付款与退款', '定价页展示服务端当前的价格、额度、有效期和单次上限。仅在结账功能启用且你主动确认付款时才会真实扣款；30 天月卡为一次购买，不自动续费。退款申请可联系 support@righttoken.ai；是否退款需依适用法律和具体订单情况核对。Stripe 确认成功退款后，平台按累计退款金额调整该订单未使用的额度；已消耗额度无法追回。银行卡争议仍需人工核对。', 'Plans, payments, and refunds', 'The pricing page shows current server-side prices, credits, validity periods, and per-task limits. A real charge occurs only when checkout is enabled and you confirm payment. A 30-day pass is a one-time purchase, not an auto-renewing subscription. Contact support@righttoken.ai about a refund; eligibility depends on applicable law and the order. After Stripe confirms a successful refund, unused credits from that order are adjusted in proportion to the cumulative refunded amount. Spent credits cannot be recovered. Card disputes still require manual review.'],
  ['服务变化', '测试阶段的模型、额度与功能可能调整。页面只描述当前实际可用或明确标为预览的能力，不保证未上线功能的时间表。', 'Changes to the service', 'Models, credits, and features may change during testing. Pages describe only capabilities that are currently available or explicitly marked as previews, and do not guarantee a timeline for unreleased features.'],
];

function LegalPage({ navigate, type }) {
  const { isEnglish } = useLocale();
  const isPrivacy = type === 'privacy';
  const sections = isPrivacy ? privacySections : termsSections;
  return (
    <Shell navigate={navigate}>
      <main className="rtp-legal-main">
        <aside className="rtp-legal-aside">
          <span className="rtp-kicker">{isPrivacy ? <LockKey weight="fill" /> : <Article weight="fill" />} {isPrivacy ? 'PRIVACY' : 'TERMS'}</span>
          <h1>{isPrivacy ? (isEnglish ? 'Privacy Policy' : '隐私政策') : (isEnglish ? 'Terms of Service' : '服务条款')}</h1>
          <p>{isEnglish ? 'Updated: October 16, 2026' : '更新日期：2026 年 10 月 16 日'}</p>
          <div className="rtp-legal-note"><ShieldCheck weight="bold" /><span>{isPrivacy ? (isEnglish ? 'This policy describes actual data practices without promising features that do not yet exist.' : '只描述实际处理方式，不把尚未实现的能力写成承诺。') : (isEnglish ? 'Pay special attention to academic integrity, content responsibility, and plan details.' : '请特别留意学术诚信、内容责任与套餐说明。')}</span></div>
          <button className="rtp-btn rtp-btn-paper" onClick={go(navigate, '/help')}>{isEnglish ? 'Questions? Visit help' : '有问题？联系帮助'} <ArrowRight /></button>
        </aside>
        <article className="rtp-legal-document">
          <header><span>RightThesis / {isPrivacy ? (isEnglish ? 'Privacy Policy' : '隐私政策') : (isEnglish ? 'Terms of Service' : '服务条款')}</span><b>{isEnglish ? 'Version 1.1' : '版本 1.1'}</b></header>
          <p className="rtp-legal-intro">{isEnglish ? 'This notice explains, in clear and restrained language, what you need to know when using RightThesis. The product is still in testing, so planned features are not described as already available.' : '本说明以清楚、克制的语言介绍你在使用 RightThesis 时需要了解的事项。产品仍处于测试阶段，文中不会将计划中的功能描述为已经提供。'}</p>
          {sections.map(([title, copy, titleEn, copyEn], index) => (
            <section key={title}><span>{String(index + 1).padStart(2, '0')}</span><div><h2>{isEnglish ? titleEn : title}</h2><p>{isEnglish ? copyEn : copy}</p></div></section>
          ))}
        </article>
      </main>
    </Shell>
  );
}

export function PrivacyPage({ navigate }) {
  return <LegalPage navigate={navigate} type="privacy" />;
}

export function TermsPage({ navigate }) {
  return <LegalPage navigate={navigate} type="terms" />;
}

const helpItems = [
  { category: '开始使用', categoryEn: 'Getting started', q: '支持哪些文件和语言？', qEn: 'Which files and languages are supported?', a: '可粘贴文本，或上传 TXT / DOCX / PDF；中文和英文均可诊断，并在守卫允许的范围内改写。纯图片扫描版 PDF 暂不支持，请先运行 OCR。', aEn: 'Paste text or upload TXT, DOCX, or PDF. Chinese and English can both be diagnosed and rewritten where the safeguards allow it. Image-only scanned PDFs are not supported; run OCR first.' },
  { category: '开始使用', categoryEn: 'Getting started', q: '分析和改写有什么区别？', qEn: 'What is the difference between analysis and rewriting?', a: '分析用于定位表达、术语和论证边界问题；改写会生成修改候选并消耗相应额度。你可以只分析，不进行改写。', aEn: 'Analysis locates issues in expression, terminology, and argumentative boundaries. Rewriting creates revision candidates and uses the corresponding credits. You can run an analysis without rewriting.' },
  { category: '修改与审阅', categoryEn: 'Revision & review', q: '系统会改变我的事实或引用吗？', qEn: 'Will the system change my facts or citations?', a: '保真守卫会优先保护数字、专有名词、引用位置和关键事实。任何自动系统都不能替代作者复核，因此高风险项目会明确标记为“需审阅”。', aEn: 'Faithfulness guards prioritize numbers, proper nouns, citation positions, and key facts. No automated system can replace author review, so high-risk items are clearly marked “Needs review.”' },
  { category: '修改与审阅', categoryEn: 'Revision & review', q: '能保证通过 AI 生成检测吗？', qEn: 'Can you guarantee that my paper will pass AI-generation checks?', a: '不能保证固定分数或必然通过。RightThesis 的目标是降低常见检测工具显示的 AI 生成率、提高通过检测的可能性；结果会随检测工具、版本、语言与学科而变化。', aEn: 'No fixed score or guaranteed pass is possible. RightThesis aims to lower the AI-generation rate reported by common detectors and improve the likelihood of passing, but results vary by detector, version, language, and discipline.' },
  { category: '额度与套餐', categoryEn: 'Credits & plans', q: '月卡和字数包能同时用吗？', qEn: 'Can I use a pass and a character pack together?', a: '可以。两类额度可以同时持有，系统会优先使用更早到期的额度，并在每次任务开始前展示预计消耗。', aEn: 'Yes. You can hold both credit types at once. Credits that expire sooner are used first, and estimated usage appears before every task begins.' },
  { category: '额度与套餐', categoryEn: 'Credits & plans', q: '任务失败还会扣额度吗？', qEn: 'Do failed tasks use credits?', a: '不会。任务创建时会预占额度；失败或没有候选被采纳时会释放。每次确认前的额度预览与额度账本是当前规则的核对依据。', aEn: 'No. Credits are reserved when a task is created, then released if it fails or no candidate is accepted. The pre-confirmation usage preview and credit ledger are the current sources of truth.' },
  { category: '账户与安全', categoryEn: 'Account & security', q: '需要我配置模型服务吗？', qEn: 'Do I need to configure a model service?', a: '不需要。模型服务由 RightThesis 统一配置和维护，你只需要选择适合稿件的改写策略。', aEn: 'No. RightThesis configures and maintains the model service. You only need to choose the rewriting strategy that suits your draft.' },
  { category: '账户与安全', categoryEn: 'Account & security', q: '如何处理账户或文档问题？', qEn: 'How do I resolve an account or document issue?', a: '可以先查看任务状态与版本历史。当前版本尚未接入客服提交渠道；请记录任务时间和文件类型，且不要在任何反馈中粘贴密码、Key 或敏感凭证。', aEn: 'First check the task status and version history. A support-submission channel is not connected yet; record the task time and file type, and never include passwords, API keys, or sensitive credentials in feedback.' },
];

export function HelpPage({ navigate }) {
  const { isEnglish } = useLocale();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('全部');
  const [open, setOpen] = useState(0);
  const categories = ['全部', ...new Set(helpItems.map((item) => item.category))];
  const filtered = useMemo(() => helpItems.filter((item) => {
    const categoryMatch = category === '全部' || item.category === category;
    const queryMatch = !query.trim() || `${isEnglish ? item.qEn : item.q}${isEnglish ? item.aEn : item.a}`.toLowerCase().includes(query.trim().toLowerCase());
    return categoryMatch && queryMatch;
  }), [category, isEnglish, query]);
  const categoryLabel = (value) => {
    if (!isEnglish) return value;
    if (value === '全部') return 'All topics';
    return helpItems.find((item) => item.category === value)?.categoryEn || value;
  };

  return (
    <Shell navigate={navigate} active="帮助">
      <main className="rtp-inner-main rtp-help-main">
        <section className="rtp-help-hero">
          <span className="rtp-kicker"><BookOpenText weight="fill" /> {isEnglish ? 'Help center' : '帮助中心'}</span>
          <h1>{isEnglish ? <>Find the answer.<br /><em>Keep writing.</em></> : <>先找到答案，<br /><em>再继续写作。</em></>}</h1>
          <div className="rtp-help-search"><MagnifyingGlass weight="bold" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isEnglish ? 'Search files, rewriting, credits, or accounts' : '搜索文件、改写、额度或账户问题'} aria-label={isEnglish ? 'Search help content' : '搜索帮助内容'} />{query && <button onClick={() => setQuery('')} aria-label={isEnglish ? 'Clear search' : '清空搜索'}><X /></button>}</div>
          <div className="rtp-help-quick">
            <button onClick={go(navigate, '/app')}><FileText weight="bold" /> {isEnglish ? 'Open workspace' : '打开工作台'} <ArrowRight /></button>
            <button onClick={go(navigate, '/pricing')}><Lightning weight="bold" /> {isEnglish ? 'View plans' : '查看套餐'} <ArrowRight /></button>
          </div>
        </section>
        <section className="rtp-help-content">
          <aside>
            <span>{isEnglish ? 'Browse by topic' : '按主题浏览'}</span>
            {categories.map((item) => <button key={item} type="button" aria-pressed={category === item} className={category === item ? 'is-active' : ''} onClick={() => { setCategory(item); setOpen(-1); }}>{categoryLabel(item)}<span>{item === '全部' ? helpItems.length : helpItems.filter((x) => x.category === item).length}</span></button>)}
          </aside>
          <div className="rtp-faq-list">
            <div className="rtp-faq-head"><div><span>{categoryLabel(category)}</span><h2>{query ? (isEnglish ? `Results for “${query}”` : `“${query}”的搜索结果`) : (isEnglish ? 'Frequently asked questions' : '常见问题')}</h2></div><b>{isEnglish ? `${filtered.length} ${filtered.length === 1 ? 'item' : 'items'}` : `${filtered.length} 条`}</b></div>
            {filtered.length ? filtered.map((item) => {
              const actualIndex = helpItems.indexOf(item);
              const isOpen = open === actualIndex;
              return <article className={isOpen ? 'is-open' : ''} key={item.q}><button id={`rtp-faq-button-${actualIndex}`} type="button" onClick={() => setOpen(isOpen ? -1 : actualIndex)} aria-expanded={isOpen} aria-controls={`rtp-faq-answer-${actualIndex}`}><span><small>{isEnglish ? item.categoryEn : item.category}</small><b>{isEnglish ? item.qEn : item.q}</b></span><CaretDown weight="bold" /></button>{isOpen && <p id={`rtp-faq-answer-${actualIndex}`} role="region" aria-labelledby={`rtp-faq-button-${actualIndex}`}>{isEnglish ? item.aEn : item.a}</p>}</article>;
            }) : <div className="rtp-empty-search"><MagnifyingGlass size={32} /><h3>{isEnglish ? 'No direct answer found' : '没有找到直接答案'}</h3><p>{isEnglish ? 'Try another keyword or browse all questions.' : '换一个关键词试试，或浏览“全部”问题。'}</p><button className="rtp-btn rtp-btn-paper" onClick={() => { setQuery(''); setCategory('全部'); }}>{isEnglish ? 'View all questions' : '查看全部问题'}</button></div>}
          </div>
        </section>
        <section className="rtp-help-contact">
          <div><span>{isEnglish ? 'Still stuck?' : '仍然卡住了？'}</span><h2>{isEnglish ? 'Bring the task details. We’ll troubleshoot together.' : '带上任务信息，我们一起排查。'}</h2><p>{isEnglish ? 'Share the time, file type, and on-screen message. Do not send passwords, sign-in credentials, or unnecessary personal information.' : '描述发生时间、文件类型和屏幕提示即可；请不要发送密码、登录凭据或不必要的个人信息。'}</p></div>
          <button className="rtp-btn rtp-btn-yellow" onClick={go(navigate, '/app')}>{isEnglish ? 'Back to workspace' : '回到工作台'} <ArrowRight weight="bold" /></button>
        </section>
      </main>
    </Shell>
  );
}
