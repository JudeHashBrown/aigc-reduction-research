import { cloneElement, isValidElement, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowsClockwise,
  Bell,
  CalendarBlank,
  ChartLineUp,
  Check,
  CheckCircle,
  Clock,
  Coins,
  Copy,
  CreditCard,
  Database,
  DownloadSimple,
  Envelope,
  Eye,
  FileText,
  FunnelSimple,
  Gauge,
  GoogleLogo,
  HardDrives,
  Info,
  Lightning,
  ListChecks,
  LockKey,
  MagnifyingGlass,
  Package,
  Pause,
  Play,
  Plus,
  Pulse,
  Receipt,
  SealCheck,
  ShieldCheck,
  ShieldWarning,
  SignOut,
  SlidersHorizontal,
  Trash,
  TrendUp,
  UserCircle,
  Users,
  Wallet,
  WarningCircle,
  Wrench,
  XCircle,
} from "@phosphor-icons/react";
import { useLocale } from "../locale.jsx";
import { localizedPlanDescription, localizedPlanName } from "../plan-copy.js";
import { ensureSession, getApi, postApi, logoutSession, usePlatform } from "../platform.jsx";
import "./operations-pages.css";

const OPS_EN = {
  "用户与权益": "Users and credits",
  "最近 100 位账户的身份与额度摘要；不展示论文内容，不提供直接改额度操作。": "Identity and credit summaries for the latest 100 accounts. Manuscript contents and direct balance changes are not available here.",
  "邮箱": "Email", "名称": "Name", "可用字数": "Available characters", "文稿数": "Manuscripts", "注册时间": "Registered",
  "改写任务": "Rewrite jobs",
  "最近 100 个真实任务的状态及 Token 用量；正文和改写结果不会在管理台展示。": "Status and token usage for the latest 100 jobs; no manuscript or result text is shown.",
  "任务号": "Job ID", "阶段": "Phase", "计费字数": "Billable characters", "输入 Token": "Input tokens", "输出 Token": "Output tokens", "开始时间": "Started",
  "套餐目录": "Plan catalog",
  "查看当前实际生效的服务端套餐。价格修改仍需代码审查和发布，避免在管理台误改真实收款。": "View live server plans. Price changes still require code review and deployment to avoid accidental live-billing changes.",
  "套餐 ID": "Plan ID", "价格": "Price", "额度": "Credits", "有效天数": "Valid days",
  "收款与模型用量": "Payments and model usage",
  "展示真实已支付订单净额与已结算任务 Token。模型单价和 Stripe 手续费尚未接入，不能据此计算毛利。": "Shows actual net order amount and tokens for committed jobs. Model pricing and Stripe fees are not included, so this is not gross margin.",
  "订单净额（未扣费）": "Net order amount (before fees)", "已结算改写任务": "Committed rewrite jobs", "模型 Token": "Model tokens",
  "服务状态": "Service status",
  "只读查看当前任务和待付款订单；停服、容量和部署操作仍由服务器受控执行。": "Read-only job and pending-order counts. Shutdown, capacity, and deployment changes remain server-controlled.",
  "运行中任务": "Running jobs", "失败任务": "Failed jobs", "待确认订单": "Pending orders",
  "正在读取…": "Loading…", "刷新": "Refresh",
  "已支付": "Paid",
  "确认中": "Confirming",
  "已退款": "Refunded",
  "部分退款": "Partially refunded",
  "失败": "Failed",
  "已结算": "Settled",
  "已预占": "Reserved",
  "已释放": "Released",
  "已发放": "Granted",
  "运行中": "Running",
  "排队中": "Queued",
  "已完成": "Completed",
  "正常": "Healthy",
  "降级": "Degraded",
  "已停用": "Disabled",
  "需复核": "Review required",
  "已对账": "Reconciled",
  "差异": "Mismatch",
  "生效中": "Active",
  "草稿": "Draft",
  "已受理": "Received",
  "轻量月卡": "Lite Monthly Pass",
  "专业月卡": "Pro Monthly Pass",
  "章节包": "Chapter Pack",
  "论文包": "Thesis Pack",
  "长文包": "Long-form Pack",
  "适合单篇论文阶段性优化": "For focused work on a single paper",
  "适合长论文与多轮修订": "For long papers and multiple revision rounds",
  "轻量补充，不影响月卡": "A small top-up that stays separate from your monthly pass",
  "适合一篇完整论文": "For one complete paper",
  "适合多章节集中处理": "For processing several chapters together",
  "30 天有效 · 非无限量": "Valid for 30 days · Usage capped",
  "90 天有效": "Valid for 90 days",
  "180 天有效": "Valid for 180 days",
  "内测赠送": "Beta bonus",
  "赠送额度": "Bonus credits",
  "月卡额度": "One-time pass credits",
  "独立字数包": "Standalone character packs",
  "深度保真改写": "Deep faithful rewrite",
  "4,812 字 × 1.5": "4,812 characters × 1.5",
  "平衡保真改写": "Balanced faithful rewrite",
  "保守保真改写": "Conservative faithful rewrite",
  "1,202 字 × 1.0": "1,202 characters × 1.0",
  "任务处理中": "Job in progress",
  "任务失败回退": "Failed-job rollback",
  "超时，预占全额归还": "Timed out; the full reservation was returned",
  "购买章节包": "Purchased Chapter Pack",
  "演示订单确认后发放 20,000 字": "20,000 characters granted after demo-order confirmation",
  "内测体验发放": "Beta trial grant",
  "一次性体验额度": "One-time trial credits",
  "支付宝（演示）": "Alipay (demo)",
  "微信支付（演示）": "WeChat Pay (demo)",
  "返回": "Back",
  "切换视图": "Switch view",
  "搜索": "Search",
  "暂无记录": "No records",
  "全部账号与云端数据": "All account and cloud data",
  "全部已保存文档与版本": "All saved documents and versions",
  "删除账号与云端数据": "Delete account and cloud data",
  "删除已保存文档和版本": "Delete saved documents and versions",
  "可先逐文档处理，也可演示全部账号数据删除流程。": "Choose one document first, or walk through deleting all account data.",
  "可逐篇选择文档，或演示处理全部已保存内容。": "Choose individual documents, or walk through processing all saved content.",
  "开始安全流程": "Start safe flow",
  "选择范围": "Choose scope",
  "先确认是逐文档，还是全部处理。": "First choose one document or everything.",
  "删除范围": "Deletion scope",
  "逐文档": "One document",
  "只演示处理一篇指定文档": "Process one selected document in this demo",
  "全部账号数据": "All account data",
  "全部已保存内容": "All saved content",
  "进入范围更大的二次确认": "Continue to an additional confirmation for this broader scope",
  "选择文档": "Choose document",
  "取消": "Cancel",
  "继续核对": "Review scope",
  "二次确认": "Confirm again",
  "范围：": "Scope: ",
  "这是本地 UI 演示": "This is a local UI demo",
  "确认后只会展示处理与完成状态，绝不会删除真实账号、文档、版本或交易记录。": "Confirming only shows processing and completion states. It never deletes a real account, document, version, or transaction record.",
  "我已核对演示范围：": "I have reviewed the demo scope: ",
  "返回修改": "Change scope",
  "确认演示处理": "Confirm demo action",
  "正在演示处理": "Processing demo action",
  "正在生成本地状态反馈，没有发送任何删除请求。": "Generating local status feedback; no deletion request was sent.",
  "演示流程已完成": "Demo flow complete",
  "未发生真实变更；账号、文档和数据仍完整保留。": "No real change was made; the account, documents, and data remain intact.",
  "重新演示": "Run demo again",
  "推荐": "Recommended",
  "/ 30天": "/ 30 days",
  "字额度": "character credits",
  "MONEY / 额度中心": "MONEY / CREDITS",
  "每一字，都有来路": "Every character is accounted for",
  "月卡与独立字数包可以叠加；系统按最早到期的额度桶优先消耗。": "Monthly passes and standalone packs stack; credits expiring first are used first.",
  "购买额度": "Buy credits",
  "当前可用": "Available now",
  "本月已结算": "Settled this month",
  "不含处理中预占": "Excludes active reservations",
  "处理中预占": "Reserved in progress",
  "失败将自动释放": "Released automatically on failure",
  "最近到期": "Next expiry",
  "2026-10-24 · 14 天后": "2026-10-24 · in 14 days",
  "余额概览": "Balance overview",
  "内测方案": "Beta plans",
  "到期桶": "Expiry buckets",
  "可用额度构成": "Available-credit breakdown",
  "合计可用": "Total available",
  "字": "characters",
  "总发放": "Total granted",
  "字 · 已消费": "characters · used",
  "· 到期": "· expires",
  "剩余 /": "Remaining /",
  "消费规则": "Usage rules",
  "先预占，再结算": "Reserve first, settle later",
  "创建改写任务时预占额度；失败或没有候选通过守卫时，全额归还。": "Credits are reserved when a rewrite starts and fully returned if it fails or no candidate passes the safeguards.",
  "最早到期先用": "Use the earliest expiry first",
  "赠送额度、月卡和字数包共同排序，避免临期额度浪费。": "Bonus credits, monthly passes, and packs share one expiry order so near-expiry credits are not wasted.",
  "分析与安全清理免费": "Analysis and safety cleanup are free",
  "仅模型保真改写计入字符额度。": "Only faithful model rewrites use character credits.",
  "账本不可覆盖": "Ledger entries are immutable",
  "发放、预占、结算与释放都保留独立流水。": "Grants, reservations, settlements, and releases remain separate ledger entries.",
  "查看额度明细": "View credit activity",
  "内测参考方案": "Beta reference plans",
  "：用于验证用户需求与成本结构，不构成最终商业定价承诺。": ": These plans validate demand and cost structure; they are not a final pricing commitment.",
  "月卡": "Monthly passes",
  "额度到期顺序": "Credit expiry order",
  "消耗顺序": "Usage order",
  "来源": "Source",
  "剩余": "Remaining",
  "初始额度": "Initial credits",
  "到期日": "Expiry date",
  "使用进度": "Usage progress",
  "MONEY / 额度账本": "MONEY / CREDIT LEDGER",
  "额度明细": "Credit activity",
  "每次发放、预占、结算和释放都有独立流水，余额变化可追溯。": "Every grant, reservation, settlement, and release has its own entry, so every balance change is traceable.",
  "CSV 已准备（演示）": "CSV ready (demo)",
  "导出 CSV": "Export CSV",
  "本月净消耗": "Net usage this month",
  "已结算任务 7 次": "7 jobs settled",
  "预占中": "Reserved",
  "任务 J-26A88": "Job J-26A88",
  "失败归还": "Returned after failure",
  "本月 1 次自动释放": "1 automatic release this month",
  "已在本地演示中生成 CSV 准备状态；没有下载或发送任何真实数据。": "The local demo marked a CSV as ready; no real data was downloaded or sent.",
  "最近账本流水（节选）": "Recent ledger activity (sample)",
  "RECENT LEDGER · 6 条": "RECENT LEDGER · 6 ENTRIES",
  "搜索任务号或事件": "Search by job ID or event",
  "筛选账本": "Filter ledger",
  "全部": "All",
  "发放": "Granted",
  "时间": "Time",
  "流水 / 任务号": "Entry / job ID",
  "事件": "Event",
  "额度变化": "Credit change",
  "状态": "Status",
  "当前仅展示最近 6 条流水；上方 11,420 字来自本月全部 7 个已结算任务。": "Only the 6 most recent entries are shown; the 11,420 characters above include all 7 jobs settled this month.",
  "深度模式按 1.5 倍预估；最终规则以任务创建时展示并确认的计量快照为准。": "Deep mode is estimated at 1.5×; the confirmed metering snapshot shown when the job is created governs the final charge.",
  "MONEY / 订单": "MONEY / ORDERS",
  "订单与付款": "Orders and payments",
  "当前均为本地演示记录，不会连接支付渠道；支付、权益和对账状态仍分开呈现。": "These are local demo records and do not connect to a payment provider. Payment, entitlement, and reconciliation states remain separate.",
  "新建订单": "New order",
  "全部订单": "All orders",
  "搜索订单号或产品": "Search by order ID or product",
  "筛选订单": "Filter orders",
  "订单号": "Order ID",
  "创建时间": "Created",
  "产品": "Product",
  "支付方式": "Payment method",
  "金额": "Amount",
  "支付状态": "Payment status",
  "对账": "Reconciliation",
  "待对账": "Pending reconciliation",
  "当前选中": "Selected",
  "权益处理": "Entitlement",
  "已幂等发放": "Granted idempotently",
  "已冲正": "Reversed",
  "未发放": "Not granted",
  "核对依据": "Verification checks",
  "签名 · 金额 · 商户 · 状态": "Signature · amount · merchant · status",
  "凭证已展开": "Receipt opened",
  "查看凭证": "View receipt",
  "CHECKOUT / 演示收银台": "CHECKOUT / DEMO",
  "确认你的额度": "Confirm your credits",
  "这是交互原型，不会发起真实扣款。价格为内测参考方案。": "This interactive prototype never initiates a real charge. Prices are beta references.",
  "30 天月卡": "30-day passes",
  "新额度会与现有月卡、字数包叠加；消耗顺序按各额度桶的到期日决定。": "New credits stack with existing passes and packs; each bucket's expiry date determines usage order.",
  "付款方式演示": "Demo payment method",
  "演示付款方式": "Demo payment methods",
  "微": "W",
  "支": "A",
  "微信支付": "WeChat Pay",
  "支付宝": "Alipay",
  "字可用额度": "characters available",
  "产品金额": "Product amount",
  "付款方式": "Payment method",
  "优惠": "Discount",
  "应付": "Total due",
  "分析与安全清理不扣额度": "Analysis and safety cleanup use no credits",
  "仅在本地模拟确认后展示权益": "Entitlements appear only after local demo confirmation",
  "订单、退款与额度流水可核对": "Orders, refunds, and credit entries remain reconcilable",
  "演示提交订单": "Submit demo order",
  "等待服务端确认": "Awaiting server confirmation",
  "浏览器回跳只负责展示；验签和订单核对完成前不会增加额度。": "The browser redirect is presentational; credits are not added until signature and order checks finish.",
  "模拟成功": "Simulate success",
  "模拟失败": "Simulate failure",
  "演示确认完成": "Demo confirmation complete",
  "字只在当前原型中展示，不会写入真实账本。": "characters are shown only in this prototype and are not written to a real ledger.",
  "查看额度": "View credits",
  "订单未完成": "Order incomplete",
  "未发放额度，也不会生成消费流水。": "No credits were granted and no usage entry was created.",
  "继续即表示你已阅读价格、有效期、额度消耗和退款说明。当前页面仅为 UI 原型。": "By continuing, you acknowledge the price, validity period, credit usage, and refund terms. This page is a UI prototype.",
};

