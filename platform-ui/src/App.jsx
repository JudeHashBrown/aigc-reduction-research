import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowSquareOut,
  CaretDown,
  ChartLineUp,
  ClockCounterClockwise,
  Coins,
  Command,
  FileText,
  Gauge,
  GearSix,
  Lifebuoy,
  ListBullets,
  LockKey,
  Receipt,
  ShieldCheck,
  SignOut,
  UserCircle,
  UsersThree,
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
  ServiceStatusPage,
  AdminOverviewPage,
  AdminUsersPage,
  AdminTrafficPage,
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

const routeTitles = {
  "/": "品牌首页", "/pricing": "定价", "/auth": "登录与注册",
  "/auth/verify": "邮箱验证", "/auth/forgot": "忘记密码",
  "/legal/privacy": "隐私与数据", "/legal/terms": "服务条款", "/help": "帮助中心",
  "/app": "文档首页", "/app/new": "新建与导入", "/app/workbench": "保真优化工作台",
  "/app/versions": "版本与任务历史", "/app/billing": "我的权益",
  "/app/billing/usage": "额度明细", "/app/billing/orders": "订单与月卡",
  "/checkout/pro": "支付确认", "/app/settings/account": "账号设置",
  "/app/settings/service": "服务状态",
  "/admin": "运营总览", "/admin/users": "用户", "/admin/jobs": "改写任务",
  "/admin/traffic": "网站访问量",
  "/admin/plans": "套餐配置", "/admin/orders": "订单与对账",
  "/admin/economics": "收款与模型用量", "/admin/service": "服务状态",
  "/admin/privacy": "隐私审计", "/404": "页面未找到",
};
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
  "/app/workbench": "Faithful rewrite workspace",
  "/app/versions": "Versions & tasks",
  "/app/billing": "Plans & balance",
  "/app/billing/usage": "Usage ledger",
  "/app/billing/orders": "Orders & passes",
  "/checkout/pro": "Checkout",
  "/app/settings/account": "Account settings",
  "/app/settings/service": "Service status",
  "/admin": "Operations overview",
  "/admin/users": "Users",
  "/admin/traffic": "Website traffic",
  "/admin/jobs": "Rewrite jobs",
  "/admin/plans": "Plan settings",
  "/admin/orders": "Orders & reconciliation",
  "/admin/economics": "Unit economics",
  "/admin/service": "Service controls",
  "/admin/privacy": "Privacy audit",
  "/404": "Page not found",
};

