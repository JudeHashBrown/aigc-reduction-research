import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowSquareOut,
  BookOpenText,
  CaretDown,
  ChartLineUp,
  ClockCounterClockwise,
  Coins,
  Command,
  FileText,
  Gauge,
  GearSix,
  House,
  Lifebuoy,
  ListBullets,
  LockKey,
  Receipt,
  ShieldCheck,
  SignOut,
  UserCircle,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import {
  LandingPage,
  PricingPage,
  AuthPage,
  PrivacyPage,
  TermsPage,
  HelpPage,
} from "./pages/PublicPages.jsx";
import {
  DashboardPage,
  NewDocumentPage,
  WorkbenchPage,
  VersionsPage,
} from "./pages/LiveCorePages.jsx";
import {
  BillingPage,
  UsagePage,
  OrdersPage,
  CheckoutPage,
  AccountSettingsPage,
  PrivacySettingsPage,
  ServiceStatusPage,
  AdminOverviewPage,
  AdminUsersPage,
  AdminJobsPage,
  AdminPlansPage,
  AdminOrdersPage,
  AdminEconomicsPage,
  AdminServicePage,
  AdminPrivacyPage,
  SystemStatePage,
} from "./pages/OperationsPages.jsx";
import { LanguageToggle, useLocale } from "./locale.jsx";
import { getWorkspace, logoutSession, usePlatform } from "./platform.jsx";
import "./pages/public-pages.css";
import "./pages/core-pages.css";
import "./pages/operations-pages.css";

const pageGroups = [
  {
    label: "Public",
    items: [
      ["品牌首页", "/"],
      ["定价", "/pricing"],
      ["登录与注册", "/auth"],
      ["邮箱验证", "/auth/verify"],
      ["忘记密码", "/auth/forgot"],
      ["隐私与数据", "/legal/privacy"],
      ["服务条款", "/legal/terms"],
      ["帮助中心", "/help"],
    ],
  },
  {
    label: "Core",
    items: [
      ["文档首页", "/app"],
      ["新建与导入", "/app/new"],
      ["保真优化工作台", "/app/documents/rt-014"],
      ["版本与任务历史", "/app/documents/rt-014/versions"],
    ],
  },
  {
    label: "Money",
    items: [
      ["我的权益", "/app/billing"],
      ["额度明细", "/app/billing/usage"],
      ["订单与月卡", "/app/billing/orders"],
      ["支付确认", "/checkout/pro"],
    ],
  },
  {
    label: "Account",
    items: [
      ["账号设置", "/app/settings/account"],
      ["数据管理", "/app/settings/privacy"],
      ["服务状态", "/app/settings/service"],
    ],
  },
  {
    label: "Admin",
    items: [
      ["运营总览", "/admin"],
      ["用户", "/admin/users"],
      ["改写任务", "/admin/jobs"],
      ["套餐配置", "/admin/plans"],
      ["订单与对账", "/admin/orders"],
      ["成本与毛利", "/admin/economics"],
      ["服务控制", "/admin/service"],
      ["隐私审计", "/admin/privacy"],
    ],
  },
  {
    label: "System",
    items: [
      ["页面未找到", "/404"],
      ["服务错误", "/500"],
      ["离线", "/offline"],
      ["维护中", "/maintenance"],
      ["会话过期", "/session-expired"],
      ["额度不足", "/insufficient-balance"],
    ],
  },
];

const routeTitles = Object.fromEntries(pageGroups.flatMap((group) => group.items.map(([label, path]) => [path, label])));
const routeTitlesEnglish = {
  "/": "Home",
  "/pricing": "Pricing",
  "/auth": "Sign in / Register",
  "/auth/verify": "Email verification",
  "/auth/forgot": "Password recovery",
  "/legal/privacy": "Privacy & data",
  "/legal/terms": "Terms of service",
  "/help": "Help center",
  "/app": "Documents",
  "/app/new": "New import",
  "/app/documents/rt-014": "Faithful rewrite workspace",
  "/app/documents/rt-014/versions": "Versions & tasks",
  "/app/billing": "Plans & balance",
  "/app/billing/usage": "Usage ledger",
  "/app/billing/orders": "Orders & passes",
  "/checkout/pro": "Checkout",
  "/app/settings/account": "Account settings",
  "/app/settings/privacy": "Privacy controls",
  "/app/settings/service": "Service status",
  "/admin": "Operations overview",
  "/admin/users": "Users",
  "/admin/jobs": "Rewrite jobs",
  "/admin/plans": "Plan settings",
  "/admin/orders": "Orders & reconciliation",
  "/admin/economics": "Unit economics",
  "/admin/service": "Service controls",
  "/admin/privacy": "Privacy audit",
  "/404": "Page not found",
  "/500": "Service error",
  "/offline": "Offline",
  "/maintenance": "Maintenance",
  "/session-expired": "Session expired",
  "/insufficient-balance": "Insufficient balance",
};