Object.assign(OPS_EN, {
  "MONEY / 额度中心": "MONEY / CREDITS",
  "每一字，都有来路": "Every character is accounted for",
  "余额、套餐与额度桶均直接读取当前平台账本。": "Balances, plans, and credit buckets are read directly from the platform ledger.",
  "正在读取平台账本…": "Reading the platform ledger…",
  "当前可用": "Available now",
  "当前方案": "Current plan",
  "单任务上限": "Per-job limit",
  "最近到期": "Next expiry",
  "等待账本响应": "Waiting for the ledger",
  "来自后端权益摘要": "From the backend entitlement summary",
  "等待后端返回": "Waiting for the backend",
  "没有有期限额": "No expiring credits",
  "平台方案": "Platform plans",
  "额度桶": "Credit buckets",
  "账本可用余额": "Ledger balance",
  "当前权益": "Current entitlement",
  "正在等待账本摘要": "Waiting for the ledger summary",
  "当前剩余": "Remaining now",
  "当前没有独立额度桶": "No active credit buckets",
  "账本规则": "Ledger rules",
  "任务创建时预占额度；失败或未通过守卫时由后端释放。": "Credits are reserved when a job starts and released by the backend if it fails or does not pass the safeguards.",
  "真实余额": "Live balance",
  "页面只展示账本摘要中的 balance，不推算历史消费。": "This page shows the balance returned by the ledger and does not infer historical usage.",
  "真实额度桶": "Live credit buckets",
  "仅展示 grants 返回的剩余量和到期时间。": "Only the remaining amount and expiry returned by grants are shown.",
  "独立流水": "Independent ledger entries",
  "发放、预占、结算和释放在额度明细中逐条展示。": "Grants, reservations, settlements, and releases are shown as separate ledger entries.",
  "套餐来自后端目录": "Plans come from the backend catalog",
  "支付与下单前端尚未接入。": "Payment and checkout are not connected yet.",
  "基础方案": "Base plan",
  "订阅方案": "30-day plans",
  "平台暂未返回套餐目录。": "The platform has not returned a plan catalog.",
  "顺序": "Order",
  "到期时间": "Expiry",
  "MONEY / 额度账本": "MONEY / CREDIT LEDGER",
  "额度明细": "Credit activity",
  "发放、预占、结算和释放均来自真实后端流水。": "Every grant, reservation, settlement, and release comes from the backend ledger.",
  "CSV 已导出": "CSV exported",
  "当前余额": "Current balance",
  "来自后端账本摘要": "From the backend ledger summary",
  "已加载额度增加": "Loaded credit increases",
  "已加载额度减少": "Loaded credit decreases",
  "最近账本流水": "Recent ledger activity",
  "变更后余额": "Balance after",
  "平台运行状态": "Platform status",
  "仅展示当前后端实际返回的健康、配置与账本证据。": "Only health, configuration, and ledger evidence returned by the live backend is shown.",
  "已连接核心后端": "Core backend connected",
  "正在核对后端": "Checking the backend",
  "部分后端状态不可用": "Some backend status is unavailable",
  "健康检查、平台配置与额度账本均已返回。": "Health, platform configuration, and the credit ledger all responded.",
  "请以组件表中的实际响应为准。": "Use the component table below as the source of truth.",
  "未接入项不会显示模拟数据": "Unconnected systems do not show simulated data",
  "订单、支付与管理员动作均明确停用。": "Orders, payments, and administrator actions are explicitly disabled.",
  "范围 / 配置": "Scope / configuration",
  "当前后端证据": "Current backend evidence",
  "网页与 API 服务": "Web and API service",
  "本地同源服务": "Local same-origin service",
  "平台服务": "Platform service",
  "等待 /health": "Waiting for /health",
  "检查中": "Checking",
  "分析规则引擎": "Analysis rule engine",
  "模型改写服务": "Model rewrite service",
  "未配置": "Not configured",
  "等待 /api/config": "Waiting for /api/config",
  "等待 /api/billing/summary": "Waiting for /api/billing/summary",
  "订单与支付": "Orders and payments",
  "没有订单、支付确认、退款或对账前端能力": "No order, payment confirmation, refund, or reconciliation frontend is connected.",
  "管理员控制面": "Administrator control plane",
  "只读占位": "Read-only placeholder",
  "没有管理员数据或写操作 API": "No administrator data or write API is connected.",
  "当前可核对能力": "Currently verifiable capabilities",
  "健康检查": "Health check",
  "读取 /health 的 ok 字段": "Reads the ok field from /health",
  "分析配置": "Analysis configuration",
  "已校准": "Calibrated",
  "未标记校准": "Not marked as calibrated",
  "会话模式": "Session mode",
  "试用模式": "Trial mode",
  "正式会话模式": "Standard session mode",
  "尚无后端数据": "No backend data yet",
  "未接入遥测与控制面": "Telemetry and the control plane are not connected",
  "后端没有 30 日 SLA、实时延迟、队列长度、事件历史或管理员写操作接口，因此本页不展示这些指标。": "The backend does not expose a 30-day SLA, live latency, queue depth, incident history, or administrator write APIs, so this page does not invent those metrics.",
  "免费体验": "Free experience",
  "小额包": "Small pack",
  "大论文包": "Large paper pack",
  "学生月卡": "Student 30-day plan",
  "高频月卡": "Frequent-use 30-day plan",
  "本地模拟支付": "Local simulated payment",
  "本地模拟支付：只测试套餐与额度流程，不会扣款。": "Local simulated payment tests only the plan and credit flow; it never charges money.",
  "Humanizer 中英双语": "Humanizer bilingual engine",
  "：订单、支付与管理员动作均明确停用。": ": Orders, payments, and administrator actions are explicitly disabled.",
  "管理员能力未接入": "Administrator capabilities are not connected",
  "没有管理员 API 或授权控制面": "No administrator API or authorized control plane",
  "本页不展示模拟指标，也不提供刷新、开关、编辑、导出、对账或隐私处置等假动作。": "This page shows no simulated metrics and offers no fake refresh, toggle, edit, export, reconciliation, or privacy actions.",
  "真实运营指标与管理员动作尚未接入。": "Live operations metrics and administrator actions are not connected.",
  "用户查询、权益调整与账号管理尚未接入。": "User lookup, entitlement adjustment, and account administration are not connected.",
  "全局任务队列、追踪与管理员处置尚未接入。": "The global job queue, tracing, and administrator actions are not connected.",
  "方案目录可由用户端只读获取，管理员编辑与发布尚未接入。": "The user app can read the plan catalog; administrator editing and publishing are not connected.",
  "订单查询、退款、对账与权益冲正尚未接入。": "Order lookup, refunds, reconciliation, and entitlement reversal are not connected.",
  "真实收入、成本和毛利数据源尚未接入。": "Live revenue, cost, and margin data sources are not connected.",
  "服务开关、容量管理与变更审计尚未接入。": "Service controls, capacity management, and change auditing are not connected.",
  "隐私请求、留存策略与审计导出尚未接入。": "Privacy requests, retention policies, and audit export are not connected.",
  "ACCOUNT / 账号": "ACCOUNT / PROFILE",
  "账号设置": "Account settings",
  "用于恢复付费权益、同步订单和保护文档任务。": "Recover paid entitlements, sync orders, and protect document jobs.",
  "已保存": "Saved",
  "保存修改": "Save changes",
  "设置导航": "Settings navigation",
  "账号资料": "Account profile",
  "隐私与数据": "Privacy and data",
  "额度与订单": "Credits and orders",
  "基础资料": "Profile",
  "显示名称": "Display name",
  "登录邮箱": "Sign-in email",
  "订单、额度和任务均绑定到可恢复账号；邮箱验证后即可使用。": "Orders, credits, and jobs are tied to a recoverable account and become available after email verification.",
  "通知": "Notifications",
  "安全与登录提醒": "Security and sign-in alerts",
  "新设备登录、邮箱变更和账号风险": "New-device sign-ins, email changes, and account risk",
  "长任务完成提醒": "Long-job completion alerts",
  "仅在超过 3 分钟的任务完成时发送": "Sent only when a job lasting more than 3 minutes completes",
  "登录设备": "Signed-in devices",
  "Mac · 当前设备": "Mac · Current device",
  "上海 · Chrome · 刚刚活跃": "Shanghai · Chrome · Active just now",
  "当前": "Current",
  "上海 · Safari · 2 天前": "Shanghai · Safari · 2 days ago",
  "会话已在本地演示中标记退出": "Session marked signed out in the local demo",
  "退出": "Sign out",
  "已退出（演示）": "Signed out (demo)",
  "已演示退出 iPhone 会话；未向任何真实设备发送指令。": "The iPhone session was signed out in the demo; no command was sent to a real device.",
  "ACCOUNT / 隐私": "ACCOUNT / PRIVACY",
  "选择正文留存时间，并查看每类数据为什么被处理、何时删除。": "Choose how long document text is retained and see why each data type is processed and when it is deleted.",
  "导出演示已准备": "Export demo ready",
  "导出我的数据": "Export my data",
  "已创建本地导出演示状态；没有打包、下载或发送真实数据。": "A local export-demo state was created; no real data was packaged, downloaded, or sent.",
  "正文不是运营素材": "Your text is not operations material",
  "不在操作日志中记录论文全文；用于产品改进的数据默认关闭。": "Full paper text is never recorded in operations logs, and product-improvement data sharing is off by default.",
  "正文留存": "Document retention",
  "任务完成即删除": "Delete when the job completes",
  "不支持跨设备恢复": "Cross-device recovery unavailable",
  "保留 24 小时": "Keep for 24 hours",
  "推荐 · 便于失败恢复与导出": "Recommended · Supports recovery and export",
  "保留 7 天": "Keep for 7 days",
  "适合多轮修订": "For multiple revision rounds",
  "数据使用开关": "Data-use controls",
  "允许使用匿名结构特征改进产品": "Allow anonymous structural features to improve the product",
  "不含正文、姓名、邮箱和引用内容；可随时撤回": "Excludes document text, names, email addresses, and quotations; revoke anytime",
  "发送错误诊断": "Send error diagnostics",
  "仅任务号、错误码、耗时和客户端版本": "Job ID, error code, duration, and client version only",
  "处理清单": "Data inventory",
  "邮箱、显示名称": "Email and display name",
  "登录与账号恢复": "Sign-in and account recovery",
  "账号存在期间": "For the life of the account",
  "账号服务": "Account service",
  "用户主动提交的正文": "Document text submitted by the user",
  "分析与改写": "Analysis and rewriting",
  "24 小时": "24 hours",
  "7 天": "7 days",
  "处理服务": "Processing service",
  "订单号、金额、状态": "Order ID, amount, and status",
  "付款、退款与对账": "Payments, refunds, and reconciliation",
  "按交易记录要求": "As required for transaction records",
  "账务服务": "Billing service",
  "任务号、错误码、耗时": "Job ID, error code, and duration",
  "安全与故障定位": "Security and troubleshooting",
  "30 天": "30 days",
  "运维人员": "Operations staff",
  "数据": "Data",
  "目的": "Purpose",
  "保留期": "Retention",
  "最小访问范围": "Minimum access",
  "网页与 API 网关": "Web and API gateway",
  "华东": "East China",
  "本地分析引擎": "Local analysis engine",
  "主集群": "Primary cluster",
  "保真改写队列": "Faithful-rewrite queue",
  "等待 18 s": "18 s wait",
  "额度账本": "Credit ledger",
  "主库": "Primary database",
  "支付确认（演示）": "Payment confirmation (demo)",
  "未接入": "Not connected",
  "SERVICE / 运行状态": "SERVICE / STATUS",
  "核心处理服务可核对": "Core processing services are verifiable",
  "这里只展示服务健康与事件进展；支付与经济系统尚未接入，相关内容均为本地演示。": "This page shows service health and incident progress only. Payment and economics systems are not connected; related content is local demo data.",
  "刷新中": "Refreshing",
  "刷新状态": "Refresh status",
  "核心处理服务正常": "Core processing services are healthy",
  "改写队列等待时间略高；支付渠道未接入，收银台与订单均为演示数据。": "Rewrite queue wait time is slightly elevated. Payment providers are not connected, so checkout and order data are demos.",
  "更新于 15:38": "Updated at 15:38",
  "支付未接入": "Payments not connected",
  "：微信支付、支付宝、退款与对账目前只演示界面状态，不会发起真实扣款或权益变更。": ": WeChat Pay, Alipay, refunds, and reconciliation currently demonstrate UI states only; no real charge or entitlement change occurs.",
  "服务组件": "Service components",
  "组件": "Component",
  "范围": "Scope",
  "当前延迟": "Current latency",
  "30 日可用性": "30-day availability",
  "进行中的事件": "Active incident",
  "部分深度改写任务排队时间增加": "Some deep-rewrite jobs are taking longer to queue",
  "已扩容任务消费者；预占额度保持锁定，超时任务会自动释放。": "Job workers have been scaled up. Reserved credits remain locked, and timed-out jobs release automatically.",
  "下一次更新：16:10 前": "Next update: by 16:10",
  "最近 30 天": "Last 30 days",
  "成功完成任务": "Jobs completed successfully",
  "支付演示流程覆盖": "Payment-demo flow coverage",
  "额度账本一致性": "Credit-ledger consistency",
  "轻量月卡 + 章节包": "Lite Monthly Pass + Chapter Pack",
  "3 分钟前": "3 minutes ago",
  "18 分钟前": "18 minutes ago",
  "2 小时前": "2 hours ago",
  "无有效权益": "No active entitlement",
  "19 天前": "19 days ago",
  "平衡": "Balanced",
  "深度": "Deep",
  "保守": "Conservative",
  "总览": "Overview",
  "用户": "Users",
  "任务": "Jobs",
  "方案": "Plans",
  "订单": "Orders",
  "成本": "Economics",
  "服务": "Service",
  "隐私": "Privacy",
  "运营总览": "Operations overview",
  "任务、额度与隐私请求使用可追溯事件口径；订单金额为本地演示数据。": "Jobs, credits, and privacy requests use traceable events; order amounts are local demo data.",
  "运营数据已在本地重新载入；没有请求真实管理端接口。": "Operations data was reloaded locally; no real admin API was called.",
  "已刷新（演示）": "Refreshed (demo)",
  "刷新数据": "Refresh data",
  "今日有效任务": "Valid jobs today",
  "成功率 98.7%": "98.7% success rate",
  "待处理队列": "Pending queue",
  "P95 等待 28 秒": "P95 wait: 28 seconds",
  "今日演示订单金额": "Demo order value today",
  "退款演示 ¥192": "Demo refunds: ¥192",
  "需人工复核": "Manual review required",
  "支付 2 · 隐私 1 · 任务 3": "Payments 2 · Privacy 1 · Jobs 3",
  "运营检查": "Operations checks",
  "额度账本与任务结算": "Credit ledger and job settlement",
  "10 分钟前核对": "Checked 10 minutes ago",
  "支付演示与本地订单": "Payment demo and local orders",
  "未连接真实支付渠道": "No real payment provider connected",
  "退款与权益冲正": "Refund and entitlement reversal",
  "全部一致": "All consistent",
  "文档删除计划": "Document deletion schedule",
  "1 个请求待执行": "1 request pending",
  "最近 7 日": "Last 7 days",
  "贡献毛利率": "Contribution margin",
  "内测观测值 · 不含固定研发成本": "Beta observation · Excludes fixed R&D costs",
  "模型与计算": "Model and compute",
  "支付与退款": "Payments and refunds",
  "毛利贡献": "Margin contribution",
  "实时任务抽样": "Live job sample",
  "任务号": "Job ID",
  "模式": "Mode",
  "计费字符": "Billable characters",
  "估算成本": "Estimated cost",
  "追踪号": "Trace ID",
  "管理台只显示任务元数据、计量与结果状态，不展示论文全文或改写正文。": "The admin console shows job metadata, metering, and result status only—never full papers or rewritten text.",
  "用户与权益": "Users and entitlements",
  "仅展示运营必需的脱敏身份、权益与风险信号。": "Only the masked identities, entitlements, and risk signals required for operations are shown.",
  "客服调整草稿已在本地创建；没有改动任何用户权益。": "A support-adjustment draft was created locally; no user entitlement changed.",
  "创建客服调整": "Create support adjustment",
  "用户列表": "User list",
  "搜索用户 ID 或脱敏邮箱": "Search by user ID or masked email",
  "待复核": "Needs review",
  "停用": "Disabled",
  "用户 ID": "User ID",
  "脱敏身份": "Masked identity",
  "有效权益": "Active entitlement",
  "可用额度": "Available credits",
  "任务数": "Jobs",
  "最后活跃": "Last active",
  "账号状态": "Account status",
  "操作": "Action",
  "查看账本": "View ledger",
  "任务队列": "Job queue",
  "查看任务状态、预占额度与成本；正文内容不会进入运营日志。": "Inspect job status, reserved credits, and costs; document text never enters operations logs.",
  "已在本地演示中标记“暂停新任务”；真实队列未受影响。": "New jobs are marked paused in the local demo; the real queue is unaffected.",
  "已在本地演示中恢复新任务；真实队列未受影响。": "New jobs are resumed in the local demo; the real queue is unaffected.",
  "恢复新任务（演示）": "Resume new jobs (demo)",
  "暂停新任务": "Pause new jobs",
  "并发上限 20": "Concurrency limit: 20",
  "排队": "Queued",
  "最老任务 41 秒": "Oldest job: 41 seconds",
  "今日失败": "Failed today",
  "1.3% · 超时为主": "1.3% · Mostly timeouts",
  "任务记录": "Job records",
  "搜索任务、用户或追踪号": "Search jobs, users, or trace IDs",
  "完成": "Completed",
  "输入字符": "Input characters",
  "额度预占": "Credits reserved",
  "耗时": "Duration",
  "方案与额度": "Plans and credits",
  "方案是可版本化配置；已成交订单继续使用购买时的产品快照。": "Plans are versioned configurations; completed orders retain the product snapshot captured at purchase.",
  "空白方案草稿已在本地创建；没有写入后台配置。": "A blank plan draft was created locally; no backend configuration was written.",
  "新建草稿": "New draft",
  "以下均为": "All items below are ",
  "。改价需创建新版本，不覆盖历史订单、额度桶或退款依据。": ". Price changes require a new version and never overwrite historical orders, credit buckets, or refund evidence.",
  "字数包": "Character packs",
  "产品 ID": "Product ID",
  "展示名": "Display name",
  "价格": "Price",
  "额度": "Credits",
  "有效期": "Validity",
  "上架": "Available",
  "下架": "Unavailable",
  "复制为草稿": "Copy as draft",
  "统一消耗规则": "Unified entitlement policy",
  "允许叠加": "Stacking allowed",
  "月卡与任意独立字数包同时有效。": "Monthly passes and any standalone character pack can remain active together.",
  "按到期日排序": "Ordered by expiry",
  "最早到期额度先消耗；同日按发放时间。": "Credits expiring first are used first; same-day expiries use grant time.",
  "任务级幂等": "Job-level idempotency",
  "一个任务只允许一次结算或一次全额释放。": "A job can be settled once or released in full once.",
  "订单与对账": "Orders and reconciliation",
  "当前为未接入渠道的演示数据；支付、对账与权益状态仍保持独立。": "These are demo records with no provider connected; payment, reconciliation, and entitlement states remain independent.",
  "本地演示对账已完成：5 条样例记录已核对，没有连接支付渠道。": "Local demo reconciliation completed: 5 sample records checked with no payment provider connection.",
  "演示对账完成": "Demo reconciliation complete",
  "演示对账": "Run demo reconciliation",
  "今日演示订单": "Demo orders today",
  "183 笔": "183 orders",
  "演示金额 ¥8,431": "Demo amount: ¥8,431",
  "2 笔": "2 orders",
  "最长 6 分钟": "Longest: 6 minutes",
  "退款": "Refunds",
  "4 笔": "4 orders",
  "金额 ¥192": "Amount: ¥192",
  "对账差异": "Reconciliation mismatches",
  "1 笔": "1 order",
  "已阻断发放": "Grant blocked",
  "支付记录": "Payment records",
  "搜索订单、用户或渠道单号": "Search orders, users, or provider IDs",
  "本地订单": "Local order",
  "渠道单号": "Provider ID",
  "付款": "Payment",
  "权益": "Entitlement",
  "成本与单位经济": "Costs and unit economics",
  "以下为内测情景模型，不代表真实实收；收入、计算、支付和退款按同一演示链路核对。": "This beta scenario model does not represent actual revenue; income, compute, payments, and refunds are reconciled along one demo flow.",
  "24小时": "24 hours",
  "7天": "7 days",
  "30天": "30 days",
  "情景收入": "Scenario revenue",
  "变动成本": "Variable cost",
  "每万结算字 ¥4.11": "¥4.11 per 10,000 settled characters",
  "占确认收入 3.6%": "3.6% of confirmed revenue",
  "贡献毛利": "Contribution margin",
  "内测观测，不含固定成本": "Beta observation; excludes fixed costs",
  "产品经济性": "Product economics",
  "单均收入": "Average revenue",
  "支付成本": "Payment cost",
  "退款摊销": "Refund allocation",
  "成本可核对字段": "Cost trace fields",
  "任务维度": "Job level",
  "输入/输出 token、候选数、重试、耗时、结算字符": "Input/output tokens, candidates, retries, duration, and settled characters",
  "订单维度": "Order level",
  "支付金额、通道费、退款、权益发放与冲正": "Payment amount, provider fee, refund, entitlement grant, and reversal",
  "价格版本": "Price version",
  "购买时快照，不用当前价格反算历史毛利": "Use the purchase-time snapshot; never recalculate historical margin from current prices",
  "风险提醒": "Risk note",
  "深度模式成本高于计费倍数": "Deep-mode cost exceeds its billing multiplier",
  "近 7 日深度模式单字成本是平衡模式的 1.82 倍，当前额度倍率为 1.5。建议继续观测，不在内测期承诺固定毛利。": "Over the last 7 days, deep mode cost 1.82× as much per character as balanced mode while its credit multiplier is 1.5×. Keep observing and avoid promising a fixed beta margin.",
  "开启": "On",
  "关闭": "Off",
  "服务控制": "Service controls",
  "运行健康、队列与功能开关集中管理；敏感配置不进入此页面。": "Manage service health, queues, and feature flags together; sensitive configuration is excluded.",
  "服务状态已在本地重新载入；没有请求真实控制面。": "Service status was reloaded locally; no real control-plane request was made.",
  "刷新": "Refresh",
  "7 / 8 项检查通过": "7 of 8 checks passed",
  "真实支付仍保持关闭；服务端回调域名与退款流程尚待验收。": "Real payments remain off; the server callback domain and refund flow still need acceptance testing.",
  "内测模式": "Beta mode",
  "功能开关": "Feature flags",
  "新建改写任务": "Create rewrite jobs",
  "允许新建改写任务": "Allow new rewrite jobs",
  "关闭后，运行中任务继续完成": "Running jobs continue after this is turned off",
  "深度模式": "Deep mode",
  "开放深度模式": "Enable deep mode",
  "受并发与成本上限保护": "Protected by concurrency and cost limits",
  "真实支付入口": "Live-payment entry point",
  "当前关闭；仅保留演示收银台": "Currently off; demo checkout remains available",
  "文档导出": "Document export",
  "允许文档导出": "Allow document export",
  "DOCX / PDF 导出服务正常": "DOCX / PDF export service is healthy",
  "容量与队列": "Capacity and queues",
  "工作进程": "Workers",
  "排队任务": "Queued jobs",
  "数据库连接": "Database connections",
  "对象存储": "Object storage",
  "服务变更记录": "Service change log",
  "扩容任务消费者": "Scale job workers",
  "关闭真实支付入口": "Disable live-payment entry point",
  "轮换服务凭据": "Rotate service credentials",
  "版本 17": "Version 17",
  "版本 18": "Version 18",
  "操作者": "Actor",
  "动作": "Action",
  "变更前": "Before",
  "变更后": "After",
  "结果": "Result",
  "隐私控制台": "Privacy console",
  "数据留存、访问、导出与删除请求均保留最小必要的审计证据。": "Retention, access, export, and deletion requests keep only the minimum audit evidence required.",
  "审计摘要已在本地生成演示状态；没有下载或传输真实审计数据。": "An audit-summary demo state was generated locally; no real audit data was downloaded or transmitted.",
  "摘要已准备（演示）": "Summary ready (demo)",
  "导出审计摘要": "Export audit summary",
  "待处理请求": "Pending requests",
  "删除请求 · 剩余 5 天": "Deletion request · 5 days remaining",
  "24h 自动删除": "24-hour auto-deletion",
  "184 份": "184 documents",
  "下一批 16:00": "Next batch: 16:00",
  "特权访问": "Privileged access",
  "过去 24 小时": "Past 24 hours",
  "策略覆盖": "Policy coverage",
  "全部数据类型已登记": "All data types registered",
  "用户请求": "User requests",
  "留存策略": "Retention policies",
  "访问审计": "Access audit",
  "权利请求": "Rights requests",
  "删除文档与版本": "Delete documents and versions",
  "17 个对象": "17 objects",
  "账号、订单、任务元数据": "Account, order, and job metadata",
  "请求号": "Request ID",
  "类型": "Type",
  "受理日": "Received",
  "承诺完成": "Due date",
  "数据留存策略": "Data retention policy",
  "策略变更双人复核": "Two-person review for policy changes",
  "防止单人延长正文保留期": "Prevents one person from extending document retention",
  "论文正文与版本": "Paper text and versions",
  "7 天（用户选择）": "7 days (user selected)",
  "自动删除": "Auto-delete",
  "任务元数据": "Job metadata",
  "90 天": "90 days",
  "去标识化": "De-identify",
  "订单与账务": "Orders and billing",
  "依交易记录要求": "Per transaction-record requirements",
  "依适用规则": "Per applicable rules",
  "最小字段保留": "Retain minimum fields",
  "管理员审计": "Administrator audit",
  "180 天": "180 days",
  "1 年": "1 year",
  "滚动删除": "Rolling deletion",
  "数据类型": "Data type",
  "默认": "Default",
  "上限": "Maximum",
  "到期动作": "Expiry action",
  "敏感操作审计": "Sensitive-action audit",
  "批准数据导出": "Approve data export",
  "元数据清单": "Metadata inventory",
  "执行自动删除": "Run automatic deletion",
  "184 个对象": "184 objects",
  "正文与版本": "Document text and versions",
  "查看错误追踪": "View error trace",
  "错误码与耗时": "Error code and duration",
  "对象": "Target",
  "最小范围": "Minimum scope",
  "这一页不在论文里": "This page is not in the paper",
  "链接可能已失效，或页面地址输入有误。你的文档与额度不会受影响。": "The link may have expired or the address may be incorrect. Your documents and credits are unaffected.",
  "返回首页": "Go home",
  "未知路由会默认来到这里。": "Unknown routes lead here by default.",
  "服务开了个小差": "The service hit a snag",
  "当前操作没有完成，也不会产生重复任务或额度结算。": "The action did not complete and will not create a duplicate job or credit settlement.",
  "返回工作区": "Return to workspace",
  "错误追踪号：RT-DEMO-500（仅演示）": "Error trace: RT-DEMO-500 (demo only)",
  "网络连接已中断": "Network connection lost",
  "已编辑内容会留在当前本地演示状态；恢复连接前不会提交任务。": "Edited content remains in the current local demo state; no job is submitted until the connection returns.",
  "重新检查": "Check again",
  "检查操作仅更新界面，不会访问外部网络。": "This check updates the interface only and makes no external network request.",
  "正在进行短暂维护": "Brief maintenance in progress",
  "文档浏览仍可使用，新建改写任务暂时停用。额度不会过期或被扣除。": "Document browsing remains available, but new rewrite jobs are temporarily disabled. Credits will not expire or be deducted.",
  "查看服务状态": "View service status",
  "预计恢复：今天 16:30（演示信息）": "Estimated recovery: today at 16:30 (demo)",
  "登录状态已过期": "Session expired",
  "为保护论文与订单信息，请重新登录。未提交的本地编辑仍会保留。": "Sign in again to protect paper and order information. Unsaved local edits will remain available.",
  "重新登录": "Sign in again",
  "不会自动上传或清除当前内容。": "Current content will not be uploaded or cleared automatically.",
  "本次任务额度不足": "Not enough credits for this job",
  "创建任务前的预估额度高于当前可用余额，因此没有预占、扣除或提交改写。": "The estimated credits exceeded the available balance, so no reservation, deduction, or rewrite submission occurred.",
  "查看套餐与额度": "View plans and credits",
  "支付尚未接入；套餐与结算流程均为本地演示。": "Payments are not connected; plans and settlement flows are local demos.",
  "已完成本地连接检查演示；没有发起任何网络请求。": "The local connection-check demo completed; no network request was made.",
});

const localeTag = (isEnglish) => (isEnglish ? "en-US" : "zh-CN");
const formatMoney = (value, isEnglish) => new Intl.NumberFormat(localeTag(isEnglish), {
  style: "currency",
  currency: "CNY",
  currencyDisplay: "narrowSymbol",
  minimumFractionDigits: 2,
}).format(Number(value));
const formatNumber = (value, isEnglish) => new Intl.NumberFormat(localeTag(isEnglish)).format(value);

function translateText(value, isEnglish) {
  if (!isEnglish || typeof value !== "string") return value;
  const leading = value.match(/^\s*/)?.[0] || "";
  const trailing = value.match(/\s*$/)?.[0] || "";
  const core = value.trim();
  if (!core) return value;
  if (OPS_EN[core]) return `${leading}${OPS_EN[core]}${trailing}`;
  const scoped = core.match(/^逐文档 · (.+)$/);
  if (scoped) return `${leading}One document · ${scoped[1]}${trailing}`;
  const completedScope = core.match(/^(.+) 未发生真实变更；账号、文档和数据仍完整保留。$/);
  if (completedScope) return `${leading}${translateText(completedScope[1], true)} was not changed; the account, documents, and data remain intact.${trailing}`;
  const characterAmount = core.match(/^([+\-−]?[\d,.]+) 字$/);
  if (characterAmount) return `${leading}${characterAmount[1]} characters${trailing}`;
  const bucketCount = core.match(/^共 (\d+) 个有效额度桶$/);
  if (bucketCount) return `${leading}${bucketCount[1]} active credit buckets${trailing}`;
  const activeBucketCount = core.match(/^(\d+) 个有效额度桶$/);
  if (activeBucketCount) return `${leading}${activeBucketCount[1]} active credit buckets${trailing}`;
  const recentEntries = core.match(/^最近 (\d+) 条流水$/);
  if (recentEntries) return `${leading}${recentEntries[1]} recent ledger entries${trailing}`;
  const ledgerAccount = core.match(/^(.+) · 账户 (.+)$/);
  if (ledgerAccount) return `${leading}${translateText(ledgerAccount[1], true)} · account ${ledgerAccount[2]}${trailing}`;
  const charsWithMeta = core.match(/^([\d,.]+) 字 · (.+)$/);
  if (charsWithMeta) return `${leading}${charsWithMeta[1]} characters · ${translateText(charsWithMeta[2], true)}${trailing}`;
  const analysisConfig = core.match(/^(.+) · (已校准|未标记校准)$/);
  if (analysisConfig) return `${leading}${analysisConfig[1]} · ${translateText(analysisConfig[2], true)}${trailing}`;
  const orderLabel = core.match(/^查看订单 (.+)$/);
  if (orderLabel) return `${leading}View order ${orderLabel[1]}${trailing}`;
  const progressLabel = core.match(/^进度 (.+)$/);
  if (progressLabel) return `${leading}Progress ${progressLabel[1]}${trailing}`;
  const planSwitch = core.match(/^(.+)上架状态$/);
  if (planSwitch) return `${leading}${translateText(planSwitch[1], true)} availability${trailing}`;
  const receipt = core.match(/^演示凭证：(.+) · (.+) · (.+)。没有请求真实支付渠道。$/);
  if (receipt) return `${leading}Demo receipt: ${receipt[1]} · ${translateText(receipt[2], true)} · ${receipt[3]}. No real payment provider was contacted.${trailing}`;
  const selectedPayment = core.match(/^已选择(微信支付|支付宝)演示流程；不会连接支付渠道。$/);
  if (selectedPayment) return `${leading}${translateText(selectedPayment[1], true)} demo flow selected; no payment provider will be contacted.${trailing}`;
  const ledgerPreview = core.match(/^已打开 (.+) 的本地账本预览；没有读取真实用户数据。$/);
  if (ledgerPreview) return `${leading}Opened the local ledger preview for ${ledgerPreview[1]}; no real user data was read.${trailing}`;
  const planAvailability = core.match(/^(.+)已在本地标记为(上架|下架)；真实方案未变更。$/);
  if (planAvailability) return `${leading}${translateText(planAvailability[1], true)} was marked ${planAvailability[2] === "上架" ? "available" : "unavailable"} locally; the real plan was unchanged.${trailing}`;
  const copiedPlan = core.match(/^(.+)已复制为本地演示草稿；未写入后台。$/);
  if (copiedPlan) return `${leading}${translateText(copiedPlan[1], true)} was copied into a local demo draft; nothing was written to the backend.${trailing}`;
  const estimateWindow = core.match(/^(.+) · 演示估算$/);
  if (estimateWindow) return `${leading}${estimateWindow[1]} · demo estimate${trailing}`;
  const serviceFlag = core.match(/^(.+)已在本地演示中(开启|关闭)；真实服务配置未变更。$/);
  if (serviceFlag) return `${leading}${translateText(serviceFlag[1], true)} was turned ${serviceFlag[2] === "开启" ? "on" : "off"} in the local demo; the real service configuration was unchanged.${trailing}`;
  const reviewFlag = core.match(/^双人复核已在本地演示中(开启|关闭)；真实策略未变更。$/);
  if (reviewFlag) return `${leading}Two-person review was turned ${reviewFlag[1] === "开启" ? "on" : "off"} in the local demo; the real policy was unchanged.${trailing}`;
  return value;
}