function currentRoute() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash && ["/legal/privacy", "/legal/terms"].includes(window.location.pathname)) {
    return window.location.pathname;
  }
  const path = (hash || "/").split("?")[0];
  const replacement = {
    "/app/documents/rt-014": "/app/workbench",
    "/app/documents/rt-014/versions": "/app/versions",
    "/app/settings/privacy": "/app/settings/account",
  }[path];
  if (replacement) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${replacement}`);
    return replacement;
  }
  return path;
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
  "/app/workbench": WorkbenchPage,
  "/app/versions": VersionsPage,
  "/app/billing": BillingPage,
  "/app/billing/usage": UsagePage,
  "/app/billing/orders": OrdersPage,
  "/checkout/pro": CheckoutPage,
  "/app/settings/account": AccountSettingsPage,
  "/app/settings/service": ServiceStatusPage,
  "/admin": AdminOverviewPage,
  "/admin/users": AdminUsersPage,
  "/admin/traffic": AdminTrafficPage,
  "/admin/jobs": AdminJobsPage,
  "/admin/plans": AdminPlansPage,
  "/admin/orders": AdminOrdersPage,
  "/admin/economics": AdminEconomicsPage,
  "/admin/service": AdminServicePage,
  "/admin/privacy": AdminPrivacyPage,
};

const appNavigation = [
  ["当前文稿", "Current manuscript", "/app/workbench", Gauge],
  ["文档", "Documents", "/app", FileText],
  ["版本历史", "Versions", "/app/versions", ClockCounterClockwise],
  ["套餐与用量", "Plans & usage", "/app/billing", Coins],
  ["账号设置", "Account", "/app/settings/account", GearSix],
];

const adminNavigation = [
  ["运营总览", "Overview", "/admin", ChartLineUp],
  ["用户", "Users", "/admin/users", UsersThree],
  ["访问量", "Traffic", "/admin/traffic", ChartLineUp],
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

function Topbar({ path, navigate }) {
  const { isEnglish } = useLocale();
  const { billing, session, refresh } = usePlatform();
  const [userOpen, setUserOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const userAnchorRef = useRef(null);
  const isAdmin = path.startsWith("/admin");
  const isDocument = path === "/app/workbench";
  const workspace = getWorkspace();
  const displayName = session?.user?.display_name || session?.user?.name || (isEnglish ? "Local researcher" : "本地研究者");
  const avatarLabel = Array.from(displayName.trim())[0] || (isEnglish ? "R" : "研");
  const isAccountUser = session?.authMode === "accounts" && session?.authenticated && session?.kind !== "guest";
  const isAdminUser = isAccountUser && (session?.user?.role === "admin" || session?.user?.roles?.includes?.("admin"));
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
    setUserOpen(false);
  }, [path]);

  useEffect(() => {
    if (!userOpen) return undefined;
    const closePopovers = () => {
      setUserOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") closePopovers();
    };
    const onPointerDown = (event) => {
      if (!userAnchorRef.current?.contains(event.target)) closePopovers();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [userOpen]);

  return (
    <header className="rt-topbar">
      <div className="rt-topbar__brand">
        <Brand navigate={navigate} />
        <span className="rt-topbar__tagline">{isEnglish ? <>Let good research<br />speak more clearly</> : <>让好的研究<br />被更好地表达</>}</span>
      </div>
      <div className="rt-topbar__document">
        <span className="rt-kicker">{isAdmin ? "OPERATIONS" : (isEnglish ? routeTitlesEnglish[path] : routeTitles[path]) || "RIGHTTHESIS"}</span>
        <strong>{isAdmin ? (isEnglish ? "Operations" : "运营后台") : isDocument ? (workspace.name || (isEnglish ? "Untitled manuscript" : "未命名文稿")) : (isEnglish ? "Researcher workspace" : "研究者工作区")}</strong>
        <span>{isAdmin ? (isEnglish ? "Live service data" : "实时服务数据") : (isEnglish ? "Your research workspace" : "你的研究工作区")}</span>
      </div>
      <div className="rt-topbar__actions">
        <LanguageToggle />
        {!isAdmin && (
          <button className="rt-balance" onClick={() => navigate("/app/billing")}>
            <span>{isEnglish ? "Balance" : "剩余额度"}</span><strong>{Number(billing?.balance || 0).toLocaleString()} {isEnglish ? "chars" : "字"}</strong>
          </button>
        )}
        <div ref={userAnchorRef} className="rt-popover-anchor">
              <button className="rt-user-button" onClick={() => setUserOpen((value) => !value)} aria-expanded={userOpen} aria-haspopup="menu" aria-label={isEnglish ? "Open user menu" : "打开用户菜单"}>
                <span>{avatarLabel}</span><CaretDown size={14} weight="bold" />
              </button>
              {userOpen && (
                <div className="rt-popover rt-user-popover" role="menu" aria-label={isEnglish ? "User menu" : "用户菜单"}>
                  <div><strong>{displayName}</strong><span>{session?.user?.email || accessLabel}</span><small>{session?.user?.email ? accessLabel : ""}</small></div>
                  <button role="menuitem" onClick={() => navigate("/app/settings/account")}><UserCircle size={17} />{isEnglish ? "Account settings" : "账号设置"}</button>
                  {isAdminUser && <button role="menuitem" onClick={() => navigate("/admin/users")}><UsersThree size={17} />{isEnglish ? "Manage users" : "管理全部用户"}</button>}
                  {isAdmin && <button role="menuitem" onClick={() => navigate("/app")}><ArrowSquareOut size={17} />{isEnglish ? "Return to workspace" : "返回用户端"}</button>}
                  {isAccountUser
                    ? <button role="menuitem" disabled={signingOut} onClick={handleSignOut}><SignOut size={17} />{signingOut ? (isEnglish ? "Signing out…" : "正在退出…") : (isEnglish ? "Sign out" : "退出登录")}</button>
                    : <button role="menuitem" onClick={() => navigate("/")}><SignOut size={17} />{isEnglish ? "Return home" : "返回首页"}</button>}
                  {signOutError && <p role="alert">{signOutError}</p>}
                </div>
              )}
        </div>
      </div>
    </header>
  );
}

function Sidebar({ path, navigate }) {
  const { isEnglish } = useLocale();
  const isAdmin = path.startsWith("/admin");
  const items = isAdmin ? adminNavigation : appNavigation;
  return (
    <aside className={`rt-sidebar${isAdmin ? " rt-sidebar--admin" : ""}`}>
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
        <button onClick={() => navigate("/help")}><Lifebuoy size={21} />{isEnglish ? "Help center" : "帮助中心"}</button>
        {isAdmin && <button onClick={() => navigate("/app")}><ArrowSquareOut size={21} />{isEnglish ? "User app" : "返回用户端"}</button>}
        <span>RightThesis</span>
      </div>
    </aside>
  );
}

export function App() {
  const { isEnglish } = useLocale();
  const { session, loading, error, refresh } = usePlatform();
  const [path, setPath] = useState(currentRoute);
  const lastTrackedPath = useRef("");

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

  useEffect(() => {
    // Count browser page views, including hash-route changes, but never send
    // document text, account identifiers or the URL's query string.
    if (path.startsWith("/admin") || path === "/404" || !routeTitles[path]) {
      lastTrackedPath.current = "";
      return;
    }
    if (loading || !session?.ready || session?.authMode !== "accounts"
        || accountSignInRequired || accountAdminDenied
        || lastTrackedPath.current === path) return;
    lastTrackedPath.current = path;
    void fetch("/api/traffic/page-view", {
      method: "POST",
      credentials: "omit",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
      keepalive: true,
    }).catch(() => {
      // Analytics never blocks document, account or payment workflows.
    });
  }, [path, loading, session?.ready, session?.authMode, accountSignInRequired, accountAdminDenied]);

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
      </>
    );
  }

  return (
    <div className={`rt-shell${path.startsWith("/admin") ? " rt-shell--admin" : ""}`}>
      <Topbar path={path} navigate={navigate} />
      <Sidebar path={path} navigate={navigate} />
      <main className="rt-main"><Page navigate={navigate} statePath={path} /></main>
    </div>
  );
}