function currentRoute() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash && ["/legal/privacy", "/legal/terms"].includes(window.location.pathname)) {
    return window.location.pathname;
  }
  return (hash || "/").split("?")[0];
}

const routeComponents = {
  "/": LandingPage,
  "/pricing": PricingPage,
  "/auth": AuthPage,
  "/auth/verify": AuthPage,
  "/auth/forgot": AuthPage,
  "/legal/privacy": PrivacyPage,
  "/legal/terms": TermsPage,
  "/help": HelpPage,
  "/app": DashboardPage,
  "/app/new": NewDocumentPage,
  "/app/documents/rt-014": WorkbenchPage,
  "/app/documents/rt-014/versions": VersionsPage,
  "/app/billing": BillingPage,
  "/app/billing/usage": UsagePage,
  "/app/billing/orders": OrdersPage,
  "/checkout/pro": CheckoutPage,
  "/app/settings/account": AccountSettingsPage,
  "/app/settings/privacy": PrivacySettingsPage,
  "/app/settings/service": ServiceStatusPage,
  "/admin": AdminOverviewPage,
  "/admin/users": AdminUsersPage,
  "/admin/jobs": AdminJobsPage,
  "/admin/plans": AdminPlansPage,
  "/admin/orders": AdminOrdersPage,
  "/admin/economics": AdminEconomicsPage,
  "/admin/service": AdminServicePage,
  "/admin/privacy": AdminPrivacyPage,
};

const appNavigation = [
  ["工作台", "Workspace", "/app/documents/rt-014", Gauge],
  ["文档", "Documents", "/app", FileText],
  ["版本历史", "Versions", "/app/documents/rt-014/versions", ClockCounterClockwise],
  ["套餐与用量", "Plans & usage", "/app/billing", Coins],
  ["账号设置", "Account", "/app/settings/account", GearSix],
];

const adminNavigation = [
  ["运营总览", "Overview", "/admin", ChartLineUp],
  ["用户", "Users", "/admin/users", UsersThree],
  ["改写任务", "Jobs", "/admin/jobs", ListBullets],
  ["套餐配置", "Plans", "/admin/plans", Coins],
  ["订单与对账", "Orders", "/admin/orders", Receipt],
  ["成本与毛利", "Economics", "/admin/economics", Gauge],
  ["服务控制", "Service", "/admin/service", Command],
  ["隐私审计", "Privacy", "/admin/privacy", LockKey],
];

function Brand({ navigate, compact = false }) {
  return (
    <button className={`rt-brand${compact ? " rt-brand--compact" : ""}`} onClick={() => navigate("/")}>
      RightThesis
    </button>
  );
}