function localizeValue(value, isEnglish) {
  if (!isEnglish || value == null) return value;
  if (typeof value === "string") return translateText(value, true);
  if (typeof value === "function") return value;
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      const localized = localizeValue(item, true);
      return isValidElement(localized) && localized.key == null
        ? cloneElement(localized, { key: `localized-${index}` })
        : localized;
    });
  }
  if (isValidElement(value)) {
    const props = Object.fromEntries(Object.entries(value.props).map(([key, item]) => [
      key,
      key === "rows" || key === "columns" ? item : localizeValue(item, true),
    ]));
    return cloneElement(value, props);
  }
  if (Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, localizeValue(item, true)]));
  }
  return value;
}

function useOpsLocale() {
  const { isEnglish } = useLocale();
  return {
    isEnglish,
    t: (zh, en) => (isEnglish ? en : zh),
    number: (value) => formatNumber(value, isEnglish),
    money: (value) => formatMoney(value, isEnglish),
  };
}
const go = (navigate, path) => {
  if (typeof navigate === "function") navigate(path);
};

const STATUS = {
  paid: ["已支付", "green"],
  pending: ["确认中", "yellow"],
  expired: ["已过期", "gray"],
  refunded: ["已退款", "gray"],
  partially_refunded: ["部分退款", "yellow"],
  failed: ["失败", "red"],
  settled: ["已结算", "green"],
  reserved: ["已预占", "blue"],
  released: ["已释放", "gray"],
  granted: ["已发放", "green"],
  running: ["运行中", "blue"],
  queued: ["排队中", "yellow"],
  completed: ["已完成", "green"],
  healthy: ["正常", "green"],
  degraded: ["降级", "yellow"],
  closed: ["已停用", "gray"],
  review: ["需复核", "orange"],
  reconciled: ["已对账", "green"],
  mismatch: ["差异", "red"],
  active: ["生效中", "green"],
  draft: ["草稿", "gray"],
  received: ["已受理", "blue"],
  done: ["已完成", "green"],
};

const plans = {
  monthly: [
    {
      id: "month-lite",
      name: "轻量月卡",
      price: 39.9,
      credits: 60000,
      note: "适合单篇论文阶段性优化",
      meta: "30 天有效 · 非无限量",
    },
    {
      id: "month-pro",
      name: "专业月卡",
      price: 89.9,
      credits: 200000,
      note: "适合长论文与多轮修订",
      meta: "30 天有效 · 非无限量",
      featured: true,
    },
  ],
  packs: [
    {
      id: "pack-20k",
      name: "章节包",
      price: 19.9,
      credits: 20000,
      note: "轻量补充，不影响月卡",
      meta: "90 天有效",
    },
    {
      id: "pack-60k",
      name: "论文包",
      price: 49.9,
      credits: 60000,
      note: "适合一篇完整论文",
      meta: "90 天有效",
      featured: true,
    },
    {
      id: "pack-200k",
      name: "长文包",
      price: 129.9,
      credits: 200000,
      note: "适合多章节集中处理",
      meta: "180 天有效",
    },
  ],
};

const creditBuckets = [
  {
    id: "promo-1024",
    source: "内测赠送",
    kind: "赠送额度",
    remaining: 1200,
    total: 3000,
    expires: "2026-10-24",
    priority: 1,
  },
  {
    id: "monthly-lite-1031",
    source: "轻量月卡",
    kind: "月卡额度",
    remaining: 36820,
    total: 60000,
    expires: "2026-10-31",
    priority: 2,
  },
  {
    id: "pack-20k-0108",
    source: "章节包",
    kind: "独立字数包",
    remaining: 18400,
    total: 20000,
    expires: "2027-01-08",
    priority: 3,
  },
];

const usageRows = [
  { id: "J-26A91", time: "10-10 14:32", event: "深度保真改写", detail: "4,812 字 × 1.5", amount: -7218, status: "settled" },
  { id: "J-26A88", time: "10-10 13:08", event: "平衡保真改写", detail: "任务处理中", amount: -2460, status: "reserved" },
  { id: "J-269F2", time: "10-09 22:17", event: "任务失败回退", detail: "超时，预占全额归还", amount: 3150, status: "released" },
  { id: "O-10831", time: "10-08 09:44", event: "购买章节包", detail: "演示订单确认后发放 20,000 字", amount: 20000, status: "granted" },
  { id: "J-26311", time: "10-07 18:05", event: "保守保真改写", detail: "1,202 字 × 1.0", amount: -1202, status: "settled" },
  { id: "T-10001", time: "10-01 10:00", event: "内测体验发放", detail: "一次性体验额度", amount: 3000, status: "granted" },
];

const orderRows = [
  { id: "RT-20261008-0831", at: "2026-10-08 09:44", product: "章节包", amount: 19.9, method: "支付宝（演示）", status: "paid", reconciliation: "reconciled" },
  { id: "RT-20261002-0714", at: "2026-10-02 21:18", product: "轻量月卡", amount: 39.9, method: "微信支付（演示）", status: "paid", reconciliation: "reconciled" },
  { id: "RT-20260918-0306", at: "2026-09-18 16:22", product: "论文包", amount: 49.9, method: "支付宝（演示）", status: "refunded", reconciliation: "reconciled" },
  { id: "RT-20261010-0922", at: "2026-10-10 15:01", product: "专业月卡", amount: 89.9, method: "微信支付（演示）", status: "pending", reconciliation: "pending" },
  { id: "RT-20260907-0098", at: "2026-09-07 11:36", product: "章节包", amount: 19.9, method: "支付宝（演示）", status: "failed", reconciliation: "mismatch" },
];

const allPlans = [...plans.monthly, ...plans.packs];

function requestedPlanFromHash() {
  if (typeof window === "undefined") return plans.monthly[0];
  const query = window.location.hash.split("?")[1] || "";
  const id = new URLSearchParams(query).get("plan");
  return allPlans.find((plan) => plan.id === id) || plans.monthly[0];
}

function Page({ children, className = "" }) {
  const { isEnglish } = useLocale();
  return <div className={`ops-page ${className}`}>{localizeValue(children, isEnglish)}</div>;
}

function PageHeader({ eyebrow, title, description, children, onBack }) {
  const { t } = useOpsLocale();
  return (
    <header className="ops-page-header">
      <div className="ops-page-heading">
        {onBack && (
          <button className="ops-back" type="button" onClick={onBack} aria-label={t("返回", "Back")}>
            <ArrowLeft size={18} weight="bold" />
          </button>
        )}
        <div>
          <p className="ops-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          {description && <p className="ops-description">{description}</p>}
        </div>
      </div>
      {children && <div className="ops-header-actions">{children}</div>}
    </header>
  );
}

function Button({ children, tone = "plain", icon: Icon, className = "", ...props }) {
  return (
    <button className={`ops-button ops-button--${tone} ${className}`} type="button" {...props}>
      {Icon && <Icon size={18} weight="bold" />}
      <span>{children}</span>
    </button>
  );
}

function StatusPill({ status, label }) {
  const { isEnglish } = useLocale();
  const [defaultLabel, tone] = STATUS[status] || [status, "gray"];
  return <span className={`ops-status ops-status--${tone}`}><span />{localizeValue(label || defaultLabel, isEnglish)}</span>;
}

function Tabs({ items, value, onChange, label = "切换视图" }) {
  const { isEnglish } = useLocale();
  const localizedItems = localizeValue(items, isEnglish);
  return (
    <div className="ops-tabs" role="tablist" aria-label={translateText(label, isEnglish)}>
      {localizedItems.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          className={value === item.value ? "is-active" : ""}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {item.count !== undefined && <b>{item.count}</b>}
        </button>
      ))}
    </div>
  );
}

function Metric({ label, value, note, tone = "plain", icon: Icon }) {
  return (
    <div className={`ops-metric ops-metric--${tone}`}>
      <div className="ops-metric-label">{Icon && <Icon size={18} weight="bold" />}{label}</div>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

function Section({ title, kicker, action, children, className = "" }) {
  return (
    <section className={`ops-section ${className}`}>
      {(title || action) && (
        <div className="ops-section-head">
          <div>
            {kicker && <p>{kicker}</p>}
            {title && <h2>{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function Progress({ value, max, tone = "blue" }) {
  const { t } = useOpsLocale();
  const width = max ? Math.max(3, Math.min(100, (value / max) * 100)) : 0;
  const normalizedValue = max ? Math.max(0, Math.min(max, value)) : 0;
  return (
    <div
      className="ops-progress"
      role="progressbar"
      aria-label={t(`进度 ${value} / ${max}`, `Progress ${value} / ${max}`)}
      aria-valuemin={0}
      aria-valuemax={max || 100}
      aria-valuenow={normalizedValue}
    >
      <span className={`ops-progress--${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

function Toggle({ checked, onChange, label, note }) {
  return (
    <button type="button" className="ops-toggle-row" onClick={() => onChange(!checked)} role="switch" aria-checked={checked} aria-label={label}>
      <span><b>{label}</b>{note && <small>{note}</small>}</span>
      <span className={`ops-switch ${checked ? "is-on" : ""}`} aria-hidden="true"><i /></span>
    </button>
  );
}

function FilterBar({ query, onQuery, placeholder = "搜索", children }) {
  const { isEnglish } = useLocale();
  return (
    <div className="ops-filterbar">
      <label className="ops-search">
        <MagnifyingGlass size={18} />
        <input value={query} onChange={(event) => onQuery(event.target.value)} placeholder={translateText(placeholder, isEnglish)} />
      </label>
      {children}
    </div>
  );
}

function Table({ columns, rows, empty = "暂无记录", onRow }) {
  const { isEnglish } = useLocale();
  const localizedColumns = localizeValue(columns, isEnglish);
  const localizedRows = localizeValue(rows, isEnglish);
  return (
    <div className="ops-table-wrap">
      <table className="ops-table">
        <thead><tr>{localizedColumns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead>
        <tbody>
          {localizedRows.length === 0 ? (
            <tr><td colSpan={localizedColumns.length} className="ops-empty-cell">{translateText(empty, isEnglish)}</td></tr>
          ) : localizedRows.map((row, index) => (
            <tr
              key={row.id || index}
              onClick={onRow ? () => onRow(rows[index]) : undefined}
              onKeyDown={onRow ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onRow(rows[index]);
                }
              } : undefined}
              tabIndex={onRow ? 0 : undefined}
              aria-label={onRow ? (isEnglish ? `View order ${row.id || index + 1}` : `查看订单 ${row.id || index + 1}`) : undefined}
              className={onRow ? "is-clickable" : ""}
            >
              {localizedColumns.map((column) => (
                <td key={column.key} data-label={column.label}>
                  {localizeValue(column.render ? column.render(row) : row[column.key], isEnglish)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DemoFeedback({ children, tone = "blue" }) {
  if (!children) return null;
  return (
    <div className={`ops-action-feedback ops-action-feedback--${tone}`} role="status" aria-live="polite">
      <CheckCircle size={18} weight="fill" />
      <span>{children}</span>
    </div>
  );
}

function SafeDeleteFlow({ kind = "documents" }) {
  const { isEnglish } = useLocale();
  const [stage, setStage] = useState("idle");
  const [scope, setScope] = useState("single");
  const [documentId, setDocumentId] = useState("rt-014");
  const [confirmed, setConfirmed] = useState(false);
  const isAccount = kind === "account";
  const titleId = `${kind}-delete-title`;
  const documentNames = {
    "rt-014": "教育公平研究.docx",
    "rt-009": "平台经济与劳动关系.docx",
    "rt-006": "公共政策评估方法.docx",
  };
  const scopeLabel = scope === "single"
    ? `逐文档 · ${documentNames[documentId]}`
    : isAccount ? "全部账号与云端数据" : "全部已保存文档与版本";

  useEffect(() => {
    if (stage !== "processing") return undefined;
    const timer = window.setTimeout(() => setStage("complete"), 700);
    return () => window.clearTimeout(timer);
  }, [stage]);

  const reset = () => {
    setStage("idle");
    setScope("single");
    setDocumentId("rt-014");
    setConfirmed(false);
  };

  return localizeValue((
    <section className={`ops-delete-zone ${stage !== "idle" ? "is-open" : ""}`} aria-labelledby={titleId}>
      <div className="ops-delete-summary">
        <div>
          <p className="ops-eyebrow">{isAccount ? "ACCOUNT CONTROL" : "RIGHT TO DELETE"}</p>
          <b id={titleId}>{isAccount ? "删除账号与云端数据" : "删除已保存文档和版本"}</b>
          <p>{isAccount ? "可先逐文档处理，也可演示全部账号数据删除流程。" : "可逐篇选择文档，或演示处理全部已保存内容。"}</p>
        </div>
        {stage === "idle" && <Button icon={Trash} onClick={() => setStage("scope")}>开始安全流程</Button>}
      </div>

      {stage === "scope" && (
        <div className="ops-delete-flow" aria-live="polite">
          <div className="ops-delete-step"><span>1</span><div><b>选择范围</b><small>先确认是逐文档，还是全部处理。</small></div></div>
          <div className="ops-delete-scope" role="radiogroup" aria-label="删除范围">
            <button type="button" role="radio" aria-checked={scope === "single"} className={scope === "single" ? "is-selected" : ""} onClick={() => { setScope("single"); setConfirmed(false); }}>
              <FileText size={22} weight="fill" /><span><b>逐文档</b><small>只演示处理一篇指定文档</small></span>
            </button>
            <button type="button" role="radio" aria-checked={scope === "all"} className={scope === "all" ? "is-selected" : ""} onClick={() => { setScope("all"); setConfirmed(false); }}>
              <Trash size={22} weight="fill" /><span><b>{isAccount ? "全部账号数据" : "全部已保存内容"}</b><small>进入范围更大的二次确认</small></span>
            </button>
          </div>
          {scope === "single" && (
            <label className="ops-delete-select">
              <span>选择文档</span>
              <select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
                {Object.entries(documentNames).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
          )}
          <div className="ops-delete-actions">
            <Button onClick={reset}>取消</Button>
            <Button tone="blue" icon={ArrowRight} onClick={() => { setConfirmed(false); setStage("confirm"); }}>继续核对</Button>
          </div>
        </div>
      )}

      {stage === "confirm" && (
        <div className="ops-delete-flow ops-delete-flow--confirm" aria-live="polite">
          <div className="ops-delete-step"><span>2</span><div><b>二次确认</b><small>范围：{scopeLabel}</small></div></div>
          <div className="ops-note ops-note--yellow">
            <ShieldWarning size={28} weight="fill" />
            <div><b>这是本地 UI 演示</b><p>确认后只会展示处理与完成状态，绝不会删除真实账号、文档、版本或交易记录。</p></div>
          </div>
          <label className="ops-delete-confirm">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            <span>我已核对演示范围：{scopeLabel}</span>
          </label>
          <div className="ops-delete-actions">
            <Button onClick={() => { setConfirmed(false); setStage("scope"); }}>返回修改</Button>
            <Button tone="blue" icon={Trash} disabled={!confirmed} onClick={() => setStage("processing")}>确认演示处理</Button>
          </div>
        </div>
      )}

      {stage === "processing" && (
        <div className="ops-delete-flow ops-delete-result" role="status" aria-live="assertive">
          <Clock size={36} weight="fill" />
          <div><b>正在演示处理</b><p>正在生成本地状态反馈，没有发送任何删除请求。</p></div>
        </div>
      )}

      {stage === "complete" && (
        <div className="ops-delete-flow ops-delete-result ops-delete-result--complete" role="status" aria-live="polite">
          <CheckCircle size={38} weight="fill" />
          <div><b>演示流程已完成</b><p>{scopeLabel} 未发生真实变更；账号、文档和数据仍完整保留。</p></div>
          <Button tone="green" icon={ArrowsClockwise} onClick={reset}>重新演示</Button>
        </div>
      )}
    </section>
  ), isEnglish);
}

function PlanCard({ plan, selected, onSelect, compact = false }) {
  const { isEnglish, number, money } = useOpsLocale();
  return localizeValue((
    <button
      type="button"
      className={`ops-plan ${selected ? "is-selected" : ""} ${compact ? "is-compact" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="ops-plan-radio">{selected && <Check size={14} weight="bold" />}</span>
      <span className="ops-plan-copy">
        <span className="ops-plan-titleline"><b>{plan.name}</b>{plan.featured && <em>推荐</em>}</span>
        <span className="ops-plan-price"><strong>{money(plan.price)}</strong>{plan.id.startsWith("month") && <small>/ 30天</small>}</span>
        <span>{number(plan.credits)} 字额度</span>
        <small>{plan.note}</small>
        <small>{plan.meta}</small>
      </span>
    </button>
  ), isEnglish);
}

function platformDate(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatPlatformTime(value, isEnglish) {
  const date = platformDate(value);
  if (!date) return value ? String(value) : "—";
  return new Intl.DateTimeFormat(isEnglish ? "en" : "zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function platformPlanKind(kind, isEnglish) {
  const labels = {
    free: ["免费方案", "Free plan"],
    subscription: ["月卡额度", "One-time pass credits"],
    pack: ["独立字数包", "Standalone credit pack"],
    trial: ["体验额度", "Trial credits"],
  };
  return (labels[kind] || [kind || "额度", kind || "Credits"])[isEnglish ? 1 : 0];
}

function LivePlanCard({ plan, onSelect, selected = false }) {
  const { isEnglish, number, money } = useOpsLocale();
  const price = Number(plan.price_fen || 0) / 100;
  const Tag = onSelect ? "button" : "article";
  return (
    <Tag className={`ops-plan${selected ? " is-selected" : ""}`} type={onSelect ? "button" : undefined} onClick={onSelect} aria-pressed={onSelect ? selected : undefined}>
      <span className="ops-plan-radio"><Package size={16} weight="fill" /></span>
      <span className="ops-plan-copy">
        <span className="ops-plan-titleline"><b>{localizedPlanName(plan, isEnglish)}</b><em>{platformPlanKind(plan.kind, isEnglish)}</em></span>
        <span className="ops-plan-price"><strong>{money(price)}</strong>{plan.kind === "subscription" && <small>/ {plan.valid_days || 30}{isEnglish ? " days" : "天"}</small>}</span>
        <span>{number(plan.credits)} {isEnglish ? "character credits" : "字额度"}</span>
        {plan.description && <small>{localizedPlanDescription(plan, isEnglish)}</small>}
        <small>{plan.valid_days ? (isEnglish ? `Valid for ${plan.valid_days} days` : `${plan.valid_days} 天有效`) : (isEnglish ? "No expiry returned" : "后端未返回有效期")}</small>
      </span>
    </Tag>
  );
}

function ledgerEventLabel(kind, isEnglish) {
  const labels = {
    grant: ["额度发放", "Credit grant"],
    reserve: ["任务预占", "Job reservation"],
    settle: ["任务结算", "Job settlement"],
    release: ["额度释放", "Credit release"],
    refund: ["退款冲正", "Refund reversal"],
  };
  return (labels[kind] || [kind || "账本事件", kind || "Ledger event"])[isEnglish ? 1 : 0];
}

function ledgerStatus(kind) {
  return ({ grant: "granted", reserve: "reserved", settle: "settled", release: "released", refund: "released" })[kind] || "received";
}

function ledgerDetail(entry, isEnglish) {
  const metadata = entry?.metadata && typeof entry.metadata === "object" ? entry.metadata : {};
  if (entry.kind === "reserve") {
    const parts = [metadata.strength];
    if (metadata.billable_chars !== undefined) parts.push(`${metadata.billable_chars} ${isEnglish ? "characters" : "字"}`);
    const multiplier = Number(metadata.multiplier_milli) / 1000;
    if (Number.isFinite(multiplier)) parts.push(`× ${multiplier}`);
    return parts.filter(Boolean).join(" · ") || (isEnglish ? "Reservation created" : "已创建预占");
  }
  if (entry.kind === "settle") {
    const parts = [];
    if (metadata.accepted !== undefined) parts.push(isEnglish ? `${metadata.accepted} accepted` : `通过 ${metadata.accepted} 项`);
    if (metadata.total_tokens !== undefined) parts.push(`${metadata.total_tokens} tokens`);
    if (metadata.llm_requests !== undefined) parts.push(isEnglish ? `${metadata.llm_requests} requests` : `${metadata.llm_requests} 次请求`);
    return parts.join(" · ") || (isEnglish ? "Reservation settled" : "预占已结算");
  }
  if (entry.kind === "release") {
    const unavailable = Number(metadata.expired_or_revoked_credits || 0);
    if (unavailable > 0) return isEnglish
      ? `${entry.delta} credits returned; ${unavailable} expired or revoked credits stayed unavailable`
      : `归还 ${entry.delta} 字；${unavailable} 字已过期或退款撤销，不再可用`;
    return isEnglish ? "Reserved credits returned" : "预占额度已归还";
  }
  if (entry.kind === "grant") return metadata.product_id || metadata.provider || (isEnglish ? "Credits added" : "额度已入账");
  return "—";
}

export function BillingPage({ navigate }) {
  const { isEnglish, number, t } = useOpsLocale();
  const { billing, config, plans: catalog = [], loading, error, refresh } = usePlatform();
  const [tab, setTab] = useState("overview");
  const [refreshing, setRefreshing] = useState(false);
  const balance = Number(billing?.balance || 0);
  const grants = Array.isArray(billing?.grants) ? billing.grants.filter((grant) => Number(grant.remaining) > 0) : [];
  const planLookup = useMemo(() => new Map(catalog.map((plan) => [plan.id, plan])), [catalog]);
  const currentPlan = billing?.plan_id ? (planLookup.get(billing.plan_id)
    || { id: billing.plan_id, name: billing.plan_name || billing.plan_id }) : null;
  const buckets = grants.map((grant, index) => ({
    ...grant,
    id: `${grant.product_id || grant.kind || "grant"}-${grant.expires_at || index}`,
    priority: index + 1,
    source: planLookup.get(grant.product_id)
      ? localizedPlanName(planLookup.get(grant.product_id), isEnglish)
      : (grant.product_id || platformPlanKind(grant.kind, isEnglish)),
    kindLabel: platformPlanKind(grant.kind, isEnglish),
    expiresLabel: grant.expires_at ? formatPlatformTime(grant.expires_at, isEnglish) : t("不过期", "No expiry"),
  }));
  const nextExpiry = [...grants]
    .filter((grant) => platformDate(grant.expires_at))
    .sort((left, right) => platformDate(left.expires_at) - platformDate(right.expires_at))[0];
  const payment = billing?.payment || config?.payment || {};
  const freePlans = catalog.filter((plan) => plan.kind === "free");
  const subscriptions = catalog.filter((plan) => plan.kind === "subscription");
  const packs = catalog.filter((plan) => plan.kind === "pack");

  const reload = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Page>
      <PageHeader eyebrow="MONEY / 额度中心" title="每一字，都有来路" description="余额、套餐与额度桶均直接读取当前平台账本。">
        <Button icon={ArrowsClockwise} onClick={reload} disabled={refreshing}>{refreshing ? "刷新中" : "刷新"}</Button>
        <Button icon={CreditCard} onClick={() => go(navigate, "/checkout/pro")}>购买额度</Button>
      </PageHeader>
      {error && <div className="ops-inline-notice"><WarningCircle size={18} weight="fill" /><span>{error}</span></div>}
      {loading && !billing && <div className="ops-inline-notice"><Clock size={18} weight="fill" /><span>正在读取平台账本…</span></div>}

      <div className="ops-metrics ops-metrics--4">
        <Metric label="当前可用" value={billing ? `${number(balance)} 字` : "—"} note={billing ? `${buckets.length} 个有效额度桶` : "等待账本响应"} tone="yellow" icon={Wallet} />
        <Metric label="当前方案" value={currentPlan ? localizedPlanName(currentPlan, isEnglish) : "—"} note={billing?.plan_id || "来自后端权益摘要"} icon={Receipt} />
        <Metric label="单任务上限" value={billing?.max_chars_per_job ? `${number(billing.max_chars_per_job)} 字` : "—"} note={(billing?.allowed_strengths || []).join(" / ") || "等待后端返回"} tone="blue" icon={Gauge} />
        <Metric label="最近到期" value={nextExpiry ? `${number(nextExpiry.remaining)} 字` : "—"} note={nextExpiry ? formatPlatformTime(nextExpiry.expires_at, isEnglish) : "没有有期限额"} tone="green" icon={CalendarBlank} />
      </div>

      <Tabs value={tab} onChange={setTab} items={[
        { value: "overview", label: "余额概览" },
        { value: "plans", label: "平台方案", count: catalog.length },
        { value: "buckets", label: "额度桶", count: buckets.length },
      ]} />

      {tab === "overview" && (
        <div className="ops-two-col ops-two-col--wide">
          <Section title="可用额度构成" kicker="LIVE ENTITLEMENTS" className="ops-shadow-card">
            <div className="ops-balance-hero">
              <div><span>账本可用余额</span><strong>{billing ? number(balance) : "—"}</strong><small>字</small></div>
              <p>{billing ? `${currentPlan ? localizedPlanName(currentPlan, isEnglish) : (isEnglish ? "Current credits" : "当前权益")} · ${isEnglish ? "account" : "账户"} ${billing.account_id || "—"}` : "正在等待账本摘要"}</p>
            </div>
            <div className="ops-rule-list">
              {buckets.map((bucket) => (
                <div className="ops-rule-row" key={bucket.id}>
                  <span className="ops-priority">{bucket.priority}</span>
                  <div><b>{bucket.source}</b><small>{bucket.kindLabel} · {bucket.expiresLabel}</small></div>
                  <div className="ops-align-right"><b>{number(bucket.remaining)} 字</b><small>当前剩余</small></div>
                </div>
              ))}
              {!loading && buckets.length === 0 && <div className="ops-empty-cell">当前没有独立额度桶</div>}
            </div>
          </Section>
          <Section title="账本规则" kicker="BACKEND CONTRACT">
            <div className="ops-note ops-note--blue"><ShieldCheck size={28} weight="fill" /><div><b>{isEnglish ? "Reserve first, then settle" : "先预占，再结算"}</b><p>{isEnglish ? "A failed task ends its reservation. Only credits that are still valid are returned; expired or refunded credits do not become available again." : "失败任务会结束预占；仅仍有效的额度归还，已过期或退款撤销的额度不会重新可用。"}</p></div></div>
            <ol className="ops-numbered">
              <li><span>01</span><div><b>真实余额</b><p>页面只展示账本摘要中的 balance，不推算历史消费。</p></div></li>
              <li><span>02</span><div><b>真实额度桶</b><p>仅展示 grants 返回的剩余量和到期时间。</p></div></li>
              <li><span>03</span><div><b>独立流水</b><p>发放、预占、结算和释放在额度明细中逐条展示。</p></div></li>
            </ol>
            <Button icon={Receipt} onClick={() => go(navigate, "/app/billing/usage")}>查看额度明细</Button>
          </Section>
        </div>
      )}

      {tab === "plans" && (
        <>
          <div className="ops-inline-notice"><Info size={18} weight="fill" /><span><b>{isEnglish ? "Plans come from the server catalog" : "套餐来自后端目录"}</b>{isEnglish ? ": " : "："}{isEnglish ? (payment.provider === "stripe" && payment.checkout_enabled ? (payment.live ? "Live Stripe checkout is enabled. Available payment methods are shown there." : "Stripe test checkout is enabled; no real charge is made.") : "Checkout is not currently available.") : (payment.notice || "支付与下单前端尚未接入。")}</span></div>
          {freePlans.length > 0 && <Section title="基础方案" kicker="BASE PLAN"><div className="ops-plan-grid ops-plan-grid--2">{freePlans.map((plan) => <LivePlanCard key={plan.id} plan={plan} />)}</div></Section>}
          {subscriptions.length > 0 && <Section title="30 天月卡（不自动续费）" kicker="30-DAY PASSES"><div className="ops-plan-grid ops-plan-grid--2">{subscriptions.map((plan) => <LivePlanCard key={plan.id} plan={plan} onSelect={() => go(navigate, `/checkout/pro?plan=${encodeURIComponent(plan.id)}`)} />)}</div></Section>}
          {packs.length > 0 && <Section title="独立字数包" kicker="TOP-UP PACKS"><div className="ops-plan-grid ops-plan-grid--3">{packs.map((plan) => <LivePlanCard key={plan.id} plan={plan} onSelect={() => go(navigate, `/checkout/pro?plan=${encodeURIComponent(plan.id)}`)} />)}</div></Section>}
          {!loading && catalog.length === 0 && <div className="ops-inline-notice"><WarningCircle size={18} weight="fill" /><span>平台暂未返回套餐目录。</span></div>}
        </>
      )}

      {tab === "buckets" && (
        <Section title="额度到期顺序" kicker="BACKEND GRANTS" className="ops-shadow-card">
          <Table rows={buckets} columns={[
            { key: "priority", label: "顺序", render: (row) => <span className="ops-priority">{row.priority}</span> },
            { key: "source", label: "来源", render: (row) => <><b>{row.source}</b><small className="ops-cell-note">{row.kindLabel}</small></> },
            { key: "remaining", label: "剩余", render: (row) => <b>{number(row.remaining)} 字</b> },
            { key: "expiresLabel", label: "到期时间" },
          ]} />
        </Section>
      )}
    </Page>
  );
}

export function UsagePage({ navigate }) {
  const { isEnglish, number } = useOpsLocale();
  const { billing, refreshBilling } = usePlatform();
  const displayedPlan = billing?.plan_id
    ? localizedPlanName({ id: billing.plan_id, name: billing.plan_name || billing.plan_id }, isEnglish)
    : (isEnglish ? "From the server ledger" : "来自后端账本摘要");
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState([]);
  const [loadingLedger, setLoadingLedger] = useState(true);
  const [ledgerError, setLedgerError] = useState("");
  const [exported, setExported] = useState(false);

  const loadLedger = useCallback(async () => {
    setLoadingLedger(true);
    setLedgerError("");
    try {
      const payload = await getApi("/api/billing/ledger?limit=100");
      setEntries(Array.isArray(payload?.entries) ? payload.entries : []);
      try {
        await refreshBilling();
      } catch {
        // The ledger remains useful even if its accompanying summary refresh fails.
      }
    } catch (nextError) {
      setLedgerError(nextError.message || (isEnglish ? "Unable to load the credit ledger" : "无法读取额度账本"));
    } finally {
      setLoadingLedger(false);
    }
  }, [isEnglish, refreshBilling]);

  useEffect(() => {
    void loadLedger();
  }, [loadLedger]);

  const rows = useMemo(() => entries.map((entry, index) => ({
    ...entry,
    id: `${entry.reference || "ledger"}-${entry.created_at || index}-${index}`,
    referenceLabel: entry.reference || "—",
    time: formatPlatformTime(entry.created_at, isEnglish),
    event: ledgerEventLabel(entry.kind, isEnglish),
    detail: ledgerDetail(entry, isEnglish),
    amount: Number(entry.delta || 0),
    balanceAfter: Number(entry.balance_after || 0),
    status: ledgerStatus(entry.kind),
  })), [entries, isEnglish]);
  const filtered = rows.filter((row) => (status === "all" || row.status === status) && `${row.referenceLabel}${row.event}${row.detail}`.toLowerCase().includes(query.toLowerCase()));
  const loadedIncreases = rows.reduce((sum, row) => sum + Math.max(0, row.amount), 0);
  const loadedDecreases = rows.reduce((sum, row) => sum + Math.abs(Math.min(0, row.amount)), 0);

  const exportCsv = () => {
    const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const csvRows = [
      ["time", "reference", "kind", "detail", "delta", "balance_after"],
      ...rows.map((row) => [row.time, row.referenceLabel, row.kind, row.detail, row.amount, row.balanceAfter]),
    ];
    const blob = new Blob([`\uFEFF${csvRows.map((row) => row.map(escape).join(",")).join("\n")}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rightthesis-ledger-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setExported(true);
  };

  return (
    <Page>
      <PageHeader eyebrow="MONEY / 额度账本" title="额度明细" description="发放、预占、结算和释放均来自真实后端流水。">
        <Button icon={ArrowsClockwise} onClick={loadLedger} disabled={loadingLedger}>{loadingLedger ? "刷新中" : "刷新"}</Button>
        <Button icon={exported ? Check : DownloadSimple} tone={exported ? "green" : "plain"} onClick={exportCsv} disabled={rows.length === 0}>{exported ? "CSV 已导出" : "导出 CSV"}</Button>
        <Button icon={CreditCard} onClick={() => go(navigate, "/checkout/pro")}>购买额度</Button>
      </PageHeader>
      <div className="ops-metrics ops-metrics--3">
        <Metric label="当前余额" value={billing ? `${number(billing.balance)} 字` : "—"} note={displayedPlan} tone="yellow" icon={Wallet} />
        <Metric label="已加载额度增加" value={`${number(loadedIncreases)} 字`} note={`最近 ${rows.length} 条流水`} tone="green" icon={TrendUp} />
        <Metric label="已加载额度减少" value={`${number(loadedDecreases)} 字`} note={`最近 ${rows.length} 条流水`} tone="blue" icon={Receipt} />
      </div>
      {ledgerError && <div className="ops-inline-notice"><WarningCircle size={18} weight="fill" /><span>{ledgerError}</span></div>}
      <Section title="最近账本流水" kicker={`RECENT LEDGER · ${rows.length} 条`} className="ops-shadow-card">
        <FilterBar query={query} onQuery={setQuery} placeholder="搜索任务号或事件">
          <Tabs value={status} onChange={setStatus} label="筛选账本" items={[
            { value: "all", label: "全部", count: rows.length },
            { value: "settled", label: "已结算" },
            { value: "reserved", label: "预占中" },
            { value: "released", label: "已释放" },
            { value: "granted", label: "发放" },
          ]} />
        </FilterBar>
        <Table rows={filtered} columns={[
          { key: "time", label: "时间" },
          { key: "referenceLabel", label: "流水 / 任务号", render: (row) => <code>{row.referenceLabel}</code> },
          { key: "event", label: "事件", render: (row) => <><b>{row.event}</b><small className="ops-cell-note">{row.detail}</small></> },
          { key: "amount", label: "额度变化", render: (row) => <b className={row.amount > 0 ? "ops-positive" : row.amount < 0 ? "ops-negative" : ""}>{row.amount > 0 ? "+" : ""}{number(row.amount)} 字</b> },
          { key: "balanceAfter", label: "变更后余额", render: (row) => `${number(row.balanceAfter)} 字` },
          { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} /> },
        ]} />
        <div className="ops-footnote"><Info size={16} /> 当前展示后端返回的最近 {rows.length} 条流水；页面不会外推未返回的历史统计。</div>
      </Section>
      <div className="ops-footnote"><Info size={16} /> 计费强度、字符数与倍率以各条流水保存的 metadata 为准。</div>
    </Page>
  );
}

export function OrdersPage({ navigate }) {
  const { isEnglish, number, money } = useOpsLocale();
  const [orders, setOrders] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    getApi("/api/billing/orders")
      .then((result) => setOrders(result.orders || []))
      .catch((nextError) => setError(nextError.message || "订单读取失败"));
  }, []);
  return (
    <Page>
      <PageHeader eyebrow="MONEY / 订单" title="订单与付款" description="仅展示当前账户的真实账本订单；测试交易会明确标记。">
        <Button onClick={() => go(navigate, "/app/billing")}>返回额度中心</Button>
      </PageHeader>
      <Section title="最近订单" kicker="ACCOUNT ORDERS" className="ops-shadow-card">
        {error && <div className="ops-inline-notice"><WarningCircle size={18} weight="fill" /><span>{error}</span></div>}
        {!error && orders.length === 0 && <div className="ops-inline-notice"><Info size={18} weight="fill" /><span>{isEnglish ? "This account has no orders yet." : "当前账户还没有订单。"}</span></div>}
        {orders.length > 0 && <Table rows={orders} columns={[
          { key: "order_id", label: "订单号", render: (row) => <code>{row.order_id}</code> },
          { key: "product_id", label: "套餐" },
          { key: "amount_fen", label: "金额", render: (row) => money(row.amount_fen / 100) },
          { key: "credits", label: "额度", render: (row) => `${number(row.credits)} ${isEnglish ? "characters" : "字"}` },
          { key: "provider", label: "通道", render: (row) => row.provider === "stripe" ? (row.live ? (isEnglish ? "Stripe live" : "Stripe 正式") : (isEnglish ? "Stripe test" : "Stripe 测试")) : (isEnglish ? "Local simulation" : "本地模拟") },
          { key: "status", label: "状态", render: (row) => {
            const labels = {
              paid: isEnglish ? "Paid" : "已支付",
              refunded: isEnglish ? "Refunded" : "已退款",
              partially_refunded: isEnglish ? "Partially refunded" : "部分退款",
              expired: isEnglish ? "Expired without payment" : "未付款已过期",
              failed: isEnglish ? "Checkout unavailable" : "收银台创建失败",
              pending: isEnglish ? "Awaiting payment" : "待付款",
            };
            return <StatusPill status={row.status} label={labels[row.status] || row.status} />;
          } },
        ]} />}
      </Section>
    </Page>
  );
}

export function CheckoutPage({ navigate }) {
  const { isEnglish, number, money } = useOpsLocale();
  const { plans: catalog = [], billing, config, session, loading, refresh, refreshBilling } = usePlatform();
  const query = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams((window.location.hash.split("?")[1] || ""));
  const requestedPlanId = query.get("plan") || "";
  const returnedOrderId = query.get("order") || "";
  const returnResult = query.get("result") || "";
  const paidCatalog = catalog.filter((plan) => Number(plan.price_fen) > 0);
  const [selectedId, setSelectedId] = useState(() => {
    if (requestedPlanId) return requestedPlanId;
    try {
      const saved = window.sessionStorage.getItem("rightthesis-checkout-plan") || "";
      window.sessionStorage.removeItem("rightthesis-checkout-plan");
      return saved;
    } catch {
      return "";
    }
  });
  const [busy, setBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");
  const [returnedOrder, setReturnedOrder] = useState(null);
  const selected = paidCatalog.find((plan) => plan.id === selectedId) || paidCatalog[0];
  const payment = billing?.payment || config?.payment || {};
  const signedIn = session?.authMode === "accounts" && session?.authenticated && session?.kind !== "guest";
  const canPay = signedIn && payment.provider === "stripe" && payment.checkout_enabled === true;
  const isLive = payment.live === true;

  useEffect(() => { if (requestedPlanId) setSelectedId(requestedPlanId); }, [requestedPlanId]);
  useEffect(() => {
    if (!returnedOrderId) return undefined;
    let active = true;
    let attempts = 0;
    const check = async () => {
      attempts += 1;
      try {
        const result = await getApi(`/api/billing/orders/${encodeURIComponent(returnedOrderId)}`);
        if (!active) return;
        setReturnedOrder(result.order);
        if (["paid", "refunded", "expired", "failed"].includes(result.order?.status)) {
          if (result.order.status === "paid") await refreshBilling();
          return;
        }
      } catch (nextError) {
        if (active) setCheckoutError(isEnglish ? "Could not read the order status. Please retry from Orders." : (nextError.message || "订单状态读取失败"));
      }
      if (active && attempts < 15) window.setTimeout(check, 2000);
    };
    void check();
    return () => { active = false; };
  }, [returnedOrderId, refreshBilling, isEnglish]);

  const beginCheckout = async () => {
    if (!selected || !canPay || busy) return;
    setBusy(true);
    setCheckoutError("");
    try {
      const currentSession = await ensureSession(true);
      if (currentSession.authMode !== "accounts" || !currentSession.authenticated || currentSession.kind === "guest") {
        try {
          window.sessionStorage.setItem("rightthesis-auth-return", "/checkout/pro");
          window.sessionStorage.setItem("rightthesis-checkout-plan", selected.id);
        } catch {
          // A user can still sign in and reselect the plan without storage.
        }
        await refresh();
        navigate("/auth");
        return;
      }
      const idempotencyKey = `checkout_${crypto.randomUUID().replaceAll("-", "")}`;
      const result = await postApi("/api/billing/checkout", {
        product_id: selected.id, idempotency_key: idempotencyKey,
      });
      const target = new URL(result.checkout_url);
      if (target.protocol !== "https:" || target.hostname !== "checkout.stripe.com") {
        throw new Error(isEnglish ? "The checkout URL is invalid." : "收银台返回地址无效");
      }
      window.location.assign(target.href);
    } catch (nextError) {
      if (nextError.status === 401 || nextError.data?.code === "authentication_required") {
        try {
          window.sessionStorage.setItem("rightthesis-auth-return", "/checkout/pro");
          window.sessionStorage.setItem("rightthesis-checkout-plan", selected.id);
        } catch {
          // Authentication remains available even without browser storage.
        }
        await refresh();
        navigate("/auth");
      } else {
        setCheckoutError(isEnglish
          ? `Could not start checkout${nextError.status ? ` (HTTP ${nextError.status})` : ""}. Please retry or contact support.`
          : (nextError.message || "无法创建订单"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page className="ops-checkout-page">
      <PageHeader eyebrow={isLive ? "CHECKOUT / STRIPE" : "CHECKOUT / STRIPE TEST"} title={isEnglish ? "Choose credits" : "选择额度"} description={isEnglish ? `Choose card, WeChat Pay, or Alipay on Stripe Checkout. ${isLive ? "This is a live payment; availability depends on Stripe Checkout." : "Only test transactions are available."}` : `银行卡、微信支付或支付宝均在 Stripe 收银台选择；${isLive ? "正式收款，实际可用方式以收银台为准。" : "当前仅支持测试交易。"}`} onBack={() => go(navigate, "/app/billing")} />
      <div className="ops-checkout-grid">
        <div>
          <Section title="30 天月卡" kicker="ONE-TIME PASS">
            <div className="ops-plan-grid ops-plan-grid--2">{paidCatalog.filter((plan) => plan.kind === "subscription").map((plan) => <LivePlanCard key={plan.id} plan={plan} selected={selected?.id === plan.id} onSelect={() => setSelectedId(plan.id)} />)}</div>
          </Section>
          <Section title="独立字数包" kicker="TOP-UP PACKS">
            <div className="ops-plan-grid ops-plan-grid--3">{paidCatalog.filter((plan) => plan.kind === "pack").map((plan) => <LivePlanCard key={plan.id} plan={plan} selected={selected?.id === plan.id} onSelect={() => setSelectedId(plan.id)} />)}</div>
          </Section>
          <div className="ops-inline-notice"><Info size={18} weight="fill" /><span>{isEnglish ? "Passes are one-time purchases, valid for 30 days, and do not renew automatically. Credit packs are valid for 90 days. Prices and credits come from the server catalog." : "月卡一次购买、有效 30 天、不自动续费；字数包有效 90 天。所有金额和额度均来自服务端目录。"}</span></div>
        </div>
        <aside className="ops-checkout-summary ops-shadow-card">
          <p className="ops-eyebrow">ORDER SUMMARY</p>
          <h2>{selected ? localizedPlanName(selected, isEnglish) : (isEnglish ? "Loading plans" : "正在加载套餐")}</h2>
          <div className="ops-checkout-credit"><strong>{selected ? number(selected.credits) : "—"}</strong><span>{isEnglish ? "character credits" : "字可用额度"}</span></div>
          <dl>
            <div><dt>{isEnglish ? "Purchasing account" : "购买账号"}</dt><dd>{session?.user?.email || session?.user?.display_name || (isEnglish ? "Sign in first" : "请先登录")}</dd></div>
            <div><dt>产品金额</dt><dd>{selected ? money(Number(selected.price_fen) / 100) : "—"}</dd></div>
            <div><dt>付款方式</dt><dd>{isEnglish ? "Card / WeChat Pay / Alipay" : "银行卡 / 微信 / 支付宝"}</dd></div>
            <div className="ops-total"><dt>应付</dt><dd>{selected ? money(Number(selected.price_fen) / 100) : "—"}</dd></div>
          </dl>
          <div className="ops-note ops-note--yellow"><Info size={20} weight="fill" /><div><b>{isEnglish ? (isLive ? "Stripe live payment" : "Stripe test mode") : (isLive ? "Stripe 正式支付" : "Stripe 测试模式")}</b><p>{isEnglish ? (canPay ? (isLive ? "Live payment methods depend on availability in Stripe Checkout." : "Test checkout only; no real charge will be made.") : "Stripe Checkout is not available yet.") : (payment.notice || "支付通道尚未启用。")}</p></div></div>
          {checkoutError && <div className="ops-inline-notice"><WarningCircle size={18} weight="fill" /><span>{checkoutError}</span></div>}
          {returnedOrder?.status === "paid" && <div className="ops-payment-result ops-payment-result--success"><CheckCircle size={30} weight="fill" /><b>{isEnglish ? (returnedOrder.live ? "Payment confirmed; credits added" : "Test payment confirmed; credits added") : (returnedOrder.live ? "付款已确认，额度已到账" : "测试付款已确认，额度已到账")}</b><p>{isEnglish ? "Order" : "订单"} {returnedOrder.order_id}</p></div>}
          {returnedOrder?.status === "refunded" && <div className="ops-payment-result ops-payment-result--pending"><Info size={30} weight="fill" /><b>{isEnglish ? "Order refunded; unused credits revoked" : "订单已退款，未使用额度已撤销"}</b><p>{isEnglish ? "Order" : "订单"} {returnedOrder.order_id}</p></div>}
          {returnedOrder?.status === "partially_refunded" && <div className="ops-payment-result ops-payment-result--pending"><Info size={30} weight="fill" /><b>{isEnglish ? "Partial refund confirmed; unused credits adjusted" : "部分退款已确认，未用额度已调整"}</b><p>{isEnglish ? "Order" : "订单"} {returnedOrder.order_id}</p></div>}
          {returnedOrder?.status === "expired" && <div className="ops-payment-result ops-payment-result--pending"><Clock size={30} weight="fill" /><b>{isEnglish ? "Checkout expired without payment" : "收银台已过期，订单未付款"}</b><p>{isEnglish ? "No credits were issued. You can start a new checkout." : "未发放额度；可重新发起结账。"}</p></div>}
          {returnedOrder?.status === "failed" && <div className="ops-payment-result ops-payment-result--pending"><Info size={30} weight="fill" /><b>{isEnglish ? "Checkout could not be created" : "收银台创建失败"}</b><p>{isEnglish ? "No payment was started. You can retry." : "未发起付款；可重试。"}</p></div>}
          {returnedOrderId && (!returnedOrder || returnedOrder.status === "pending") && <div className="ops-payment-result ops-payment-result--pending"><Clock size={30} weight="fill" /><b>{isEnglish ? (returnResult === "cancel" ? "Back from checkout; payment not completed" : "Waiting for server payment confirmation") : (returnResult === "cancel" ? "已返回平台；订单未付款" : "等待服务端确认付款")}</b><p>{isEnglish ? "Credits are issued only after a verified Stripe callback confirms payment." : "只有 Stripe 签名回调确认成功后才会发放额度。"}</p></div>}
          <Button tone="blue" icon={CreditCard} className="ops-full-button" disabled={!canPay || !selected || busy || loading} onClick={beginCheckout}>{isEnglish ? (busy ? "Opening Stripe…" : isLive ? "Open secure Stripe Checkout" : "Open Stripe test checkout") : (busy ? "正在前往 Stripe…" : isLive ? "前往 Stripe 安全收银台" : "前往 Stripe 测试收银台")}</Button>
          <Button tone="plain" icon={Receipt} onClick={() => go(navigate, "/app/billing/orders")}>查看订单</Button>
          {!canPay && <div className="ops-inline-notice"><Info size={18} weight="fill" /><span>{isEnglish ? (!signedIn ? "Sign in before purchasing." : "Checkout opens after the server key and webhook are configured.") : (!signedIn ? "请先登录账户再购买。" : "完成服务端密钥和 Webhook 配置后，购买按钮才会开放。")}</span></div>}
        </aside>
      </div>
    </Page>
  );
}

function LegacyBillingPage({ navigate }) {
  const { number } = useOpsLocale();
  const [tab, setTab] = useState("overview");
  const totalRemaining = creditBuckets.reduce((sum, bucket) => sum + bucket.remaining, 0);
  const totalGranted = creditBuckets.reduce((sum, bucket) => sum + bucket.total, 0);

  return (
    <Page>
      <PageHeader eyebrow="MONEY / 额度中心" title="每一字，都有来路" description="月卡与独立字数包可以叠加；系统按最早到期的额度桶优先消耗。">
        <Button tone="blue" icon={Plus} onClick={() => go(navigate, "/checkout/pro")}>购买额度</Button>
      </PageHeader>

      <div className="ops-metrics ops-metrics--4">
        <Metric label="当前可用" value={`${number(totalRemaining)} 字`} note={`共 ${creditBuckets.length} 个有效额度桶`} tone="yellow" icon={Wallet} />
        <Metric label="本月已结算" value="11,420 字" note="不含处理中预占" icon={Receipt} />
        <Metric label="处理中预占" value="2,460 字" note="失败将自动释放" tone="blue" icon={Clock} />
        <Metric label="最近到期" value="1,200 字" note="2026-10-24 · 14 天后" tone="green" icon={CalendarBlank} />
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "overview", label: "余额概览" },
          { value: "plans", label: "内测方案" },
          { value: "buckets", label: "到期桶", count: 3 },
        ]}
      />

      {tab === "overview" && (
        <div className="ops-two-col ops-two-col--wide">
          <Section title="可用额度构成" kicker="STACKED ENTITLEMENTS" className="ops-shadow-card">
            <div className="ops-balance-hero">
              <div><span>合计可用</span><strong>{number(totalRemaining)}</strong><small>字</small></div>
              <Progress value={totalRemaining} max={totalGranted} tone="blue" />
              <p>总发放 {number(totalGranted)} 字 · 已消费 {number(totalGranted - totalRemaining)} 字</p>
            </div>
            <div className="ops-rule-list">
              {creditBuckets.map((bucket) => (
                <div className="ops-rule-row" key={bucket.id}>
                  <span className="ops-priority">{bucket.priority}</span>
                  <div><b>{bucket.source}</b><small>{bucket.kind} · 到期 {bucket.expires}</small></div>
                  <div className="ops-align-right"><b>{number(bucket.remaining)} 字</b><small>剩余 / {number(bucket.total)}</small></div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="消费规则" kicker="VERIFIABLE RULES">
            <div className="ops-note ops-note--blue">
              <ShieldCheck size={28} weight="fill" />
              <div><b>先预占，再结算</b><p>创建改写任务时预占额度；失败或没有候选通过守卫时，全额归还。</p></div>
            </div>
            <ol className="ops-numbered">
              <li><span>01</span><div><b>最早到期先用</b><p>赠送额度、月卡和字数包共同排序，避免临期额度浪费。</p></div></li>
              <li><span>02</span><div><b>分析与安全清理免费</b><p>仅模型保真改写计入字符额度。</p></div></li>
              <li><span>03</span><div><b>账本不可覆盖</b><p>发放、预占、结算与释放都保留独立流水。</p></div></li>
            </ol>
            <Button tone="plain" icon={Receipt} onClick={() => go(navigate, "/app/billing/usage")}>查看额度明细</Button>
          </Section>
        </div>
      )}

      {tab === "plans" && (
        <>
          <div className="ops-inline-notice"><Info size={18} weight="fill" /><span><b>内测参考方案</b>：用于验证用户需求与成本结构，不构成最终商业定价承诺。</span></div>
          <Section title="月卡" kicker="30-DAY PASS">
            <div className="ops-plan-grid ops-plan-grid--2">
              {plans.monthly.map((plan) => <PlanCard key={plan.id} plan={plan} onSelect={() => go(navigate, `/checkout/pro?plan=${encodeURIComponent(plan.id)}`)} />)}
            </div>
          </Section>
          <Section title="独立字数包" kicker="TOP-UP PACKS">
            <div className="ops-plan-grid ops-plan-grid--3">
              {plans.packs.map((plan) => <PlanCard key={plan.id} plan={plan} onSelect={() => go(navigate, `/checkout/pro?plan=${encodeURIComponent(plan.id)}`)} />)}
            </div>
          </Section>
        </>
      )}

      {tab === "buckets" && (
        <Section title="额度到期顺序" kicker="EARLIEST EXPIRY FIRST" className="ops-shadow-card">
          <Table
            rows={creditBuckets}
            columns={[
              { key: "priority", label: "消耗顺序", render: (row) => <span className="ops-priority">{row.priority}</span> },
              { key: "source", label: "来源", render: (row) => <><b>{row.source}</b><small className="ops-cell-note">{row.kind}</small></> },
              { key: "remaining", label: "剩余", render: (row) => <b>{number(row.remaining)} 字</b> },
              { key: "total", label: "初始额度", render: (row) => `${number(row.total)} 字` },
              { key: "expires", label: "到期日" },
              { key: "usage", label: "使用进度", render: (row) => <div className="ops-table-progress"><Progress value={row.total - row.remaining} max={row.total} /><small>{Math.round(((row.total - row.remaining) / row.total) * 100)}%</small></div> },
            ]}
          />
        </Section>
      )}
    </Page>
  );
}

function LegacyUsagePage({ navigate }) {
  const { number } = useOpsLocale();
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [exported, setExported] = useState(false);
  const filtered = usageRows.filter((row) => (status === "all" || row.status === status) && `${row.id}${row.event}${row.detail}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <Page>
      <PageHeader eyebrow="MONEY / 额度账本" title="额度明细" description="每次发放、预占、结算和释放都有独立流水，余额变化可追溯。">
        <Button icon={exported ? Check : DownloadSimple} tone={exported ? "green" : "plain"} onClick={() => setExported(true)}>{exported ? "CSV 已准备（演示）" : "导出 CSV"}</Button>
        <Button tone="blue" icon={Plus} onClick={() => go(navigate, "/checkout/pro")}>购买额度</Button>
      </PageHeader>
      <div className="ops-metrics ops-metrics--3">
        <Metric label="本月净消耗" value="11,420 字" note="已结算任务 7 次" tone="yellow" icon={TrendUp} />
        <Metric label="预占中" value="2,460 字" note="任务 J-26A88" tone="blue" icon={Clock} />
        <Metric label="失败归还" value="3,150 字" note="本月 1 次自动释放" tone="green" icon={ArrowsClockwise} />
      </div>
      <DemoFeedback tone="green">{exported ? "已在本地演示中生成 CSV 准备状态；没有下载或发送任何真实数据。" : ""}</DemoFeedback>
      <Section title="最近账本流水（节选）" kicker="RECENT LEDGER · 6 条" className="ops-shadow-card">
        <FilterBar query={query} onQuery={setQuery} placeholder="搜索任务号或事件">
          <Tabs value={status} onChange={setStatus} label="筛选账本" items={[
            { value: "all", label: "全部", count: usageRows.length },
            { value: "settled", label: "已结算" },
            { value: "reserved", label: "预占中" },
            { value: "released", label: "已释放" },
            { value: "granted", label: "发放" },
          ]} />
        </FilterBar>
        <Table rows={filtered} columns={[
          { key: "time", label: "时间" },
          { key: "id", label: "流水 / 任务号", render: (row) => <code>{row.id}</code> },
          { key: "event", label: "事件", render: (row) => <><b>{row.event}</b><small className="ops-cell-note">{row.detail}</small></> },
          { key: "amount", label: "额度变化", render: (row) => <b className={row.amount > 0 ? "ops-positive" : "ops-negative"}>{row.amount > 0 ? "+" : ""}{number(row.amount)} 字</b> },
          { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} /> },
        ]} />
        <div className="ops-footnote"><Info size={16} /> 当前仅展示最近 6 条流水；上方 11,420 字来自本月全部 7 个已结算任务。</div>
      </Section>
      <div className="ops-footnote"><Info size={16} /> 深度模式按 1.5 倍预估；最终规则以任务创建时展示并确认的计量快照为准。</div>
    </Page>
  );
}

function LegacyOrdersPage({ navigate }) {
  const { money } = useOpsLocale();
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(orderRows[0]);
  const [receiptShown, setReceiptShown] = useState(false);
  const filtered = orderRows.filter((row) => (status === "all" || row.status === status) && `${row.id}${row.product}${row.method}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <Page>
      <PageHeader eyebrow="MONEY / 订单" title="订单与付款" description="当前均为本地演示记录，不会连接支付渠道；支付、权益和对账状态仍分开呈现。">
        <Button tone="blue" icon={Plus} onClick={() => go(navigate, "/checkout/pro")}>新建订单</Button>
      </PageHeader>
      <Section title="全部订单" kicker="PAYMENT RECORDS" className="ops-shadow-card">
        <FilterBar query={query} onQuery={setQuery} placeholder="搜索订单号或产品">
          <Tabs value={status} onChange={setStatus} label="筛选订单" items={[
            { value: "all", label: "全部", count: orderRows.length },
            { value: "paid", label: "已支付" },
            { value: "pending", label: "确认中" },
            { value: "refunded", label: "已退款" },
            { value: "failed", label: "失败" },
          ]} />
        </FilterBar>
        <Table onRow={(row) => { setSelected(row); setReceiptShown(false); }} rows={filtered} columns={[
          { key: "id", label: "订单号", render: (row) => <code>{row.id}</code> },
          { key: "at", label: "创建时间" },
          { key: "product", label: "产品", render: (row) => <b>{row.product}</b> },
          { key: "method", label: "支付方式" },
          { key: "amount", label: "金额", render: (row) => <b>{money(row.amount)}</b> },
          { key: "status", label: "支付状态", render: (row) => <StatusPill status={row.status} /> },
          { key: "reconciliation", label: "对账", render: (row) => <StatusPill status={row.reconciliation} label={row.reconciliation === "pending" ? "待对账" : undefined} /> },
        ]} />
      </Section>
      {selected && (
        <aside className="ops-detail-strip" aria-live="polite">
          <div><span>当前选中</span><b>{selected.id}</b></div>
          <div><span>权益处理</span><b>{selected.status === "paid" ? "已幂等发放" : selected.status === "refunded" ? "已冲正" : "未发放"}</b></div>
          <div><span>核对依据</span><b>签名 · 金额 · 商户 · 状态</b></div>
          <Button icon={receiptShown ? Check : Receipt} tone={receiptShown ? "green" : "plain"} onClick={() => setReceiptShown(true)}>{receiptShown ? "凭证已展开" : "查看凭证"}</Button>
        </aside>
      )}
      <DemoFeedback tone="green">{receiptShown ? `演示凭证：${selected.id} · ${selected.product} · ${money(selected.amount)}。没有请求真实支付渠道。` : ""}</DemoFeedback>
    </Page>
  );
}

function LegacyCheckoutPage({ navigate, statePath }) {
  const { number, money } = useOpsLocale();
  const initialPlan = requestedPlanFromHash();
  const [kind, setKind] = useState(initialPlan.id.startsWith("pack-") ? "packs" : "monthly");
  const [selectedId, setSelectedId] = useState(initialPlan.id);
  const [result, setResult] = useState("idle");
  const [paymentMethod, setPaymentMethod] = useState("wechat");
  const selected = allPlans.find((plan) => plan.id === selectedId) || plans.monthly[0];
  const requestedPlanId = typeof window === "undefined" ? "" : new URLSearchParams((window.location.hash.split("?")[1] || "")).get("plan");

  useEffect(() => {
    const requested = allPlans.find((plan) => plan.id === requestedPlanId);
    if (!requested) return;
    setSelectedId(requested.id);
    setKind(requested.id.startsWith("pack-") ? "packs" : "monthly");
    setResult("idle");
  }, [requestedPlanId, statePath]);

  const switchKind = (next) => {
    setKind(next);
    setSelectedId(next === "monthly" ? "month-lite" : "pack-20k");
    setResult("idle");
  };

  return (
    <Page className="ops-checkout-page">
      <PageHeader eyebrow="CHECKOUT / 演示收银台" title="确认你的额度" description="这是交互原型，不会发起真实扣款。价格为内测参考方案。" onBack={() => go(navigate, "/app/billing")} />
      <div className="ops-checkout-grid">
        <div>
          <Tabs value={kind} onChange={switchKind} items={[
            { value: "monthly", label: "30 天月卡" },
            { value: "packs", label: "独立字数包" },
          ]} />
          <div className={`ops-plan-grid ${kind === "monthly" ? "ops-plan-grid--2" : "ops-plan-grid--3"}`}>
            {plans[kind].map((plan) => (
              <PlanCard key={plan.id} plan={plan} selected={selectedId === plan.id} onSelect={() => { setSelectedId(plan.id); setResult("idle"); }} compact />
            ))}
          </div>
          <div className="ops-inline-notice"><Coins size={19} weight="fill" /><span>新额度会与现有月卡、字数包叠加；消耗顺序按各额度桶的到期日决定。</span></div>
          <Section title="付款方式演示" kicker="PAYMENT METHOD">
            <div className="ops-payment-methods" role="radiogroup" aria-label="演示付款方式">
              <button className={paymentMethod === "wechat" ? "is-selected" : ""} type="button" role="radio" aria-checked={paymentMethod === "wechat"} onClick={() => { setPaymentMethod("wechat"); setResult("idle"); }}><span className="ops-pay-logo ops-pay-logo--wechat">微</span><b>微信支付（演示）</b>{paymentMethod === "wechat" ? <CheckCircle size={20} weight="fill" /> : <span />}</button>
              <button className={paymentMethod === "alipay" ? "is-selected" : ""} type="button" role="radio" aria-checked={paymentMethod === "alipay"} onClick={() => { setPaymentMethod("alipay"); setResult("idle"); }}><span className="ops-pay-logo ops-pay-logo--alipay">支</span><b>支付宝（演示）</b>{paymentMethod === "alipay" ? <CheckCircle size={20} weight="fill" /> : <span />}</button>
            </div>
            <DemoFeedback>{`已选择${paymentMethod === "wechat" ? "微信支付" : "支付宝"}演示流程；不会连接支付渠道。`}</DemoFeedback>
          </Section>
        </div>

        <aside className="ops-checkout-summary ops-shadow-card">
          <p className="ops-eyebrow">ORDER SUMMARY</p>
          <h2>{selected.name}</h2>
          <div className="ops-checkout-credit"><strong>{number(selected.credits)}</strong><span>字可用额度</span></div>
          <dl>
            <div><dt>产品金额</dt><dd>{money(selected.price)}</dd></div>
            <div><dt>付款方式</dt><dd>{paymentMethod === "wechat" ? "微信支付（演示）" : "支付宝（演示）"}</dd></div>
            <div><dt>优惠</dt><dd>—</dd></div>
            <div className="ops-total"><dt>应付</dt><dd>{money(selected.price)}</dd></div>
          </dl>
          <ul className="ops-check-list">
            <li><CheckCircle size={18} weight="fill" />分析与安全清理不扣额度</li>
            <li><CheckCircle size={18} weight="fill" />仅在本地模拟确认后展示权益</li>
            <li><CheckCircle size={18} weight="fill" />订单、退款与额度流水可核对</li>
          </ul>

          {result === "idle" && <Button tone="blue" icon={CreditCard} className="ops-full-button" onClick={() => setResult("processing")}>演示提交订单</Button>}
          {result === "processing" && (
            <div className="ops-payment-result ops-payment-result--pending">
              <Clock size={34} weight="fill" />
              <b>等待服务端确认</b>
              <p>浏览器回跳只负责展示；验签和订单核对完成前不会增加额度。</p>
              <div className="ops-demo-actions">
                <Button tone="green" icon={CheckCircle} onClick={() => setResult("success")}>模拟成功</Button>
                <Button tone="plain" icon={XCircle} onClick={() => setResult("failed")}>模拟失败</Button>
              </div>
            </div>
          )}
          {result === "success" && (
            <div className="ops-payment-result ops-payment-result--success">
              <SealCheck size={38} weight="fill" />
              <b>演示确认完成</b>
              <p>{number(selected.credits)} 字只在当前原型中展示，不会写入真实账本。</p>
              <Button tone="green" icon={ArrowRight} onClick={() => go(navigate, "/app/billing")}>查看额度</Button>
            </div>
          )}
          {result === "failed" && (
            <div className="ops-payment-result ops-payment-result--failed">
              <WarningCircle size={38} weight="fill" />
              <b>订单未完成</b>
              <p>未发放额度，也不会生成消费流水。</p>
              <Button icon={ArrowsClockwise} onClick={() => setResult("idle")}>重新演示</Button>
            </div>
          )}
          <small className="ops-legal-copy">继续即表示你已阅读价格、有效期、额度消耗和退款说明。当前页面仅为 UI 原型。</small>
        </aside>
      </div>
    </Page>
  );
}

export function AccountSettingsPage({ navigate }) {
  const { isEnglish } = useLocale();
  const { session, billing, refresh } = usePlatform();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const user = session?.user || {};
  const accountId = billing?.account_id || user.account_id || user.id || "—";
  const rawProviders = Array.isArray(user.providers)
    ? user.providers
    : Array.isArray(user.auth_providers)
      ? user.auth_providers
      : user.provider
        ? [user.provider]
        : [];
  const providers = rawProviders.map((provider) => typeof provider === "string" ? provider : provider?.provider).filter(Boolean);
  const isAccountUser = session?.authMode === "accounts" && session?.authenticated && session?.kind !== "guest";
  const isGuest = session?.kind === "guest" || session?.trialMode;
  const providerLabels = providers.map((provider) => provider === "google" ? "Google" : (isEnglish ? "Email + password" : "邮箱 + 密码"));

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    setSignOutError("");
    try {
      await logoutSession();
      await refresh();
      navigate("/auth");
    } catch (error) {
      setSignOutError(error.message || (isEnglish ? "Sign-out failed." : "退出登录失败。"));
    } finally {
      setSigningOut(false);
    }
  };

  if (!isAccountUser) {
    const title = isGuest
      ? (isEnglish ? "Anonymous trial account" : "匿名试用账户")
      : (isEnglish ? "Local development access" : "本地开发访问");
    return (
      <Page>
        <PageHeader
          eyebrow={isEnglish ? "ACCOUNT / ACCESS" : "ACCOUNT / 访问状态"}
          title={title}
          description={isEnglish ? "Sign in or register for a verified account. Saved manuscripts and credits are tied to that account; unsaved browser drafts remain on this device." : "登录或注册后，已保存文稿和额度会绑定账户；未同步的浏览器草稿仍只保留在当前设备。"}
        />
        <Section title={isEnglish ? "Current access" : "当前访问方式"} kicker="CURRENT SESSION" className="ops-shadow-card">
          <div className="ops-note ops-note--yellow"><UserCircle size={28} weight="fill" /><div><b>{title}</b><p>{isEnglish ? `Backend account reference: ${accountId}` : `后端账户标识：${accountId}`}</p></div></div>
          <ol className="ops-numbered">
            <li><span>01</span><div><b>{isEnglish ? "Google or verified email" : "Google 或已验证邮箱"}</b><p>{isEnglish ? "Choose Google, or register an email account and complete inbox verification." : "可使用 Google，或注册邮箱账户并完成收件箱验证。"}</p></div></li>
            <li><span>02</span><div><b>{isEnglish ? "Credits follow the account" : "额度跟随账户"}</b><p>{isEnglish ? "A signed-in identity owns its saved manuscripts, usage ledger, and orders." : "已登录账户保存文稿、用量账本和订单。"}</p></div></li>
          </ol>
          <div className="ops-header-actions"><Button tone="blue" icon={UserCircle} onClick={() => navigate("/auth")}>{isEnglish ? "Sign in or register" : "登录或注册"}</Button></div>
        </Section>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader
        eyebrow={isEnglish ? "ACCOUNT / VERIFIED" : "ACCOUNT / 已验证"}
        title={isEnglish ? "Account and sign-in" : "账户与登录"}
        description={isEnglish ? "Review the verified identity attached to saved manuscripts, credits, usage, and orders." : "查看与已保存文稿、额度、用量和订单绑定的已验证身份。"}
      >
        <Button icon={SignOut} onClick={handleSignOut} disabled={signingOut}>{signingOut ? (isEnglish ? "Signing out…" : "正在退出…") : (isEnglish ? "Sign out" : "退出登录")}</Button>
      </PageHeader>
      <div className="ops-two-col ops-two-col--wide">
        <Section title={isEnglish ? "Verified identity" : "已验证身份"} kicker="LIVE ACCOUNT" className="ops-shadow-card">
          <div className="ops-note ops-note--green"><ShieldCheck size={28} weight="fill" /><div><b>{user.display_name || user.name || (isEnglish ? "RightThesis account" : "RightThesis 账户")}</b><p>{user.email || (isEnglish ? "Verified provider account" : "已验证的登录账户")}</p></div></div>
          <div className="ops-rule-list">
            <div className="ops-rule-row"><Envelope size={22} weight="fill" /><div><b>{isEnglish ? "Email" : "邮箱"}</b><small>{user.email ? `${user.email}${user.email_verified ? (isEnglish ? " · verified" : " · 已验证") : ""}` : (isEnglish ? "Provided by the connected identity provider" : "由已连接的身份提供方返回")}</small></div></div>
            <div className="ops-rule-row">{providers.includes("google") ? <GoogleLogo size={22} weight="fill" /> : <LockKey size={22} weight="fill" />}<div><b>{isEnglish ? "Sign-in methods" : "登录方式"}</b><small>{providerLabels.length ? providerLabels.join(" + ") : (isEnglish ? "Verified account session" : "已验证账户会话")}</small></div></div>
            <div className="ops-rule-row"><UserCircle size={22} weight="fill" /><div><b>{isEnglish ? "Account reference" : "账户标识"}</b><small>{accountId}</small></div></div>
          </div>
        </Section>
        <Section title={isEnglish ? "Account boundaries" : "账户能力边界"} kicker="WHAT THIS ENABLES">
          <ol className="ops-numbered">
            <li><span>01</span><div><b>{isEnglish ? "Recoverable access" : "可恢复访问"}</b><p>{isEnglish ? "Email accounts can reset their password after inbox verification; Google accounts use Google OAuth." : "邮箱账户可在收件箱验证后重置密码；Google 账户使用 Google OAuth。"}</p></div></li>
            <li><span>02</span><div><b>{isEnglish ? "Account-scoped credits" : "账户级额度"}</b><p>{isEnglish ? "The current balance and usage ledger belong to this backend account." : "当前余额与用量账本归属于该后端账户。"}</p></div></li>
            <li><span>03</span><div><b>{isEnglish ? "Saved manuscripts follow the account" : "已保存文稿跟随账户"}</b><p>{isEnglish ? "Saved manuscripts and completed tasks can be reopened after signing in on another device. Unsynced edits remain in this browser until saved." : "已保存文稿和完成的任务可在其他设备登录后重新打开；未同步编辑须保存成功后才会出现在其他设备。"}</p></div></li>
          </ol>
          <div className="ops-header-actions"><Button icon={Wallet} onClick={() => navigate("/app/billing")}>{isEnglish ? "View credits" : "查看额度"}</Button><Button icon={ShieldCheck} onClick={() => navigate("/app/settings/privacy")}>{isEnglish ? "Privacy status" : "隐私状态"}</Button></div>
          {signOutError && <div className="ops-note ops-note--yellow" role="alert"><WarningCircle size={24} weight="fill" /><div><b>{isEnglish ? "Could not sign out" : "无法退出登录"}</b><p>{signOutError}</p></div></div>}
        </Section>
      </div>
    </Page>
  );
}

function LegacyAccountAccessPage({ navigate }) {
  const { isEnglish } = useLocale();
  const { session, billing } = usePlatform();
  const accountId = billing?.account_id || session?.user?.account_id || session?.user?.id || "—";
  const accessMode = session?.trialMode
    ? (isEnglish ? "Anonymous trial session" : "匿名试用会话")
    : (isEnglish ? "Local development session" : "本地开发会话");

  return (
    <Page>
      <PageHeader
        eyebrow={isEnglish ? "ACCOUNT / ACCESS" : "ACCOUNT / 访问状态"}
        title={isEnglish ? "Production accounts are not connected yet" : "生产账号系统尚未接入"}
        description={isEnglish ? "This build uses the access mode returned by the local backend. It does not simulate email, passwords, devices, or account recovery." : "当前版本使用本地后端返回的访问模式，不模拟邮箱、密码、登录设备或账号恢复。"}
      />
      <div className="ops-two-col ops-two-col--wide">
        <Section title={isEnglish ? "Current access" : "当前访问方式"} kicker="LIVE SESSION" className="ops-shadow-card">
          <div className="ops-note ops-note--green"><UserCircle size={28} weight="fill" /><div><b>{accessMode}</b><p>{isEnglish ? `Backend account reference: ${accountId}` : `后端账户标识：${accountId}`}</p></div></div>
          <ol className="ops-numbered">
            <li><span>01</span><div><b>{isEnglish ? "No user-managed key" : "无需用户配置 Key"}</b><p>{isEnglish ? "The rewrite model is configured by the platform." : "改写模型由平台统一配置。"}</p></div></li>
            <li><span>02</span><div><b>{isEnglish ? "No production identity" : "没有生产身份系统"}</b><p>{isEnglish ? "Email sign-in, verification, recovery, and cross-device sessions are not available." : "邮箱登录、验证、找回和跨设备会话均未开放。"}</p></div></li>
            <li><span>03</span><div><b>{isEnglish ? "No fake account actions" : "不提供虚假账号操作"}</b><p>{isEnglish ? "Profile edits, sign-out controls, and account deletion remain disabled until real APIs exist." : "在真实 API 接入前，资料编辑、设备退出和账号删除均保持停用。"}</p></div></li>
          </ol>
        </Section>
        <Section title={isEnglish ? "Available now" : "当前可用"} kicker="CONNECTED FEATURES">
          <div className="ops-rule-list">
            <div className="ops-rule-row"><ShieldCheck size={22} weight="fill" /><div><b>{isEnglish ? "Bilingual analysis and rewrite" : "中英文诊断与保真改写"}</b><small>{isEnglish ? "Uses the current backend session" : "使用当前后端会话"}</small></div></div>
            <div className="ops-rule-row"><Wallet size={22} weight="fill" /><div><b>{isEnglish ? "Credit ledger" : "额度账本"}</b><small>{isEnglish ? "Read-only balance and usage evidence" : "只读展示余额与用量证据"}</small></div></div>
          </div>
          <div className="ops-header-actions">
            <Button icon={Wallet} onClick={() => go(navigate, "/app/billing")}>{isEnglish ? "View credits" : "查看额度"}</Button>
            <Button icon={ShieldCheck} onClick={() => go(navigate, "/app/settings/privacy")}>{isEnglish ? "Privacy status" : "隐私状态"}</Button>
          </div>
        </Section>
      </div>
    </Page>
  );
}

function LegacyAccountSettingsPage({ navigate }) {
  const [name, setName] = useState("论文作者");
  const [email, setEmail] = useState("w***@example.com");
  const [saved, setSaved] = useState(false);
  const [securityMail, setSecurityMail] = useState(true);
  const [jobMail, setJobMail] = useState(false);
  const [iphoneActive, setIphoneActive] = useState(true);

  return (
    <Page>
      <PageHeader eyebrow="ACCOUNT / 账号" title="账号设置" description="用于恢复付费权益、同步订单和保护文档任务。">
        <Button tone={saved ? "green" : "blue"} icon={saved ? Check : undefined} onClick={() => setSaved(true)}>{saved ? "已保存" : "保存修改"}</Button>
      </PageHeader>
      <div className="ops-settings-grid">
        <nav className="ops-settings-nav" aria-label="设置导航">
          <button className="is-active" type="button"><UserCircle size={19} />账号资料</button>
          <button type="button" onClick={() => go(navigate, "/app/settings/privacy")}><ShieldCheck size={19} />隐私与数据</button>
          <button type="button" onClick={() => go(navigate, "/app/billing")}><Wallet size={19} />额度与订单</button>
        </nav>
        <div className="ops-settings-main">
          <Section title="基础资料" kicker="PROFILE" className="ops-shadow-card">
            <div className="ops-form-grid">
              <label><span>显示名称</span><input value={name} onChange={(event) => { setName(event.target.value); setSaved(false); }} /></label>
              <label><span>登录邮箱</span><input value={email} onChange={(event) => { setEmail(event.target.value); setSaved(false); }} /></label>
            </div>
            <p className="ops-form-help"><LockKey size={16} />订单、额度和任务均绑定到可恢复账号；邮箱验证后即可使用。</p>
          </Section>
          <Section title="通知" kicker="NOTIFICATIONS">
            <Toggle checked={securityMail} onChange={setSecurityMail} label="安全与登录提醒" note="新设备登录、邮箱变更和账号风险" />
            <Toggle checked={jobMail} onChange={setJobMail} label="长任务完成提醒" note="仅在超过 3 分钟的任务完成时发送" />
          </Section>
          <Section title="登录设备" kicker="ACTIVE SESSIONS">
            <div className="ops-rule-list">
              <div className="ops-rule-row"><span className="ops-device-icon"><HardDrives size={21} /></span><div><b>Mac · 当前设备</b><small>上海 · Chrome · 刚刚活跃</small></div><StatusPill status="active" label="当前" /></div>
              <div className="ops-rule-row"><span className="ops-device-icon"><HardDrives size={21} /></span><div><b>iPhone</b><small>{iphoneActive ? "上海 · Safari · 2 天前" : "会话已在本地演示中标记退出"}</small></div>{iphoneActive ? <Button onClick={() => setIphoneActive(false)}>退出</Button> : <StatusPill status="closed" label="已退出（演示）" />}</div>
            </div>
          </Section>
          <DemoFeedback tone="green">{!iphoneActive ? "已演示退出 iPhone 会话；未向任何真实设备发送指令。" : ""}</DemoFeedback>
          <SafeDeleteFlow kind="account" />
        </div>
      </div>
    </Page>
  );
}

export function PrivacySettingsPage({ navigate }) {
  const { isEnglish } = useLocale();
  const { session } = usePlatform();
  const [request, setRequest] = useState(null);
  const [confirmedEmail, setConfirmedEmail] = useState("");
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState("");
  const isAccountUser = session?.authMode === "accounts" && session?.authenticated;
  const email = session?.user?.email || "";

  useEffect(() => {
    if (!isAccountUser) return;
    getApi("/api/account/privacy-request")
      .then((result) => setRequest(result.request || null))
      .catch((error) => setFeedback(error.message || (isEnglish ? "Could not load privacy request." : "无法读取隐私申请。")));
  }, [isAccountUser, isEnglish]);

  const exportData = async () => {
    setBusy("export");
    setFeedback("");
    try {
      const result = await getApi("/api/account/data-export");
      const objectUrl = URL.createObjectURL(new Blob(
        [JSON.stringify(result, null, 2)], { type: "application/json;charset=utf-8" },
      ));
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "rightthesis-account-data.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setFeedback(isEnglish ? "Your account data export is downloading." : "账户数据导出文件已开始下载。")
    } catch (error) {
      setFeedback(error.message || (isEnglish ? "Export failed." : "导出失败。"));
    } finally {
      setBusy("");
    }
  };

  const requestDeletion = async () => {
    setBusy("delete");
    setFeedback("");
    try {
      const result = await postApi("/api/account/delete-request", {
        confirm_email: confirmedEmail.trim(),
      });
      setRequest(result.request);
      setConfirmedEmail("");
      setFeedback(isEnglish ? "Deletion request received. It is reviewed before any data is removed." : "删除申请已受理；在核对权益与备份后才会执行删除。")
    } catch (error) {
      setFeedback(error.message || (isEnglish ? "Request failed." : "申请失败。"));
    } finally {
      setBusy("");
    }
  };

  const cancelDeletion = async () => {
    setBusy("cancel");
    setFeedback("");
    try {
      const result = await postApi("/api/account/delete-request/cancel", {});
      setRequest(result.request);
      setFeedback(isEnglish ? "Deletion request cancelled." : "已取消删除申请。")
    } catch (error) {
      setFeedback(error.message || (isEnglish ? "Cancellation failed." : "取消失败。"));
    } finally {
      setBusy("");
    }
  };
  return (
    <Page>
      <PageHeader
        eyebrow={isEnglish ? "PRIVACY / YOUR DATA" : "PRIVACY / 你的数据"}
        title={isEnglish ? "Privacy and data" : "隐私与数据"}
        description={isEnglish ? "Export your account data or submit a deletion request. Deletion is reviewed before fulfillment; financial records may need to be retained." : "可以导出账户数据或提交删除申请。删除须先核对任务、订单与剩余额度；财务记录可能需要保留。"}
      />
      <div className="ops-two-col ops-two-col--wide">
        <Section title={isEnglish ? "Current data path" : "当前数据路径"} kicker="VERIFIABLE FLOW" className="ops-shadow-card">
          <ol className="ops-numbered">
            <li><span>01</span><div><b>{isEnglish ? "Local draft backup" : "浏览器待同步备份"}</b><p>{isEnglish ? "Unsynced text is cached per manuscript in this browser. Saved caches are cleared at sign-out; unsynced copies remain to prevent loss." : "未同步文字按文稿暂存在此浏览器。退出登录时清除已同步缓存；未同步备份保留以防丢稿。"}</p></div></li>
            <li><span>02</span><div><b>{isEnglish ? "Platform server" : "平台服务器"}</b><p>{isEnglish ? "Saved original files, manuscripts, reports, and rewrite results are stored by account in the platform's server database. Encrypted server backups are separate from browser drafts; keep your own copy too." : "已保存的原文件、文稿、报告和改写结果按账户存放在平台服务器数据库中，并定时制作服务器加密备份；重要文稿仍请自行保留副本。"}</p></div></li>
            <li><span>03</span><div><b>{isEnglish ? "Platform-managed LLM" : "平台统一配置的 LLM"}</b><p>{isEnglish ? "When you confirm a model rewrite, the relevant text is sent by the backend to its configured model provider." : "用户确认模型改写后，相关正文由后端发送给已配置的模型服务商。"}</p></div></li>
            <li><span>04</span><div><b>{isEnglish ? "Usage ledger" : "用量账本"}</b><p>{isEnglish ? "Credit and job-usage metadata are recorded for reservation, settlement, and release. Completed task results are retained on the platform server." : "额度与任务用量元数据用于预占、结算和释放；已完成任务结果保存在平台服务器。"}</p></div></li>
          </ol>
        </Section>
        <Section title={isEnglish ? "Your data controls" : "你的数据操作"} kicker="ACCOUNT DATA">
          <div className="ops-note ops-note--yellow"><WarningCircle size={28} weight="fill" /><div><b>{isEnglish ? "Deletion requires review" : "删除申请需核对"}</b><p>{isEnglish ? "A request does not delete data immediately. Running jobs, pending payments and unused paid credits must be settled first. Financial records remain pseudonymous after fulfillment; configurable retention is not available yet." : "提交申请不会立即删除。运行任务、待确认付款和未使用的付费额度须先处理；完成后财务记录会以去身份化账户标识保留。目前尚无自选留存期。"}</p></div></div>
          {isAccountUser ? <>
            <div className="ops-header-actions">
              <Button icon={DownloadSimple} onClick={exportData} disabled={Boolean(busy)}>{busy === "export" ? (isEnglish ? "Preparing…" : "正在导出…") : (isEnglish ? "Download my data" : "下载我的数据")}</Button>
            </div>
            {request?.status === "pending" ? <div className="ops-note ops-note--yellow"><Info size={24} weight="fill" /><div><b>{isEnglish ? "Deletion request pending" : "删除申请待处理"}</b><p>{isEnglish ? `Request ${request.id}. You may cancel it while it is pending.` : `申请编号 ${request.id}。处理前可以取消。`}</p><Button onClick={cancelDeletion} disabled={Boolean(busy)}>{isEnglish ? "Cancel request" : "取消申请"}</Button></div></div> : <div className="ops-form-grid">
              <label><span>{isEnglish ? "Type your account email to request deletion" : "输入当前账户邮箱以申请删除"}</span><input type="email" autoComplete="email" value={confirmedEmail} onChange={(event) => setConfirmedEmail(event.target.value)} placeholder={email} /></label>
              <Button icon={Trash} onClick={requestDeletion} disabled={Boolean(busy) || confirmedEmail.trim() !== email}>{busy === "delete" ? (isEnglish ? "Submitting…" : "正在提交…") : (isEnglish ? "Request account deletion" : "申请删除账户")}</Button>
            </div>}
          </> : <p>{isEnglish ? "Sign in to export account data or request deletion." : "登录后可导出账户数据或申请删除。"}</p>}
          {feedback && <div className="ops-note ops-note--green" role="status"><Info size={24} weight="fill" /><div><p>{feedback}</p></div></div>}
          <div className="ops-header-actions">
            <Button icon={UserCircle} onClick={() => go(navigate, "/app/settings/account")}>{isEnglish ? "Account status" : "账号状态"}</Button>
            <Button icon={Info} onClick={() => go(navigate, "/legal/privacy")}>{isEnglish ? "Read privacy notice" : "查看隐私说明"}</Button>
          </div>
        </Section>
      </div>
    </Page>
  );
}

function LegacyPrivacySettingsPage({ navigate }) {
  const [retention, setRetention] = useState("24h");
  const [productData, setProductData] = useState(false);
  const [diagnostics, setDiagnostics] = useState(true);
  const [exportRequested, setExportRequested] = useState(false);

  return (
    <Page>
      <PageHeader eyebrow="ACCOUNT / 隐私" title="隐私与数据" description="选择正文留存时间，并查看每类数据为什么被处理、何时删除。">
        <Button icon={exportRequested ? Check : DownloadSimple} tone={exportRequested ? "green" : "plain"} onClick={() => setExportRequested(true)}>{exportRequested ? "导出演示已准备" : "导出我的数据"}</Button>
      </PageHeader>
      <DemoFeedback tone="green">{exportRequested ? "已创建本地导出演示状态；没有打包、下载或发送真实数据。" : ""}</DemoFeedback>
      <div className="ops-settings-grid">
        <nav className="ops-settings-nav" aria-label="设置导航">
          <button type="button" onClick={() => go(navigate, "/app/settings/account")}><UserCircle size={19} />账号资料</button>
          <button className="is-active" type="button"><ShieldCheck size={19} />隐私与数据</button>
          <button type="button" onClick={() => go(navigate, "/app/billing")}><Wallet size={19} />额度与订单</button>
        </nav>
        <div className="ops-settings-main">
          <div className="ops-privacy-promise ops-shadow-card">
            <ShieldCheck size={38} weight="fill" />
            <div><p className="ops-eyebrow">PRIVACY BY DEFAULT</p><h2>正文不是运营素材</h2><p>不在操作日志中记录论文全文；用于产品改进的数据默认关闭。</p></div>
          </div>
          <Section title="正文留存" kicker="DOCUMENT RETENTION">
            <div className="ops-choice-list">
              {[
                ["none", "任务完成即删除", "不支持跨设备恢复"],
                ["24h", "保留 24 小时", "推荐 · 便于失败恢复与导出"],
                ["7d", "保留 7 天", "适合多轮修订"],
              ].map(([value, label, note]) => (
                <button type="button" key={value} className={retention === value ? "is-selected" : ""} onClick={() => setRetention(value)}>
                  <span className="ops-radio-dot" />
                  <span><b>{label}</b><small>{note}</small></span>
                </button>
              ))}
            </div>
          </Section>
          <Section title="数据使用开关" kicker="CONSENT">
            <Toggle checked={productData} onChange={setProductData} label="允许使用匿名结构特征改进产品" note="不含正文、姓名、邮箱和引用内容；可随时撤回" />
            <Toggle checked={diagnostics} onChange={setDiagnostics} label="发送错误诊断" note="仅任务号、错误码、耗时和客户端版本" />
          </Section>
          <Section title="处理清单" kicker="DATA INVENTORY" className="ops-shadow-card">
            <Table rows={[
              { id: "account", data: "邮箱、显示名称", purpose: "登录与账号恢复", retention: "账号存在期间", access: "账号服务" },
              { id: "document", data: "用户主动提交的正文", purpose: "分析与改写", retention: retention === "none" ? "任务完成即删除" : retention === "24h" ? "24 小时" : "7 天", access: "处理服务" },
              { id: "payment", data: "订单号、金额、状态", purpose: "付款、退款与对账", retention: "按交易记录要求", access: "账务服务" },
              { id: "logs", data: "任务号、错误码、耗时", purpose: "安全与故障定位", retention: "30 天", access: "运维人员" },
            ]} columns={[
              { key: "data", label: "数据" },
              { key: "purpose", label: "目的" },
              { key: "retention", label: "保留期" },
              { key: "access", label: "最小访问范围" },
            ]} />
          </Section>
          <SafeDeleteFlow kind="documents" />
        </div>
      </div>
    </Page>
  );
}

export function ServiceStatusPage() {
  const { isEnglish, number } = useOpsLocale();
  const { session, config, billing, loading, error, refresh } = usePlatform();
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [checkedAt, setCheckedAt] = useState(null);

  const loadStatus = useCallback(async () => {
    setRefreshing(true);
    setHealthError("");
    const [healthResult] = await Promise.allSettled([getApi("/health"), refresh()]);
    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      setHealth(null);
      setHealthError(healthResult.reason?.message || (isEnglish ? "Health check failed" : "健康检查失败"));
    }
    setCheckedAt(new Date());
    setRefreshing(false);
  }, [isEnglish, refresh]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const healthOk = health?.ok === true;
  const checks = config?.checks && typeof config.checks === "object" ? config.checks : {};
  const checkEvidence = Object.entries(checks).map(([language, count]) => `${language.toUpperCase()} ${count}`).join(" · ") || "—";
  const payment = config?.payment || billing?.payment || {};
  const checkoutEnabled = payment.provider === "stripe" && payment.checkout_enabled === true;
  const components = [
    {
      id: "gateway",
      name: "网页与 API 服务",
      scope: config?.local_mode ? "本地同源服务" : "平台服务",
      evidence: healthOk ? `GET /health · ok=true${config?.product_version ? ` · ${config.product_version}` : ""}` : (healthError || "等待 /health"),
      status: healthOk ? "healthy" : "degraded",
      label: health === null && !healthError ? "检查中" : undefined,
    },
    {
      id: "analysis",
      name: "分析规则引擎",
      scope: config?.policy || "—",
      evidence: config ? `${checkEvidence} · ${(config.supported_languages || []).join(" / ") || "—"}` : "等待 /api/config",
      status: healthOk && config ? "healthy" : "degraded",
    },
    {
      id: "rewrite",
      name: "模型改写服务",
      scope: config?.llm_model || "—",
      evidence: config?.llm_configured ? "llm_configured=true" : "llm_configured=false",
      status: config?.llm_configured ? "healthy" : "closed",
      label: config?.llm_configured ? undefined : "未配置",
    },
    {
      id: "billing",
      name: "额度账本",
      scope: billing?.plan_name || billing?.plan_id || "—",
      evidence: billing ? `${number(billing.balance)} 字 · ${billing.account_id || "—"}` : "等待 /api/billing/summary",
      status: billing ? "healthy" : "degraded",
    },
    {
      id: "payments",
      name: isEnglish ? "Orders and payment" : "订单与支付",
      scope: payment.display_name || payment.provider || "—",
      evidence: payment.notice || (isEnglish ? "Waiting for payment configuration" : "等待支付配置"),
      status: checkoutEnabled ? (payment.live ? "healthy" : "degraded") : "closed",
      label: checkoutEnabled
        ? (payment.live ? (isEnglish ? "Live checkout" : "正式收款")
          : (isEnglish ? "Test checkout" : "测试收银台"))
        : (isEnglish ? "Unavailable" : "未接入"),
    },
    {
      id: "admin",
      name: isEnglish ? "Administrator review" : "管理员核对",
      scope: config?.admin_read_only_configured
        ? (isEnglish ? "Authorized read-only access" : "授权只读访问")
        : (isEnglish ? "No administrator configured" : "未配置管理员"),
      evidence: config?.admin_read_only_configured
        ? (isEnglish ? "Orders and deletion requests are available to authorized admins; write actions remain restricted." : "授权管理员可核对订单和删除申请；写操作仍受限。")
        : (isEnglish ? "Set ADMIN_EMAILS privately on the server to enable review access." : "需在服务器私有配置中设置 ADMIN_EMAILS。"),
      status: config?.admin_read_only_configured ? "degraded" : "closed",
      label: config?.admin_read_only_configured
        ? (isEnglish ? "Read only" : "只读")
        : (isEnglish ? "Unavailable" : "未接入"),
    },
  ];
  const coreReady = healthOk && Boolean(config) && Boolean(billing);

  return (
    <Page>
      <PageHeader eyebrow="SERVICE / 运行状态" title="平台运行状态" description="仅展示当前后端实际返回的健康、配置与账本证据。">
        <Button icon={ArrowsClockwise} onClick={loadStatus} disabled={refreshing}>{refreshing ? "刷新中" : "刷新状态"}</Button>
      </PageHeader>
      {(error || healthError) && <div className="ops-inline-notice"><WarningCircle size={18} weight="fill" /><span>{[error, healthError].filter(Boolean).join(" · ")}</span></div>}
      <div className={`ops-service-banner ${coreReady ? "ops-service-banner--good" : ""} ops-shadow-card`}>
        {coreReady ? <CheckCircle size={38} weight="fill" /> : <WarningCircle size={38} weight="fill" />}
        <div>
          <p className="ops-eyebrow">CURRENT STATUS</p>
          <h2>{coreReady ? "已连接核心后端" : loading || refreshing ? "正在核对后端" : "部分后端状态不可用"}</h2>
          <p>{coreReady ? "健康检查、平台配置与额度账本均已返回。" : "请以组件表中的实际响应为准。"}</p>
        </div>
        <time>{checkedAt ? `${isEnglish ? "Checked" : "核对于"} ${new Intl.DateTimeFormat(isEnglish ? "en" : "zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(checkedAt)}` : "—"}</time>
      </div>
      <div className="ops-inline-notice"><Info size={18} weight="fill" /><span>{checkoutEnabled
        ? (isEnglish ? "Checkout availability comes from the server. Confirm a charge only from its Stripe order and verified webhook, not from this health table."
          : "收银台可用状态来自服务端；真实扣款与额度发放仍以 Stripe 订单和已核验的 Webhook 为准。")
          : (isEnglish ? "Unavailable services show no simulated data; payment and administrator write actions remain disabled."
          : "未接入项不显示模拟数据；支付与管理员写操作均明确停用。")}</span></div>
      <Section title="服务组件" kicker="LIVE BACKEND EVIDENCE" className="ops-shadow-card">
        <Table rows={components} columns={[
          { key: "name", label: "组件", render: (row) => <b>{row.name}</b> },
          { key: "scope", label: "范围 / 配置" },
          { key: "evidence", label: "当前后端证据" },
          { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} label={row.label} /> },
        ]} />
      </Section>
      <div className="ops-two-col">
        <Section title="当前可核对能力" kicker="AVAILABLE NOW">
          <ul className="ops-audit-list">
            <li><CheckCircle size={18} weight="fill" /><span><b>健康检查</b>读取 /health 的 ok 字段</span></li>
            <li><CheckCircle size={18} weight="fill" /><span><b>分析配置</b>{checkEvidence} · {config?.calibrated ? "已校准" : "未标记校准"}</span></li>
            <li><CheckCircle size={18} weight="fill" /><span><b>会话模式</b>{session?.trialMode ? "试用模式" : "正式会话模式"}</span></li>
          </ul>
        </Section>
        <Section title="尚无后端数据" kicker="NOT CONNECTED">
          <div className="ops-note ops-note--yellow"><WarningCircle size={28} weight="fill" /><div><b>未接入遥测与控制面</b><p>后端没有 30 日 SLA、实时延迟、队列长度、事件历史或管理员写操作接口，因此本页不展示这些指标。</p></div></div>
        </Section>
      </div>
    </Page>
  );
}

function LegacyServiceStatusPage({ navigate }) {
  const [refreshing, setRefreshing] = useState(false);
  const components = [
    { id: "gateway", name: "网页与 API 网关", region: "华东", latency: "42 ms", availability: "99.99%", status: "healthy" },
    { id: "analysis", name: "本地分析引擎", region: "主集群", latency: "118 ms", availability: "99.98%", status: "healthy" },
    { id: "jobs", name: "保真改写队列", region: "主集群", latency: "等待 18 s", availability: "99.91%", status: "degraded" },
    { id: "billing", name: "额度账本", region: "主库", latency: "21 ms", availability: "100%", status: "healthy" },
    { id: "payments", name: "支付确认（演示）", region: "未接入", latency: "—", availability: "—", status: "degraded" },
  ];
  return (
    <Page>
      <PageHeader eyebrow="SERVICE / 运行状态" title="核心处理服务可核对" description="这里只展示服务健康与事件进展；支付与经济系统尚未接入，相关内容均为本地演示。">
        <Button icon={ArrowsClockwise} onClick={() => { setRefreshing(true); window.setTimeout(() => setRefreshing(false), 500); }}>{refreshing ? "刷新中" : "刷新状态"}</Button>
      </PageHeader>
      <div className="ops-service-banner ops-service-banner--good ops-shadow-card">
        <CheckCircle size={38} weight="fill" />
        <div><p className="ops-eyebrow">CURRENT STATUS</p><h2>核心处理服务正常</h2><p>改写队列等待时间略高；支付渠道未接入，收银台与订单均为演示数据。</p></div>
        <time>更新于 15:38</time>
      </div>
      <div className="ops-inline-notice"><Info size={18} weight="fill" /><span><b>支付未接入</b>：微信支付、支付宝、退款与对账目前只演示界面状态，不会发起真实扣款或权益变更。</span></div>
      <Section title="服务组件" kicker="LIVE COMPONENTS" className="ops-shadow-card">
        <Table rows={components} columns={[
          { key: "name", label: "组件", render: (row) => <b>{row.name}</b> },
          { key: "region", label: "范围" },
          { key: "latency", label: "当前延迟" },
          { key: "availability", label: "30 日可用性" },
          { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} /> },
        ]} />
      </Section>
      <div className="ops-two-col">
        <Section title="进行中的事件" kicker="ACTIVE INCIDENT">
          <div className="ops-incident">
            <div className="ops-incident-time">14:52</div>
            <div><StatusPill status="degraded" /><h3>部分深度改写任务排队时间增加</h3><p>已扩容任务消费者；预占额度保持锁定，超时任务会自动释放。</p><small>下一次更新：16:10 前</small></div>
          </div>
        </Section>
        <Section title="最近 30 天" kicker="RELIABILITY">
          <div className="ops-bar-list">
            <div><span>成功完成任务</span><b>99.3%</b><Progress value={99.3} max={100} tone="green" /></div>
            <div><span>支付演示流程覆盖</span><b>100%</b><Progress value={100} max={100} tone="blue" /></div>
            <div><span>额度账本一致性</span><b>100%</b><Progress value={100} max={100} tone="green" /></div>
          </div>
        </Section>
      </div>
    </Page>
  );
}

const adminUsers = [
  { id: "U-10931", identity: "w***@mail.com", plan: "轻量月卡 + 章节包", credits: 56420, jobs: 23, last: "3 分钟前", risk: "healthy" },
  { id: "U-10922", identity: "l***@edu.cn", plan: "专业月卡", credits: 174220, jobs: 41, last: "18 分钟前", risk: "healthy" },
  { id: "U-10807", identity: "m***@mail.com", plan: "论文包", credits: 12340, jobs: 9, last: "2 小时前", risk: "review" },
  { id: "U-10712", identity: "q***@mail.com", plan: "无有效权益", credits: 0, jobs: 2, last: "19 天前", risk: "closed" },
];

const adminJobs = [
  { id: "J-26A88", user: "U-10931", mode: "平衡", chars: 2460, reserved: 2460, cost: 0.87, duration: "01:12", status: "running", trace: "TR-91A8" },
  { id: "J-26A91", user: "U-10931", mode: "深度", chars: 4812, reserved: 7218, cost: 3.62, duration: "02:48", status: "completed", trace: "TR-91B1" },
  { id: "J-269F2", user: "U-10807", mode: "平衡", chars: 3150, reserved: 0, cost: 0.42, duration: "05:00", status: "failed", trace: "TR-902F" },
  { id: "J-268C4", user: "U-10922", mode: "保守", chars: 8400, reserved: 8400, cost: 2.14, duration: "—", status: "queued", trace: "TR-8FF2" },
];

const adminOrders = orderRows.map((row, index) => ({ ...row, user: adminUsers[index % adminUsers.length].id, providerId: `P-${row.id.slice(-4)}•••`, entitlement: row.status === "paid" ? "issued" : row.status === "refunded" ? "reversed" : "none" }));

function AdminHeader({ title, description, children }) {
  return <PageHeader eyebrow="ADMIN / CONTROL PLANE" title={title} description={description}>{children}</PageHeader>;
}

function AdminTabs({ navigate, active }) {
  const { isEnglish } = useLocale();
  const items = [
    ["overview", "总览", "/admin"], ["users", "用户", "/admin/users"], ["jobs", "任务", "/admin/jobs"],
    ["plans", "方案", "/admin/plans"], ["orders", "订单", "/admin/orders"], ["economics", "成本", "/admin/economics"],
    ["service", "服务", "/admin/service"], ["privacy", "隐私", "/admin/privacy"],
  ];
  return <div className="ops-admin-tabs">{items.map(([value, label, path]) => <button key={value} className={active === value ? "is-active" : ""} type="button" onClick={() => go(navigate, path)}>{translateText(label, isEnglish)}</button>)}</div>;
}

function AdminUnavailablePage({ navigate, active, title, description }) {
  return (
    <Page>
      <AdminHeader title={title} description={description} />
      <AdminTabs navigate={navigate} active={active} />
      <Section title="管理员能力未接入" kicker="NOT CONNECTED" className="ops-shadow-card">
        <div className="ops-note ops-note--yellow">
          <ShieldWarning size={28} weight="fill" />
          <div><b>没有管理员 API 或授权控制面</b><p>本页不展示模拟指标，也不提供刷新、开关、编辑、导出、对账或隐私处置等假动作。</p></div>
        </div>
      </Section>
    </Page>
  );
}

export function AdminOverviewPage({ navigate }) {
  const { isEnglish } = useLocale();
  const [orders, setOrders] = useState([]);
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([getApi("/api/admin/orders"), getApi("/api/admin/privacy-requests")])
      .then(([orderData, requestData]) => {
        setOrders(orderData.orders || []);
        setRequests(requestData.requests || []);
      })
      .catch((failure) => setError(failure.message || (isEnglish ? "Admin data unavailable." : "无法读取运营数据。")));
  }, [isEnglish]);
  return <Page>
    <PageHeader eyebrow="ADMIN / LIVE" title={isEnglish ? "Operations overview" : "运营总览"} description={isEnglish ? "Read-only order and privacy-request evidence from the server." : "展示服务端真实订单与隐私申请，只读核对。"} />
    {error && <div className="ops-note ops-note--yellow" role="alert"><WarningCircle size={24} weight="fill" /><div><p>{error}</p></div></div>}
    {!error && <div className="ops-two-col">
      <Section title={isEnglish ? "Recent orders" : "最近订单"} kicker="BILLING"><h2>{orders.length}</h2><Button onClick={() => navigate("/admin/orders")}>{isEnglish ? "Review orders" : "核对订单"}</Button></Section>
      <Section title={isEnglish ? "Deletion requests pending" : "待处理删除申请"} kicker="PRIVACY"><h2>{requests.length}</h2><Button onClick={() => navigate("/admin/privacy")}>{isEnglish ? "Review requests" : "查看申请"}</Button></Section>
    </div>}
  </Page>;
}

export function AdminUsersPage({ navigate }) {
  return <AdminLiveList navigate={navigate} active="users" endpoint="/api/admin/users" field="users" title="用户与权益" description="最近 100 位账户的身份与额度摘要；不展示论文内容，不提供直接改额度操作。" columns={[
    { key: "primary_email", label: "邮箱" },
    { key: "display_name", label: "名称" },
    { key: "balance", label: "可用字数" },
    { key: "manuscript_count", label: "文稿数" },
    { key: "created_at", label: "注册时间", render: (row) => new Date(row.created_at * 1000).toLocaleString() },
  ]} />;
}

export function AdminJobsPage({ navigate }) {
  return <AdminLiveList navigate={navigate} active="jobs" endpoint="/api/admin/jobs" field="jobs" title="改写任务" description="最近 100 个真实任务的状态及 Token 用量；正文和改写结果不会在管理台展示。" columns={[
    { key: "id", label: "任务号" },
    { key: "state", label: "状态" },
    { key: "phase", label: "阶段" },
    { key: "billable_chars", label: "计费字数" },
    { key: "input_tokens", label: "输入 Token" },
    { key: "output_tokens", label: "输出 Token" },
    { key: "t0", label: "开始时间", render: (row) => new Date(row.t0 * 1000).toLocaleString() },
  ]} />;
}

export function AdminPlansPage({ navigate }) {
  return <AdminLiveList navigate={navigate} active="plans" endpoint="/api/admin/plans" field="plans" title="套餐目录" description="查看当前实际生效的服务端套餐。价格修改仍需代码审查和发布，避免在管理台误改真实收款。" columns={[
    { key: "id", label: "套餐 ID" },
    { key: "name", label: "名称" },
    { key: "price_fen", label: "价格", render: (row) => `${(row.price_fen / 100).toFixed(2)} ${row.currency}` },
    { key: "credits", label: "额度" },
    { key: "valid_days", label: "有效天数" },
  ]} />;
}

function AdminLiveList({ navigate, active, endpoint, field, title, description, columns }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setRows((await getApi(endpoint))[field] || []); }
    catch (failure) { setError(failure.message || "无法读取运营数据。"); }
    finally { setLoading(false); }
  }, [endpoint, field]);
  useEffect(() => { void refresh(); }, [refresh]);
  return <Page>
    <AdminHeader title={title} description={description}><Button icon={ArrowsClockwise} onClick={refresh} disabled={loading}>{loading ? "正在读取…" : "刷新"}</Button></AdminHeader>
    <AdminTabs navigate={navigate} active={active} />
    {error ? <div className="ops-note ops-note--yellow" role="alert">{error}</div> : <Section title={title} kicker="LIVE / READ ONLY" className="ops-shadow-card"><Table rows={rows} columns={columns} empty="暂无记录" /></Section>}
  </Page>;
}

export function AdminOrdersPage({ navigate }) {
  const { isEnglish } = useLocale();
  const [orders, setOrders] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getApi("/api/admin/orders");
      setOrders(result.orders || []);
    } catch (failure) {
      setError(failure.message || (isEnglish ? "Could not load orders." : "无法读取订单。"));
    } finally {
      setLoading(false);
    }
  }, [isEnglish]);
  useEffect(() => { void refresh(); }, [refresh]);
  return <Page>
    <PageHeader eyebrow="ADMIN / BILLING" title={isEnglish ? "Orders and local ledger" : "订单与本地账本"} description={isEnglish ? "Read-only local order and webhook records. A match here does not prove Stripe has no undelivered events; check Stripe for final settlement." : "只读查看本地订单与回调记录。本地一致不代表 Stripe 没有未送达事件；最终结算仍需到 Stripe 核对。"}>
      <Button icon={ArrowsClockwise} onClick={refresh} disabled={loading}>{loading ? (isEnglish ? "Loading…" : "正在读取…") : (isEnglish ? "Refresh" : "刷新")}</Button>
    </PageHeader>
    {error && <div className="ops-note ops-note--yellow" role="alert"><WarningCircle size={24} weight="fill" /><div><p>{error}</p></div></div>}
    {!error && <Section title={isEnglish ? "Latest 100 orders" : "最近 100 笔订单"} kicker="LIVE LEDGER" className="ops-shadow-card">
      <Table rows={orders.map((order) => ({ ...order, id: order.order_id }))} empty={isEnglish ? "No orders" : "暂无订单"} columns={[
        { key: "order_id", label: isEnglish ? "Order" : "订单号" },
        { key: "account_email", label: isEnglish ? "Account" : "账户", render: (row) => row.account_email || row.account_id },
        { key: "product_id", label: isEnglish ? "Plan" : "套餐" },
        { key: "amount_fen", label: isEnglish ? "Amount" : "金额", render: (row) => `${(row.amount_fen / 100).toFixed(2)} ${row.currency}` },
        { key: "status", label: isEnglish ? "Status" : "状态", render: (row) => <StatusPill status={row.status} /> },
        { key: "refunded_fen", label: isEnglish ? "Refunded" : "累计退款", render: (row) => `${(row.refunded_fen / 100).toFixed(2)} ${row.currency}` },
        { key: "reconciliation_required", label: isEnglish ? "Local check" : "本地核对", render: (row) => row.reconciliation_required ? (isEnglish ? "Review" : "需复核") : (isEnglish ? "Locally consistent" : "本地一致") },
      ]} />
    </Section>}
  </Page>;
}

export function AdminEconomicsPage({ navigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getApi("/api/admin/economics").then(setData).catch((failure) => setError(failure.message)); }, []);
  return <Page><AdminHeader title="收款与模型用量" description="展示真实已支付订单净额与已结算任务 Token。模型单价和 Stripe 手续费尚未接入，不能据此计算毛利。" /><AdminTabs navigate={navigate} active="economics" />
    {error && <div className="ops-note ops-note--yellow" role="alert">{error}</div>}
    {data && <div className="ops-metrics ops-metrics--3"><Metric label="订单净额（未扣费）" value={`${(data.net_sales_fen / 100).toFixed(2)} ${data.currency}`} /><Metric label="已结算改写任务" value={String(data.settled_jobs)} /><Metric label="模型 Token" value={`${Number(data.input_tokens).toLocaleString()} 入 / ${Number(data.output_tokens).toLocaleString()} 出`} /></div>}
  </Page>;
}

export function AdminServicePage({ navigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getApi("/api/admin/service").then(setData).catch((failure) => setError(failure.message)); }, []);
  return <Page><AdminHeader title="服务状态" description="只读查看当前任务和待付款订单；停服、容量和部署操作仍由服务器受控执行。" /><AdminTabs navigate={navigate} active="service" />
    {error && <div className="ops-note ops-note--yellow" role="alert">{error}</div>}
    {data && <div className="ops-metrics ops-metrics--3"><Metric label="运行中任务" value={String(data.jobs_by_state.running || 0)} /><Metric label="失败任务" value={String(data.jobs_by_state.error || 0)} /><Metric label="待确认订单" value={String(data.pending_orders)} /></div>}
  </Page>;
}

export function AdminPrivacyPage({ navigate }) {
  const { isEnglish } = useLocale();
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getApi("/api/admin/privacy-requests");
      setRequests(result.requests || []);
    } catch (failure) {
      setError(failure.message || (isEnglish ? "Could not load requests." : "无法读取申请。"));
    } finally {
      setLoading(false);
    }
  }, [isEnglish]);
  useEffect(() => { void refresh(); }, [refresh]);
  return <Page>
    <PageHeader eyebrow="ADMIN / PRIVACY" title={isEnglish ? "Privacy requests" : "隐私申请"} description={isEnglish ? "Pending requests are fulfilled only after a verified backup and a review of outstanding paid entitlements." : "仅在备份恢复校验、任务与付费权益核对完成后处理删除申请。"}>
      <Button icon={ArrowsClockwise} onClick={refresh} disabled={loading}>{loading ? (isEnglish ? "Loading…" : "正在读取…") : (isEnglish ? "Refresh" : "刷新")}</Button>
    </PageHeader>
    {error && <div className="ops-note ops-note--yellow" role="alert"><WarningCircle size={24} weight="fill" /><div><p>{error}</p></div></div>}
    {!error && <Section title={isEnglish ? "Pending requests" : "待处理申请"} kicker="LIVE REQUESTS" className="ops-shadow-card"><Table rows={requests} empty={isEnglish ? "No pending requests" : "暂无待处理申请"} columns={[
      { key: "id", label: isEnglish ? "Request" : "申请号" },
      { key: "email", label: isEnglish ? "Email" : "邮箱" },
      { key: "kind", label: isEnglish ? "Type" : "类型" },
      { key: "created_at", label: isEnglish ? "Submitted" : "提交时间", render: (row) => new Date(row.created_at * 1000).toLocaleString(isEnglish ? "en" : "zh-CN") },
    ]} /></Section>}
  </Page>;
}