function Topbar({ path, navigate, onOpenMap }) {
  const { isEnglish } = useLocale();
  const { billing, config, session, refresh } = usePlatform();
  const [serviceOpen, setServiceOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const serviceAnchorRef = useRef(null);
  const userAnchorRef = useRef(null);
  const isAdmin = path.startsWith("/admin");
  const isDocument = path === "/app/documents/rt-014";
  const workspace = getWorkspace();
  const displayName = session?.user?.display_name || session?.user?.name || (isEnglish ? "Local researcher" : "本地研究者");
  const avatarLabel = Array.from(displayName.trim())[0] || (isEnglish ? "R" : "研");
  const isAccountUser = session?.authMode === "accounts" && session?.authenticated && session?.kind !== "guest";
  const accessLabel = isAccountUser
    ? (session?.user?.email_verified ? (isEnglish ? "Verified account" : "已验证账户") : (isEnglish ? "Signed-in account" : "已登录账户"))
    : session?.trialMode || session?.kind === "guest"
      ? (isEnglish ? "Anonymous trial" : "匿名试用")
      : (isEnglish ? "Local workspace" : "本地工作区");

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    setSignOutError("");
    try {
      await logoutSession();
      await refresh();
      setUserOpen(false);
      navigate("/");
    } catch (error) {
      setSignOutError(error.message || (isEnglish ? "Sign-out failed." : "退出登录失败。"));
    } finally {
      setSigningOut(false);
    }
  };

  useEffect(() => {
    setServiceOpen(false);
    setUserOpen(false);
  }, [path]);

  useEffect(() => {
    if (!serviceOpen && !userOpen) return undefined;
    const closePopovers = () => {
      setServiceOpen(false);
      setUserOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") closePopovers();
    };
    const onPointerDown = (event) => {
      if (!serviceAnchorRef.current?.contains(event.target) && !userAnchorRef.current?.contains(event.target)) closePopovers();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [serviceOpen, userOpen]);

  return (
    <header className="rt-topbar">
      <div className="rt-topbar__brand">
        <Brand navigate={navigate} />
        <span className="rt-topbar__tagline">{isEnglish ? <>Let good research<br />speak more clearly</> : <>让好的研究<br />被更好地表达</>}</span>
      </div>
      <div className="rt-topbar__document">
        <span className="rt-kicker">{isAdmin ? "OPERATIONS" : (isEnglish ? routeTitlesEnglish[path] : routeTitles[path]) || "RIGHTTHESIS"}</span>
        <strong>{isAdmin ? (isEnglish ? "Operations preview" : "运营预览") : path.includes("documents") ? (workspace.name || (isEnglish ? "Untitled manuscript" : "未命名文稿")) : (isEnglish ? "Researcher workspace" : "研究者工作区")}</strong>
        <span>{isAdmin ? (isEnglish ? "No production admin data" : "尚无生产后台数据") : (isEnglish ? "Saved local workspace" : "本地已保存工作区")}</span>
      </div>
      <div className="rt-topbar__actions">
        <LanguageToggle />
        <div ref={serviceAnchorRef} className="rt-popover-anchor">
          <button className="rt-status-button" onClick={() => { setServiceOpen((value) => !value); setUserOpen(false); }} aria-expanded={serviceOpen} aria-haspopup="dialog">
            <span className={`rt-live-dot ${config?.llm_configured ? "" : "is-offline"}`} /> {config?.llm_configured ? (isEnglish ? "AI service ready" : "AI 服务已就绪") : (isEnglish ? "Diagnosis only" : "仅诊断可用")}
          </button>
          {serviceOpen && (
            <div className="rt-popover rt-service-popover" role="dialog" aria-label="服务状态摘要">
              <strong>{isEnglish ? "Service status" : "服务状态"}</strong>
              <p>{config?.llm_configured
                ? (isEnglish ? "Bilingual rules, document parsing, and faithful rewriting are available." : "双语规则、文档解析和保真改写均可用。")
                : (isEnglish ? "Bilingual diagnosis is available; model rewriting is currently unavailable." : "双语诊断可用；模型改写服务当前不可用。")}</p>
              <button onClick={() => navigate("/app/settings/service")}>{isEnglish ? "View details" : "查看状态详情"}</button>
            </div>
          )}
        </div>
        {!isAdmin && (
          <button className="rt-balance" onClick={() => navigate("/app/billing")}>
            <span>{isEnglish ? "Balance" : "剩余额度"}</span><strong>{Number(billing?.balance || 0).toLocaleString()} {isEnglish ? "chars" : "字"}</strong>
          </button>
        )}
        {!isDocument && (
          <>
            <button className="rt-icon-button" onClick={onOpenMap} aria-label={isEnglish ? "Open all pages" : "打开全部页面"}>
              <Command size={21} weight="bold" />
            </button>
            <div ref={userAnchorRef} className="rt-popover-anchor">
              <button className="rt-user-button" onClick={() => { setUserOpen((value) => !value); setServiceOpen(false); }} aria-expanded={userOpen} aria-haspopup="menu" aria-label={isEnglish ? "Open user menu" : "打开用户菜单"}>
                <span>{avatarLabel}</span><CaretDown size={14} weight="bold" />
              </button>
              {userOpen && (
                <div className="rt-popover rt-user-popover" role="menu" aria-label={isEnglish ? "User menu" : "用户菜单"}>
                  <div><strong>{displayName}</strong><span>{session?.user?.email || accessLabel}</span><small>{session?.user?.email ? accessLabel : ""}</small></div>
                  <button role="menuitem" onClick={() => navigate("/app/settings/account")}><UserCircle size={17} />{isEnglish ? "Account settings" : "账号设置"}</button>
                  {isAccountUser
                    ? <button role="menuitem" disabled={signingOut} onClick={handleSignOut}><SignOut size={17} />{signingOut ? (isEnglish ? "Signing out…" : "正在退出…") : (isEnglish ? "Sign out" : "退出登录")}</button>
                    : <button role="menuitem" onClick={() => navigate("/")}><SignOut size={17} />{isEnglish ? "Return home" : "返回首页"}</button>}
                  {signOutError && <p role="alert">{signOutError}</p>}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </header>
  );
}

function Sidebar({ path, navigate, onOpenMap }) {
  const { isEnglish } = useLocale();
  const isAdmin = path.startsWith("/admin");
  const items = isAdmin ? adminNavigation : appNavigation;
  return (
    <aside className="rt-sidebar">
      <nav aria-label={isAdmin ? (isEnglish ? "Admin navigation" : "管理后台导航") : (isEnglish ? "Application navigation" : "应用导航")}>
        {items.map(([label, englishLabel, href, Icon]) => {
          const active = href === path || (href === "/app" && path === "/app/new") || (href === "/app/billing" && path.startsWith("/app/billing"));
          return (
            <button key={href} className={active ? "is-active" : ""} aria-current={active ? "page" : undefined} onClick={() => navigate(href)}>
              <Icon size={22} weight={active ? "fill" : "regular"} />
              <span>{isEnglish ? englishLabel : label}</span>
            </button>
          );
        })}
      </nav>
      <div className="rt-sidebar__foot">
        <button onClick={onOpenMap}><Command size={21} />{isEnglish ? "All pages" : "全部页面"}</button>
        <button onClick={() => navigate("/help")}><Lifebuoy size={21} />{isEnglish ? "Help center" : "帮助中心"}</button>
        {isAdmin && <button onClick={() => navigate("/app")}><ArrowSquareOut size={21} />{isEnglish ? "User app" : "返回用户端"}</button>}
        <span>RightThesis<br />local MVP 0.3</span>
      </div>
    </aside>
  );
}

function PageMap({ open, path, navigate, onClose }) {
  const { isEnglish } = useLocale();
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    previousFocusRef.current = document.activeElement;
    closeButtonRef.current?.focus();

    function onKey(event) {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll("button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])");
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="rt-map-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section ref={dialogRef} className="rt-page-map" role="dialog" aria-modal="true" aria-label={isEnglish ? "All pages" : "全部页面"}>
        <header>
          <div><span className="rt-kicker">SITE MAP</span><h2>{isEnglish ? "Full platform map" : "整个平台页面"}</h2></div>
          <button ref={closeButtonRef} className="rt-icon-button" onClick={onClose} aria-label={isEnglish ? "Close" : "关闭"}><X size={22} weight="bold" /></button>
        </header>
        <div className="rt-page-map__grid">
          {pageGroups.filter((group) => group.label !== "Admin").map((group) => (
            <section key={group.label}>
              <h3>{group.label}</h3>
              {group.items.map(([label, href]) => (
                <button key={href} className={path === href ? "is-current" : ""} aria-current={path === href ? "page" : undefined} onClick={() => { navigate(href); onClose(); }}>
                  <span>{isEnglish ? routeTitlesEnglish[href] || label : label}</span><small>{href}</small>
                </button>
              ))}
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}

export function App() {
  const { isEnglish } = useLocale();
  const { session, loading, error, refresh } = usePlatform();
  const [path, setPath] = useState(currentRoute);
  const [mapOpen, setMapOpen] = useState(false);

  const navigate = (nextPath) => {
    if (nextPath === path) return;
    window.location.hash = nextPath;
  };

  useEffect(() => {
    const syncRoute = () => setPath(currentRoute());
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [path]);

  const accountProtected = path.startsWith("/app") || path.startsWith("/checkout") || path.startsWith("/admin");
  const accountAdminDenied = !loading
    && session?.authMode === "accounts"
    && session?.authenticated
    && path.startsWith("/admin")
    && session?.user?.role !== "admin"
    && !session?.user?.roles?.includes?.("admin");
  const accountSignInRequired = !loading
    && session?.ready
    && session?.authMode === "accounts"
    && accountProtected
    && (!session?.authenticated || session?.kind === "guest");

  useEffect(() => {
    if (!accountSignInRequired) return;
    try {
      if (path === "/checkout/pro") {
        const query = new URLSearchParams(window.location.hash.split("?", 2)[1] || "");
        const planId = query.get("plan");
        if (planId && /^[A-Za-z0-9_-]{1,64}$/.test(planId)) {
          window.sessionStorage.setItem("rightthesis-checkout-plan", planId);
        }
      }
      window.sessionStorage.setItem("rightthesis-auth-return", path.startsWith("/admin") ? "/app" : path);
    } catch {
      // The default post-login destination remains /app if storage is blocked.
    }
    navigate("/auth");
  }, [accountSignInRequired, path]);

  const Page = useMemo(() => routeComponents[path] || SystemStatePage, [path]);
  const isPublic = ["/", "/pricing", "/auth", "/auth/verify", "/auth/forgot", "/legal/privacy", "/legal/terms", "/help", "/checkout/pro"].includes(path) || !routeComponents[path];
  const needsFloatingLanguage = ["/auth", "/auth/verify", "/auth/forgot", "/checkout/pro"].includes(path) || !routeComponents[path];

  if (accountProtected && (loading || !session?.ready || accountSignInRequired)) {
    return (
      <div className="rtp-auth-page">
        <main className="rtp-auth-main">
          <div className="rtp-auth-loading" role="status">
            <ShieldCheck size={30} weight="fill" />
            <span>{loading
              ? (isEnglish ? "Checking your session…" : "正在检查会话…")
              : !session?.ready
                ? (error || (isEnglish ? "The account service is unavailable." : "账户服务暂时不可用。"))
                : (isEnglish ? "Opening secure sign-in…" : "正在前往安全登录…")}</span>
            {!loading && !session?.ready && <button className="rtp-btn rtp-btn-blue" type="button" onClick={refresh}>{isEnglish ? "Retry" : "重试"}</button>}
          </div>
        </main>
      </div>
    );
  }

  if (accountAdminDenied) {
    return (
      <div className="rtp-auth-page">
        <main className="rtp-auth-main">
          <div className="rtp-access-status is-error" role="alert">
            <LockKey size={34} weight="fill" />
            <strong>{isEnglish ? "Admin access is not enabled" : "运营后台尚未开放账号权限"}</strong>
            <span>{isEnglish ? "This account can use the researcher workspace, but no administrator role has been granted." : "当前账户可使用研究工作台，但尚未被授予管理员角色。"}</span>
            <button className="rtp-btn rtp-btn-blue" type="button" onClick={() => navigate("/app")}>{isEnglish ? "Open workspace" : "进入工作台"}</button>
          </div>
        </main>
      </div>
    );
  }

  if (isPublic) {
    return (
      <>
        <Page navigate={navigate} statePath={path} />
        {needsFloatingLanguage && <div className="rt-floating-language"><LanguageToggle /></div>}
        <button className="rt-map-fab" onClick={() => setMapOpen(true)} aria-label={isEnglish ? "Open all pages" : "打开全部页面"}><Command size={18} weight="bold" /><span>{isEnglish ? "All pages" : "全部页面"}</span></button>
        <PageMap open={mapOpen} path={path} navigate={navigate} onClose={() => setMapOpen(false)} />
      </>
    );
  }

  return (
    <div className="rt-shell">
      <Topbar path={path} navigate={navigate} onOpenMap={() => setMapOpen(true)} />
      <Sidebar path={path} navigate={navigate} onOpenMap={() => setMapOpen(true)} />
      <main className="rt-main"><Page navigate={navigate} statePath={path} /></main>
      <PageMap open={mapOpen} path={path} navigate={navigate} onClose={() => setMapOpen(false)} />
    </div>
  );
}