function LegacyAdminOverviewPage({ navigate }) {
  const { number, money, t } = useOpsLocale();
  const [refreshState, setRefreshState] = useState("idle");
  const refreshed = refreshState === "complete";
  return (
    <Page>
      <AdminHeader title="运营总览" description="任务、额度与隐私请求使用可追溯事件口径；订单金额为本地演示数据。">
        <Button icon={refreshed ? Check : ArrowsClockwise} tone={refreshed ? "green" : "plain"} onClick={() => setRefreshState("complete")}>{refreshed ? "已刷新（演示）" : "刷新数据"}</Button>
      </AdminHeader>
      <AdminTabs navigate={navigate} active="overview" />
      <DemoFeedback tone="green">{refreshed ? t("运营数据已在本地重新载入；没有请求真实管理端接口。", "Operations data was reloaded locally; no real admin API was called.") : ""}</DemoFeedback>
      <div className="ops-metrics ops-metrics--4">
        <Metric label="今日有效任务" value="1,284" note="成功率 98.7%" tone="yellow" icon={ListChecks} />
        <Metric label="待处理队列" value="37" note="P95 等待 28 秒" tone="blue" icon={Clock} />
        <Metric label="今日演示订单金额" value="¥8,431" note="退款演示 ¥192" tone="green" icon={Coins} />
        <Metric label="需人工复核" value="6" note="支付 2 · 隐私 1 · 任务 3" tone="orange" icon={ShieldWarning} />
      </div>
      <div className="ops-two-col ops-two-col--wide">
        <Section title="运营检查" kicker="CONTROL CHECKS" className="ops-shadow-card">
          <div className="ops-check-rows">
            {[
              ["额度账本与任务结算", "10 分钟前核对", "healthy"],
              ["支付演示与本地订单", "未连接真实支付渠道", "degraded"],
              ["退款与权益冲正", "全部一致", "healthy"],
              ["文档删除计划", "1 个请求待执行", "review"],
            ].map(([label, note, status]) => <div key={label}><StatusPill status={status} /><span><b>{label}</b><small>{note}</small></span><ArrowRight size={18} /></div>)}
          </div>
        </Section>
        <Section title="最近 7 日" kicker="UNIT ECONOMICS">
          <div className="ops-economics-hero"><span>贡献毛利率</span><strong>68.4%</strong><small>内测观测值 · 不含固定研发成本</small></div>
          <div className="ops-bar-list">
            <div><span>模型与计算</span><b>¥4,802</b><Progress value={57} max={100} tone="blue" /></div>
            <div><span>支付与退款</span><b>¥612</b><Progress value={18} max={100} tone="yellow" /></div>
            <div><span>毛利贡献</span><b>¥11,711</b><Progress value={68} max={100} tone="green" /></div>
          </div>
        </Section>
      </div>
      <Section title="实时任务抽样" kicker="NO DOCUMENT CONTENT" className="ops-shadow-card">
        <Table rows={adminJobs.slice(0, 3)} columns={[
          { key: "id", label: "任务号", render: (row) => <code>{row.id}</code> },
          { key: "user", label: "用户" },
          { key: "mode", label: "模式" },
          { key: "chars", label: "计费字符", render: (row) => `${number(row.chars)} 字` },
          { key: "cost", label: "估算成本", render: (row) => money(row.cost) },
          { key: "trace", label: "追踪号", render: (row) => <code>{row.trace}</code> },
          { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} /> },
        ]} />
        <div className="ops-footnote"><LockKey size={16} /> 管理台只显示任务元数据、计量与结果状态，不展示论文全文或改写正文。</div>
      </Section>
    </Page>
  );
}

function LegacyAdminUsersPage({ navigate }) {
  const { number, t } = useOpsLocale();
  const [query, setQuery] = useState("");
  const [view, setView] = useState("all");
  const [feedbackEvent, setFeedbackEvent] = useState(null);
  const feedback = feedbackEvent?.type === "adjustment"
    ? t("客服调整草稿已在本地创建；没有改动任何用户权益。", "A support-adjustment draft was created locally; no user entitlement changed.")
    : feedbackEvent?.type === "ledger"
      ? t(`已打开 ${feedbackEvent.userId} 的本地账本预览；没有读取真实用户数据。`, `Opened the local ledger preview for ${feedbackEvent.userId}; no real user data was read.`)
      : "";
  const rows = adminUsers.filter((row) => (view === "all" || row.risk === view) && `${row.id}${row.identity}${row.plan}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <Page>
      <AdminHeader title="用户与权益" description="仅展示运营必需的脱敏身份、权益与风险信号。"><Button tone="blue" icon={Plus} onClick={() => setFeedbackEvent({ type: "adjustment" })}>创建客服调整</Button></AdminHeader>
      <AdminTabs navigate={navigate} active="users" />
      <DemoFeedback>{feedback}</DemoFeedback>
      <Section title="用户列表" kicker="MINIMIZED IDENTITY" className="ops-shadow-card">
        <FilterBar query={query} onQuery={setQuery} placeholder="搜索用户 ID 或脱敏邮箱">
          <Tabs value={view} onChange={setView} items={[{ value: "all", label: "全部", count: adminUsers.length }, { value: "healthy", label: "正常" }, { value: "review", label: "待复核" }, { value: "closed", label: "停用" }]} />
        </FilterBar>
        <Table rows={rows} columns={[
          { key: "id", label: "用户 ID", render: (row) => <code>{row.id}</code> },
          { key: "identity", label: "脱敏身份" },
          { key: "plan", label: "有效权益", render: (row) => <b>{row.plan}</b> },
          { key: "credits", label: "可用额度", render: (row) => `${number(row.credits)} 字` },
          { key: "jobs", label: "任务数" },
          { key: "last", label: "最后活跃" },
          { key: "risk", label: "账号状态", render: (row) => <StatusPill status={row.risk} label={row.risk === "healthy" ? "正常" : undefined} /> },
          { key: "action", label: "操作", render: (row) => <button className="ops-text-button" type="button" onClick={() => setFeedbackEvent({ type: "ledger", userId: row.id })}>查看账本 <ArrowRight size={14} /></button> },
        ]} />
      </Section>
    </Page>
  );
}

function LegacyAdminJobsPage({ navigate }) {
  const { number, money, t } = useOpsLocale();
  const [view, setView] = useState("all");
  const [query, setQuery] = useState("");
  const [paused, setPaused] = useState(false);
  const [lastQueueAction, setLastQueueAction] = useState(null);
  const actionFeedback = lastQueueAction === "paused"
    ? t("已在本地演示中标记“暂停新任务”；真实队列未受影响。", "New jobs are marked paused in the local demo; the real queue is unaffected.")
    : lastQueueAction === "resumed"
      ? t("已在本地演示中恢复新任务；真实队列未受影响。", "New jobs are resumed in the local demo; the real queue is unaffected.")
      : "";
  const rows = adminJobs.filter((row) => (view === "all" || row.status === view) && `${row.id}${row.user}${row.trace}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <Page>
      <AdminHeader title="任务队列" description="查看任务状态、预占额度与成本；正文内容不会进入运营日志。"><Button icon={paused ? Play : Pause} tone={paused ? "green" : "plain"} onClick={() => { const next = !paused; setPaused(next); setLastQueueAction(next ? "paused" : "resumed"); }}>{paused ? "恢复新任务（演示）" : "暂停新任务"}</Button></AdminHeader>
      <AdminTabs navigate={navigate} active="jobs" />
      <DemoFeedback>{actionFeedback}</DemoFeedback>
      <div className="ops-metrics ops-metrics--3">
        <Metric label="运行中" value="12" note="并发上限 20" tone="blue" icon={Play} />
        <Metric label="排队" value="37" note="最老任务 41 秒" tone="yellow" icon={Clock} />
        <Metric label="今日失败" value="17" note="1.3% · 超时为主" tone="orange" icon={WarningCircle} />
      </div>
      <Section title="任务记录" kicker="METADATA ONLY" className="ops-shadow-card">
        <FilterBar query={query} onQuery={setQuery} placeholder="搜索任务、用户或追踪号">
          <Tabs value={view} onChange={setView} items={[{ value: "all", label: "全部" }, { value: "running", label: "运行中" }, { value: "queued", label: "排队" }, { value: "completed", label: "完成" }, { value: "failed", label: "失败" }]} />
        </FilterBar>
        <Table rows={rows} columns={[
          { key: "id", label: "任务号", render: (row) => <code>{row.id}</code> },
          { key: "user", label: "用户" },
          { key: "mode", label: "模式" },
          { key: "chars", label: "输入字符", render: (row) => `${number(row.chars)} 字` },
          { key: "reserved", label: "额度预占", render: (row) => `${number(row.reserved)} 字` },
          { key: "cost", label: "成本", render: (row) => money(row.cost) },
          { key: "duration", label: "耗时" },
          { key: "trace", label: "追踪号", render: (row) => <code>{row.trace}</code> },
          { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} /> },
        ]} />
      </Section>
    </Page>
  );
}

function LegacyAdminPlansPage({ navigate }) {
  const { number, money, t } = useOpsLocale();
  const [kind, setKind] = useState("monthly");
  const [enabled, setEnabled] = useState({ "month-lite": true, "month-pro": true, "pack-20k": true, "pack-60k": true, "pack-200k": true });
  const [feedbackEvent, setFeedbackEvent] = useState(null);
  const feedbackPlan = feedbackEvent?.planId ? allPlans.find((plan) => plan.id === feedbackEvent.planId) : null;
  const actionFeedback = feedbackEvent?.type === "draft"
    ? t("空白方案草稿已在本地创建；没有写入后台配置。", "A blank plan draft was created locally; no backend configuration was written.")
    : feedbackEvent?.type === "availability" && feedbackPlan
      ? t(`${feedbackPlan.name}已在本地标记为${feedbackEvent.enabled ? "上架" : "下架"}；真实方案未变更。`, `${translateText(feedbackPlan.name, true)} was marked ${feedbackEvent.enabled ? "available" : "unavailable"} locally; the real plan was unchanged.`)
      : feedbackEvent?.type === "copy" && feedbackPlan
        ? t(`${feedbackPlan.name}已复制为本地演示草稿；未写入后台。`, `${translateText(feedbackPlan.name, true)} was copied into a local demo draft; nothing was written to the backend.`)
        : "";
  return (
    <Page>
      <AdminHeader title="方案与额度" description="方案是可版本化配置；已成交订单继续使用购买时的产品快照。"><Button tone="blue" icon={Plus} onClick={() => setFeedbackEvent({ type: "draft" })}>新建草稿</Button></AdminHeader>
      <AdminTabs navigate={navigate} active="plans" />
      <DemoFeedback>{actionFeedback}</DemoFeedback>
      <div className="ops-inline-notice"><Info size={18} weight="fill" /><span>以下均为<b>内测参考方案</b>。改价需创建新版本，不覆盖历史订单、额度桶或退款依据。</span></div>
      <Tabs value={kind} onChange={setKind} items={[{ value: "monthly", label: "月卡", count: plans.monthly.length }, { value: "packs", label: "独立字数包", count: plans.packs.length }]} />
      <Section title={kind === "monthly" ? "30 天月卡" : "字数包"} kicker="VERSION 2026.10-BETA" className="ops-shadow-card">
        <Table rows={plans[kind]} columns={[
          { key: "id", label: "产品 ID", render: (row) => <code>{row.id}</code> },
          { key: "name", label: "展示名", render: (row) => <b>{row.name}</b> },
          { key: "price", label: "价格", render: (row) => money(row.price) },
          { key: "credits", label: "额度", render: (row) => `${number(row.credits)} 字` },
          { key: "meta", label: "有效期" },
          { key: "status", label: "上架", render: (row) => <button className={`ops-mini-switch ${enabled[row.id] ? "is-on" : ""}`} type="button" role="switch" aria-checked={enabled[row.id]} aria-label={`${row.name}上架状态`} onClick={() => { const next = !enabled[row.id]; setEnabled((prev) => ({ ...prev, [row.id]: next })); setFeedbackEvent({ type: "availability", planId: row.id, enabled: next }); }}><i /></button> },
          { key: "action", label: "操作", render: (row) => <button className="ops-text-button" type="button" onClick={() => setFeedbackEvent({ type: "copy", planId: row.id })}>复制为草稿 <Copy size={14} /></button> },
        ]} />
      </Section>
      <Section title="统一消耗规则" kicker="ENTITLEMENT POLICY">
        <div className="ops-policy-grid">
          <div><span>01</span><b>允许叠加</b><p>月卡与任意独立字数包同时有效。</p></div>
          <div><span>02</span><b>按到期日排序</b><p>最早到期额度先消耗；同日按发放时间。</p></div>
          <div><span>03</span><b>任务级幂等</b><p>一个任务只允许一次结算或一次全额释放。</p></div>
        </div>
      </Section>
    </Page>
  );
}

function LegacyAdminOrdersPage({ navigate }) {
  const { money, t } = useOpsLocale();
  const [view, setView] = useState("all");
  const [query, setQuery] = useState("");
  const [reconciliationState, setReconciliationState] = useState("idle");
  const reconciled = reconciliationState === "complete";
  const rows = adminOrders.filter((row) => (view === "all" || row.status === view || row.reconciliation === view) && `${row.id}${row.user}${row.providerId}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <Page>
      <AdminHeader title="订单与对账" description="当前为未接入渠道的演示数据；支付、对账与权益状态仍保持独立。"><Button icon={reconciled ? Check : ArrowsClockwise} tone={reconciled ? "green" : "plain"} onClick={() => setReconciliationState("complete")}>{reconciled ? "演示对账完成" : "演示对账"}</Button></AdminHeader>
      <AdminTabs navigate={navigate} active="orders" />
      <DemoFeedback tone="green">{reconciled ? t("本地演示对账已完成：5 条样例记录已核对，没有连接支付渠道。", "Local demo reconciliation completed: 5 sample records checked with no payment provider connection.") : ""}</DemoFeedback>
      <div className="ops-metrics ops-metrics--4">
        <Metric label="今日演示订单" value="183 笔" note="演示金额 ¥8,431" tone="yellow" icon={Receipt} />
        <Metric label="确认中" value="2 笔" note="最长 6 分钟" tone="blue" icon={Clock} />
        <Metric label="退款" value="4 笔" note="金额 ¥192" icon={ArrowsClockwise} />
        <Metric label="对账差异" value="1 笔" note="已阻断发放" tone="orange" icon={ShieldWarning} />
      </div>
      <Section title="支付记录" kicker="RECONCILIATION" className="ops-shadow-card">
        <FilterBar query={query} onQuery={setQuery} placeholder="搜索订单、用户或渠道单号">
          <Tabs value={view} onChange={setView} items={[{ value: "all", label: "全部" }, { value: "paid", label: "已支付" }, { value: "pending", label: "确认中" }, { value: "refunded", label: "已退款" }, { value: "mismatch", label: "对账差异" }]} />
        </FilterBar>
        <Table rows={rows} columns={[
          { key: "id", label: "本地订单", render: (row) => <code>{row.id}</code> },
          { key: "providerId", label: "渠道单号", render: (row) => <code>{row.providerId}</code> },
          { key: "user", label: "用户" },
          { key: "product", label: "产品" },
          { key: "amount", label: "金额", render: (row) => <b>{money(row.amount)}</b> },
          { key: "status", label: "付款", render: (row) => <StatusPill status={row.status} /> },
          { key: "reconciliation", label: "对账", render: (row) => <StatusPill status={row.reconciliation} label={row.reconciliation === "pending" ? "待对账" : undefined} /> },
          { key: "entitlement", label: "权益", render: (row) => <span>{row.entitlement === "issued" ? "已发放" : row.entitlement === "reversed" ? "已冲正" : "未发放"}</span> },
        ]} />
      </Section>
    </Page>
  );
}

function LegacyAdminEconomicsPage({ navigate }) {
  const { money } = useOpsLocale();
  const [windowName, setWindowName] = useState("7d");
  const planEconomics = [
    { id: "month-lite", product: "轻量月卡", revenue: 39.9, variable: 11.4, payment: 0.31, refund: 0.8, margin: "68.6%" },
    { id: "month-pro", product: "专业月卡", revenue: 89.9, variable: 27.8, payment: 0.69, refund: 1.6, margin: "66.5%" },
    { id: "pack-20k", product: "章节包", revenue: 19.9, variable: 4.9, payment: 0.16, refund: 0.3, margin: "73.1%" },
    { id: "pack-60k", product: "论文包", revenue: 49.9, variable: 14.6, payment: 0.38, refund: 0.7, margin: "68.6%" },
    { id: "pack-200k", product: "长文包", revenue: 129.9, variable: 44.2, payment: 1.01, refund: 2.1, margin: "63.6%" },
  ];
  return (
    <Page>
      <AdminHeader title="成本与单位经济" description="以下为内测情景模型，不代表真实实收；收入、计算、支付和退款按同一演示链路核对。">
        <Tabs value={windowName} onChange={setWindowName} items={[{ value: "24h", label: "24小时" }, { value: "7d", label: "7天" }, { value: "30d", label: "30天" }]} />
      </AdminHeader>
      <AdminTabs navigate={navigate} active="economics" />
      <div className="ops-metrics ops-metrics--4">
        <Metric label="情景收入" value="¥17,125" note={`${windowName} · 演示估算`} tone="yellow" icon={Coins} />
        <Metric label="变动成本" value="¥4,802" note="每万结算字 ¥4.11" tone="blue" icon={Pulse} />
        <Metric label="支付与退款" value="¥612" note="占确认收入 3.6%" icon={CreditCard} />
        <Metric label="贡献毛利" value="68.4%" note="内测观测，不含固定成本" tone="green" icon={ChartLineUp} />
      </div>
      <Section title="产品经济性" kicker="COHORT ESTIMATE" className="ops-shadow-card">
        <Table rows={planEconomics} columns={[
          { key: "product", label: "产品", render: (row) => <b>{row.product}</b> },
          { key: "revenue", label: "单均收入", render: (row) => money(row.revenue) },
          { key: "variable", label: "模型与计算", render: (row) => money(row.variable) },
          { key: "payment", label: "支付成本", render: (row) => money(row.payment) },
          { key: "refund", label: "退款摊销", render: (row) => money(row.refund) },
          { key: "margin", label: "贡献毛利率", render: (row) => <b>{row.margin}</b> },
        ]} />
      </Section>
      <div className="ops-two-col">
        <Section title="成本可核对字段" kicker="COST TRACE">
          <ul className="ops-audit-list">
            <li><CheckCircle size={18} weight="fill" /><span><b>任务维度</b>输入/输出 token、候选数、重试、耗时、结算字符</span></li>
            <li><CheckCircle size={18} weight="fill" /><span><b>订单维度</b>支付金额、通道费、退款、权益发放与冲正</span></li>
            <li><CheckCircle size={18} weight="fill" /><span><b>价格版本</b>购买时快照，不用当前价格反算历史毛利</span></li>
          </ul>
        </Section>
        <Section title="风险提醒" kicker="GUARDRAILS">
          <div className="ops-note ops-note--yellow"><WarningCircle size={28} weight="fill" /><div><b>深度模式成本高于计费倍数</b><p>近 7 日深度模式单字成本是平衡模式的 1.82 倍，当前额度倍率为 1.5。建议继续观测，不在内测期承诺固定毛利。</p></div></div>
        </Section>
      </div>
    </Page>
  );
}

function LegacyAdminServicePage({ navigate }) {
  const { t } = useOpsLocale();
  const [flags, setFlags] = useState({ newJobs: true, deepMode: true, checkout: false, exports: true });
  const [feedbackEvent, setFeedbackEvent] = useState(null);
  const flagLabels = {
    newJobs: ["新建改写任务", "Create rewrite jobs"],
    deepMode: ["深度模式", "Deep mode"],
    checkout: ["真实支付入口", "Live-payment entry point"],
    exports: ["文档导出", "Document export"],
  };
  const actionFeedback = feedbackEvent?.type === "refresh"
    ? t("服务状态已在本地重新载入；没有请求真实控制面。", "Service status was reloaded locally; no real control-plane request was made.")
    : feedbackEvent?.type === "flag"
      ? t(
          `${flagLabels[feedbackEvent.key][0]}已在本地演示中${feedbackEvent.value ? "开启" : "关闭"}；真实服务配置未变更。`,
          `${flagLabels[feedbackEvent.key][1]} was turned ${feedbackEvent.value ? "on" : "off"} in the local demo; the real service configuration was unchanged.`,
        )
      : "";
  const updateFlag = (key, value) => {
    setFlags((current) => ({ ...current, [key]: value }));
    setFeedbackEvent({ type: "flag", key, value });
  };
  return (
    <Page>
      <AdminHeader title="服务控制" description="运行健康、队列与功能开关集中管理；敏感配置不进入此页面。"><Button icon={actionFeedback ? Check : ArrowsClockwise} tone={actionFeedback ? "green" : "plain"} onClick={() => setFeedbackEvent({ type: "refresh" })}>刷新</Button></AdminHeader>
      <AdminTabs navigate={navigate} active="service" />
      <DemoFeedback>{actionFeedback}</DemoFeedback>
      <div className="ops-service-banner ops-service-banner--good ops-shadow-card">
        <CheckCircle size={38} weight="fill" /><div><p className="ops-eyebrow">PRODUCTION READINESS</p><h2>7 / 8 项检查通过</h2><p>真实支付仍保持关闭；服务端回调域名与退款流程尚待验收。</p></div><StatusPill status="degraded" label="内测模式" />
      </div>
      <div className="ops-two-col ops-two-col--wide">
        <Section title="功能开关" kicker="SAFE ROLLOUT" className="ops-shadow-card">
          <Toggle checked={flags.newJobs} onChange={(value) => updateFlag("newJobs", value)} label="允许新建改写任务" note="关闭后，运行中任务继续完成" />
          <Toggle checked={flags.deepMode} onChange={(value) => updateFlag("deepMode", value)} label="开放深度模式" note="受并发与成本上限保护" />
          <Toggle checked={flags.checkout} onChange={(value) => updateFlag("checkout", value)} label="真实支付入口" note="当前关闭；仅保留演示收银台" />
          <Toggle checked={flags.exports} onChange={(value) => updateFlag("exports", value)} label="允许文档导出" note="DOCX / PDF 导出服务正常" />
        </Section>
        <Section title="容量与队列" kicker="CAPACITY">
          <div className="ops-bar-list">
            <div><span>工作进程</span><b>12 / 20</b><Progress value={12} max={20} tone="blue" /></div>
            <div><span>排队任务</span><b>37 / 300</b><Progress value={37} max={300} tone="yellow" /></div>
            <div><span>数据库连接</span><b>18 / 80</b><Progress value={18} max={80} tone="green" /></div>
            <div><span>对象存储</span><b>41%</b><Progress value={41} max={100} tone="blue" /></div>
          </div>
        </Section>
      </div>
      <Section title="服务变更记录" kicker="AUDIT LOG" className="ops-shadow-card">
        <Table rows={[
          { id: "CH-813", at: "15:22", actor: "ops-01", action: "扩容任务消费者", before: "8", after: "12", result: "healthy" },
          { id: "CH-808", at: "13:40", actor: "ops-02", action: "关闭真实支付入口", before: "开启", after: "关闭", result: "healthy" },
          { id: "CH-799", at: "09:10", actor: "system", action: "轮换服务凭据", before: "版本 17", after: "版本 18", result: "healthy" },
        ]} columns={[
          { key: "at", label: "时间" }, { key: "id", label: "事件", render: (row) => <code>{row.id}</code> }, { key: "actor", label: "操作者" },
          { key: "action", label: "动作", render: (row) => <b>{row.action}</b> }, { key: "before", label: "变更前" }, { key: "after", label: "变更后" },
          { key: "result", label: "结果", render: (row) => <StatusPill status={row.result} /> },
        ]} />
      </Section>
    </Page>
  );
}

function LegacyAdminPrivacyPage({ navigate }) {
  const { t } = useOpsLocale();
  const [view, setView] = useState("requests");
  const [retentionLock, setRetentionLock] = useState(true);
  const [feedbackEvent, setFeedbackEvent] = useState(null);
  const actionFeedback = feedbackEvent?.type === "export"
    ? t("审计摘要已在本地生成演示状态；没有下载或传输真实审计数据。", "An audit-summary demo state was generated locally; no real audit data was downloaded or transmitted.")
    : feedbackEvent?.type === "review"
      ? t(`双人复核已在本地演示中${feedbackEvent.value ? "开启" : "关闭"}；真实策略未变更。`, `Two-person review was turned ${feedbackEvent.value ? "on" : "off"} in the local demo; the real policy was unchanged.`)
      : "";
  return (
    <Page>
      <AdminHeader title="隐私控制台" description="数据留存、访问、导出与删除请求均保留最小必要的审计证据。"><Button icon={feedbackEvent?.type === "export" ? Check : DownloadSimple} tone={feedbackEvent?.type === "export" ? "green" : "plain"} onClick={() => setFeedbackEvent({ type: "export" })}>{feedbackEvent?.type === "export" ? "摘要已准备（演示）" : "导出审计摘要"}</Button></AdminHeader>
      <AdminTabs navigate={navigate} active="privacy" />
      <DemoFeedback tone="green">{actionFeedback}</DemoFeedback>
      <div className="ops-metrics ops-metrics--4">
        <Metric label="待处理请求" value="1" note="删除请求 · 剩余 5 天" tone="yellow" icon={Clock} />
        <Metric label="24h 自动删除" value="184 份" note="下一批 16:00" tone="blue" icon={Trash} />
        <Metric label="特权访问" value="0" note="过去 24 小时" tone="green" icon={Eye} />
        <Metric label="策略覆盖" value="100%" note="全部数据类型已登记" icon={ShieldCheck} />
      </div>
      <Tabs value={view} onChange={setView} items={[{ value: "requests", label: "用户请求" }, { value: "retention", label: "留存策略" }, { value: "audit", label: "访问审计" }]} />
      {view === "requests" && <Section title="权利请求" kicker="DSAR QUEUE" className="ops-shadow-card"><Table rows={[
        { id: "PR-0028", user: "U-10788", type: "删除文档与版本", received: "2026-10-09", due: "2026-10-15", scope: "17 个对象", status: "received" },
        { id: "PR-0027", user: "U-10642", type: "导出我的数据", received: "2026-10-07", due: "2026-10-13", scope: "账号、订单、任务元数据", status: "done" },
      ]} columns={[
        { key: "id", label: "请求号", render: (row) => <code>{row.id}</code> }, { key: "user", label: "用户" }, { key: "type", label: "类型", render: (row) => <b>{row.type}</b> },
        { key: "received", label: "受理日" }, { key: "due", label: "承诺完成" }, { key: "scope", label: "范围" }, { key: "status", label: "状态", render: (row) => <StatusPill status={row.status} /> },
      ]} /></Section>}
      {view === "retention" && <Section title="数据留存策略" kicker="RETENTION MAP" className="ops-shadow-card">
        <Toggle checked={retentionLock} onChange={(value) => { setRetentionLock(value); setFeedbackEvent({ type: "review", value }); }} label="策略变更双人复核" note="防止单人延长正文保留期" />
        <Table rows={[
          { id: "doc", type: "论文正文与版本", default: "24 小时", max: "7 天（用户选择）", action: "自动删除" },
          { id: "job", type: "任务元数据", default: "30 天", max: "90 天", action: "去标识化" },
          { id: "order", type: "订单与账务", default: "依交易记录要求", max: "依适用规则", action: "最小字段保留" },
          { id: "audit", type: "管理员审计", default: "180 天", max: "1 年", action: "滚动删除" },
        ]} columns={[{ key: "type", label: "数据类型" }, { key: "default", label: "默认" }, { key: "max", label: "上限" }, { key: "action", label: "到期动作" }]} />
      </Section>}
      {view === "audit" && <Section title="敏感操作审计" kicker="NO CONTENT PAYLOAD" className="ops-shadow-card"><Table rows={[
        { id: "AU-712", at: "10-10 14:02", actor: "privacy-01", action: "批准数据导出", target: "PR-0027", scope: "元数据清单", status: "healthy" },
        { id: "AU-706", at: "10-09 17:11", actor: "system", action: "执行自动删除", target: "184 个对象", scope: "正文与版本", status: "healthy" },
        { id: "AU-694", at: "10-08 09:20", actor: "ops-02", action: "查看错误追踪", target: "TR-8A11", scope: "错误码与耗时", status: "healthy" },
      ]} columns={[{ key: "at", label: "时间" }, { key: "id", label: "事件", render: (row) => <code>{row.id}</code> }, { key: "actor", label: "操作者" }, { key: "action", label: "动作" }, { key: "target", label: "对象" }, { key: "scope", label: "最小范围" }, { key: "status", label: "结果", render: (row) => <StatusPill status={row.status} /> }]} /></Section>}
    </Page>
  );
}

export function SystemStatePage({ navigate, statePath = "/404" }) {
  const { t } = useOpsLocale();
  const [connectionChecked, setConnectionChecked] = useState(false);
  const normalizedPath = String(statePath || "/404").split("?")[0];
  const states = {
    "/404": {
      code: "404",
      eyebrow: "PAGE NOT FOUND",
      title: "这一页不在论文里",
      description: "链接可能已失效，或页面地址输入有误。你的文档与额度不会受影响。",
      icon: FileText,
      primary: "返回首页",
      primaryPath: "/",
      detail: "未知路由会默认来到这里。",
    },
    "/500": {
      code: "500",
      eyebrow: "INTERNAL ERROR",
      title: "服务开了个小差",
      description: "当前操作没有完成，也不会产生重复任务或额度结算。",
      icon: WarningCircle,
      primary: "返回工作区",
      primaryPath: "/app",
      detail: "错误追踪号：RT-DEMO-500（仅演示）",
    },
    "/offline": {
      code: "OFFLINE",
      eyebrow: "CONNECTION LOST",
      title: "网络连接已中断",
      description: "已编辑内容会留在当前本地演示状态；恢复连接前不会提交任务。",
      icon: HardDrives,
      primary: "重新检查",
      detail: "检查操作仅更新界面，不会访问外部网络。",
    },
    "/maintenance": {
      code: "MAINTENANCE",
      eyebrow: "PLANNED MAINTENANCE",
      title: "正在进行短暂维护",
      description: "文档浏览仍可使用，新建改写任务暂时停用。额度不会过期或被扣除。",
      icon: Wrench,
      primary: "查看服务状态",
      primaryPath: "/app/settings/service",
      detail: "预计恢复：今天 16:30（演示信息）",
    },
    "/session-expired": {
      code: "SESSION",
      eyebrow: "SESSION EXPIRED",
      title: "登录状态已过期",
      description: "为保护论文与订单信息，请重新登录。未提交的本地编辑仍会保留。",
      icon: LockKey,
      primary: "重新登录",
      primaryPath: "/auth",
      detail: "不会自动上传或清除当前内容。",
    },
    "/insufficient-balance": {
      code: "BALANCE",
      eyebrow: "INSUFFICIENT BALANCE",
      title: "本次任务额度不足",
      description: "创建任务前的预估额度高于当前可用余额，因此没有预占、扣除或提交改写。",
      icon: Wallet,
      primary: "查看套餐与额度",
      primaryPath: "/app/billing",
      detail: "支付尚未接入；套餐与结算流程均为本地演示。",
    },
  };
  const state = states[normalizedPath] || states["/404"];
  const StateIcon = state.icon;
  const runPrimary = () => {
    if (state.primaryPath) {
      go(navigate, state.primaryPath);
      return;
    }
    setConnectionChecked(true);
  };

  return (
    <Page className="ops-state-page">
      <div className="ops-state-card ops-shadow-card">
        <div className="ops-state-code" aria-hidden="true">{state.code}</div>
        <div className="ops-state-icon"><StateIcon size={42} weight="fill" /></div>
        <p className="ops-eyebrow">SYSTEM / {state.eyebrow}</p>
        <h1>{state.title}</h1>
        <p className="ops-state-description">{state.description}</p>
        <div className="ops-state-detail"><Info size={18} weight="fill" /><span>{state.detail}</span></div>
        <div className="ops-state-actions">
          <Button tone="blue" icon={ArrowRight} onClick={runPrimary}>{state.primary}</Button>
          {state.code !== "404" && <Button onClick={() => go(navigate, "/")}>返回首页</Button>}
        </div>
        <DemoFeedback tone="green">{connectionChecked ? t("已完成本地连接检查演示；没有发起任何网络请求。", "The local connection-check demo completed; no network request was made.") : ""}</DemoFeedback>
      </div>
    </Page>
  );
}
