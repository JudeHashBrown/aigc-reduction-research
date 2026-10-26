# RightThesis · 中英文学术写作本地 MVP

面向学生自有稿件的中英文学术表达优化工具。它不伪造一个“AI 率”，而是完成一条
可审阅的闭环：

```text
粘贴 / DOCX / PDF
→ 逐段识别中文 / 英文并运行对应检查
→ 安全清理或保真改写
→ 数字、引用、专名与语义边界守卫
→ 逐字对照
→ 复制或尽量保留段落 / run 样式导出 DOCX
```

## 当前能力

- **中英双语分析**：逐段识别语言；中文走 31 项 Humanizer-zh 检查，英文走 13 类词汇、句式与段落检查，每条都定位原文并给出边界。
- **上下文优先**：三项列表、破折号、连接词和被动句不会被机械判错。
- **安全清理**：只处理可以在不理解语义时确定改对的格式或空泛词。
- **保真改写**：可选保守、平衡、深度三档候选数，改写不通过守卫就保留原文。
- **事实守卫**：阻止新增数字、引用、中英文专名，以及静默改变：
  - 否定：“不开放”→“开放”
  - 确定程度：“可能”→“确定”
  - 进度：“计划”→“已完成”
  - 范围：“超过 3000”→“等于 3000”
  - 关系：“相关”→“导致”
- **文档入口**：粘贴文本、TXT、DOCX 和 PDF。PDF 只诊断；DOCX 导出会尽量保留原段落和 run 样式，含复杂修订、域、手动换行的文档仍需在 Word 中复核。
- **持久文稿与任务**：每次导入新建独立文稿，原稿、修改稿、原始 DOCX/PDF 字节及诊断结果保存在服务端 SQLite；改写任务和完整结果也持久化，刷新后可接续查看。粘贴/TXT/PDF 可复制或下载最终 TXT；导入 DOCX 另可尝试保留格式导出。
- **本地优先**：规则分析不离开本机；只有模型改写会发送到平台在服务端配置的 LLM 接口，使用者不需要提供密钥。
- **额度与支付**：SQLite 额度账本、服务端套餐表、幂等订单、改写前预占和失败自动退回。默认支付为 **mock 模拟**；Stripe 支持测试与显式开启的正式 Checkout。

## 运行

```bash
python3 -m pip install -r requirements.txt
cd platform-ui
npm ci
npm run build
cd ..
python3 web/server.py
```

打开 <http://127.0.0.1:8765>。服务会优先提供 `platform-ui/dist/client` 中的开心果绿 React 全平台界面；旧版工作台保留在 <http://127.0.0.1:8765/legacy> 作为回退。若尚未构建 React 前端，首页会安全回退到旧版工作台。不配置 LLM 也可以使用中英文分析、安全清理和文档功能。

平台管理员启用保真改写：

```bash
cp .env.example .env
# 然后仅在服务端 .env 内填入 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL
python3 web/server.py
```

`.env` 已被 Git 忽略，密钥不会返回浏览器；同名进程环境变量的优先级更高。`LLM_BASE_URL` 可以是兼容 OpenAI Chat Completions 的接口。客户端会在对方不支持 `n` 候选参数时自动降级为多次独立调用。计费相关的本地默认值等价于：

```dotenv
PAYMENT_PROVIDER=mock
BILLING_DB=data/billing.sqlite3
```

`mock` 只用来跑通界面、套餐和额度逻辑，点击“模拟购买”不会发起 Stripe、易支付或任何真实交易。

### Stripe Checkout

仅在 `AUTH_MODE=accounts` 下启用。五档套餐价格、额度和有效期均由 `web/billing.py` 服务端目录决定；支付使用同一个 Checkout `payment` 收银台。新建 RightThesis 收银台目前通过 `excluded_payment_method_types` 暂不展示微信支付，其余方式由 Stripe 按账户、地区、货币和设备判断。两档月卡是单次购买的 30 天权益，**不会自动续费**。

1. 在 Stripe 测试模式获取 Secret key，并安装 `requirements.txt` 中的 Stripe Python SDK。
2. 在另一个终端运行 `stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded --forward-to http://127.0.0.1:8877/api/billing/stripe/webhook`，记录 CLI 输出的 `whsec_`。本地 CLI 的签名密钥不同于 Dashboard webhook 密钥。
3. 仅在本机未提交的 `.env` 中设置 `AUTH_MODE=accounts`、`PAYMENT_PROVIDER=stripe`、`STRIPE_SECRET_KEY=sk_test_...`、`STRIPE_WEBHOOK_SECRET=whsec_...`、`STRIPE_LIVE_ENABLED=0`、`PUBLIC_ORIGIN=http://127.0.0.1:8877`，并启动 `python3 web/server.py 8877`。
4. 登录账户，从“额度与订单”进入收银台。Stripe 返回平台后，页面从服务端读取订单状态；只有验签通过、订单号/金额/币种/账户核对无误的回调才能增加额度。测试卡、微信及支付宝的实际可见性受 Stripe 测试账户设置和收银台条件影响。

公网正式收款的启用条件：在 Stripe **正式模式**创建 HTTPS Webhook 端点 `https://rightthesis.com/api/billing/stripe/webhook`，订阅 `checkout.session.completed`、`checkout.session.async_payment_succeeded`、`refund.created` 和 `refund.updated`；把正式模式的 `rk_live_`（至少需要创建和读取 Checkout Session、读取 Event 与 Refund 的权限；`sk_live_` 也可用）与此端点的 `whsec_` 仅写入服务器私有 `.env`；确认 `PUBLIC_ORIGIN=https://rightthesis.com`，先运行 `python3 scripts/stripe_live_preflight.py` 确认只读权限，再设置 `STRIPE_LIVE_ENABLED=1` 并重启服务。缺任一条件时收银台保持关闭。Webhook 通过签名、环境核验后，正式模式还会用独立 API 密钥从 Stripe 实时读取事件及收银台或退款对象，再核对订单号、账户、商品、金额和币种；无法读取时不会发放或撤销额度。成功退款会按累计退款金额调整该订单未用额度；已消耗额度不能追回。银行卡争议仍需人工核对。**公网实际开关以 `/api/config` 的 `payment.live` 与 `payment.checkout_enabled` 为准，不依赖文档中的静态状态。**

## 文稿保存与恢复

文稿和任务与额度账本同存于 `BILLING_DB`（默认 `data/billing.sqlite3`）。编辑时页面先按文稿在浏览器保留待同步文字，再自动保存到服务端；“已保存”表示服务端确认。保存失败会提示并允许下载本地备份，不能把未同步的稿件当成已保存。多标签页同改一稿会拒绝过期版本，避免静默覆盖；不同文稿的待同步备份彼此独立。退出登录会清理已同步缓存，但保留待同步稿供重新登录后恢复。新导入不会覆盖已有文稿，可从文档首页重新打开。

服务重启后，已完成任务的结果仍可在“版本与任务历史”下载；若模型生成时进程中断，不能安全续跑同一次调用，任务会标记中断并尝试退回预占额度。如果结果已写入数据库但尚未结算，重启会继续完成结算。旧版 `sessionStorage` 里的文字会迁移为独立“恢复文本”；旧版从未保存的原始 DOCX 字节无法恢复，需要重新导入。

文稿与任务在单机 SQLite 持久化；生产环境还每天制作 AES-GCM 加密的一致性备份，上传到香港私有 OSS，并检查上传回执。备份与主机同在香港，不是跨地域容灾；用户已选择暂不自动删除旧备份。需另存解密密钥、定期还原演练，并监控备份告警。对复杂 DOCX，导出失败时可下载完整 TXT 作为可用成果；程序会复核回写后的文字，域、未接受的修订或手动换行无法安全修改时拒绝导出，仍需在 Word 中核对样式与引用。

登录账户可以在“隐私与数据”下载 JSON 数据导出，或提交、取消账户删除申请。删除需由运营核对任务、待付款订单及未用付费额度后，使用 `scripts/privacy_requests.py` 在已验证的新近备份保护下处理。处理时删除身份、文稿和改写结果；交易与用量记录以去身份化账户标识保留，用于财务对账。加密备份在轮换前仍可能包含先前内容。具体操作见 [生产运维说明](docs/production-operations.md)。

## Google 与邮箱账号登录

默认 `AUTH_MODE=local` 仍保留无登录的本地开发体验。需要测试真实账号流程时，先在
`.env` 中启用：

```dotenv
AUTH_MODE=accounts
AUTH_SESSION_SECRET_FILE=data/auth_session_secret
AUTH_SESSION_DAYS=7

# 本地测试：验证码只打印到运行 server.py 的终端
AUTH_EMAIL_DELIVERY=console

# Google 可选；三项必须与 Google Cloud Console 完全一致
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8765/api/auth/google/callback
```

然后通过 <http://localhost:8765> 打开页面。Google 会校验授权回调的
`state`、OIDC `nonce`、PKCE、ID Token 签名、audience 和已验证邮箱；不保存
Google access token 或 refresh token。如果没有配置 Google 凭据，对应入口会明确返回
`尚未配置`，不会假装登录成功。

邮箱账号使用标准“邮箱 + 密码”：

- 注册必须输入邮箱验证码，未验证不创建凭据。
- 新密码为 6–128 个字符，需包含 ASCII 大写字母、小写字母和数字；可以额外使用
  符号、空格和 Unicode 字符。服务不会 trim 或偷偷改写密码；已有密码仍可正常登录。
- 密码使用 Argon2id（至少 19 MiB 内存、`t=2`、`p=1`）加盐哈希，数据库不存明文密码。
- 忘记密码响应始终使用同一泛化文案，不泄露邮箱是否已注册；重置成功会
  撤销该账号所有旧会话。
- 注册/重置验证码有效 10 分钟、最多尝试 5 次、60 秒才能重发；数据库仅保存带
  服务端密钥的 HMAC，验证码还绑定当前浏览器预登录会话。

共享或公网环境不得使用 `console` 邮件模式。需配置 `AUTH_EMAIL_DELIVERY=smtp`、
`AUTH_EMAIL_FROM`、`AUTH_SMTP_HOST/PORT/USERNAME/PASSWORD`，并为发件域名配置
SPF、DKIM 和 DMARC。公网入口必须配置精确 `PUBLIC_ORIGIN` 并经 HTTPS 反向代理；
应用服务本身仍只监听回环地址。

腾讯企业邮箱可作为验证码发件箱。在 `.env` 中设置 `AUTH_EMAIL_DELIVERY=smtp`、
`AUTH_SMTP_HOST=smtp.exmail.qq.com`、`AUTH_SMTP_PORT=465`、`AUTH_SMTP_SSL=1`、
`AUTH_SMTP_STARTTLS=0`；`AUTH_EMAIL_FROM` 与 `AUTH_SMTP_USERNAME` 填完整的企业邮箱地址，
`AUTH_SMTP_PASSWORD` 填该邮箱的客户端专用密码/授权码，而非在前端填写。
生成授权码并开启 SMTP 客户端访问后重启服务。缺少发件邮箱或授权码时，
服务会保留已有邮箱密码登录，但不会开放不能发送验证码的注册/找回流程。
注册与重发会在 SMTP 拒绝邮件时直接报错；找回密码始终保持泛化响应，
避免泄露邮箱是否已注册。
如果本机直连 SMTP 465 超时而本地 HTTP 代理支持 CONNECT，可选设
`AUTH_SMTP_PROXY_URL=http://127.0.0.1:7890`；仅 SSL 模式支持该代理设置，
TLS 证书仍会正常校验。能直连的部署环境应留空。

账号接口为：

| 接口 | 用途 |
|---|---|
| `POST /api/auth/register` | 提交邮箱、密码与可选显示名，发送注册验证码 |
| `POST /api/auth/register/resend` | 冷却结束后重新发送注册验证码 |
| `POST /api/auth/register/verify` | 验证注册码并创建登录会话 |
| `POST /api/auth/login` | 邮箱密码登录 |
| `POST /api/auth/password/forgot` | 泛化的忘记密码申请 |
| `POST /api/auth/password/reset` | 验证重置码、更换密码并撤销旧会话 |
| `GET /api/auth/google/start` | 开始 Google OAuth |
| `GET /api/auth/google/callback` | Google OAuth 回调 |
| `POST /api/auth/logout` | 撤销当前会话 |

所有 POST 都要求精确同源 `Origin` 和 `X-CSRF-Token`。会话 Cookie 是不透明随机值，
数据库仅存 token hash；登录成功会同时旋转会话与 CSRF token。

## 局域网匿名试用

默认仍是原有的回环单用户模式。要让同一可信 Wi-Fi / 有线局域网中的人直接试用，同时启用内测、开放访问和精确的局域网 Origin：

```bash
AUTH_MODE=trial \
TRIAL_BIND_HOST=192.168.1.51 \
TRIAL_LAN_ORIGIN=http://192.168.1.51:8766 \
TRIAL_SESSION_DAYS=1 \
python3 web/server.py 8766
```

同网设备打开 `http://192.168.1.51:8766` 即可进入。第一次访问会为当前浏览器自动签发匿名会话，并分配独立账户、任务和默认 3,000 字额度。重复打开不会重复发额度；清除 Cookie 或使用无痕窗口会被视为新访客。试用模式下 mock 充值始终被禁用。

`TRIAL_LAN_ORIGIN` 是唯一允许的局域网 Host/Origin，不做通配或后缀匹配；服务还会拒绝来自非私有网段的客户端。如果 Mac 获取到新的局域网 IP，需要更新上面两处 IP 并重启服务。

### 局域网模式的安全边界

- 局域网入口是 HTTP，Cookie 仍使用 `HttpOnly; SameSite=Strict`，写请求仍要求 CSRF，但没有 TLS 加密。只在信任的家庭/办公网络使用。
- 任何能连入该局域网的人都能获得一个匿名账户；这不是正式用户认证，也不适合公共 Wi-Fi。
- 规则分析在运行服务的 Mac 上完成；用户主动点击保真改写时，正文仍会发往已配置的 LLM 提供商。
- 如果后续需要异地访问和 HTTPS，可将绑定改回 `127.0.0.1`，并使用 `TRIAL_PUBLIC_ORIGIN` + Tailscale Serve；不要用 Funnel 公开到互联网。

## 本地套餐与计量

| 套餐 | 价格 | 额度 | 单次上限 | 有效期 |
|---|---:|---:|---:|---:|
| 免费体验 | ¥0 | 800 字 | 800 字 | 不过期 |
| 小字数包 | ¥9.9 | 3,000 字 | 3,000 字 | 90 天 |
| 论文包 | ¥29.9 | 10,000 字 | 10,000 字 | 90 天 |
| 大论文包 | ¥69.9 | 30,000 字 | 30,000 字 | 90 天 |
| 学生月卡 | ¥39.9 | 20,000 字 | 10,000 字 | 30 天 |
| 高频月卡 | ¥79.9 | 60,000 字 | 30,000 字 | 30 天 |

分析和安全清理不扣额度。模型改写按“归一化后的非空白 Unicode 字符数”计量：保守/平衡为 1.0 倍，深度为 1.5 倍并向上取整。创建任务时先原子预占，至少一个候选通过守卫才结算；调用失败或零采纳会全额释放。免费层只开放保守模式，任一有效付费额度会解锁平衡/深度模式。

上表是首版定价假设，不代表已经验证的毛利。真实上线前应按任务记录 LLM 输入/输出 token、重试和零采纳成本，再加上支付费率与退款做套餐贡献毛利验证。

默认本地模式使用固定 demo 账户；`TRIAL_MODE=1` 时改用每浏览器的匿名账户隔离。可用接口为 `GET /api/billing/plans`、`GET /api/billing/summary`、`GET /api/billing/ledger` 和 `POST /api/billing/checkout`；最后一个在试用模式下返回 `403`。这些仍是 MVP 联调契约，不是可直接暴露公网的真实支付 API。

## 测试

```bash
./tests/run_all.sh
```

测试覆盖：中英文分析/清理/改写与混排文档、原有诊断不变量、DOCX/PDF、LLM 失效模式、服务端输入、语义守卫，以及计费幂等、并发预占、失败回滚、过期额度、匿名会话、CSRF、精确局域网 Host/Origin 和跨账户任务隔离。

## 产品边界

- 这些是表达问题和修改建议，**不是作者身份判定**。
- 不承诺“保证过知网/维普”，不报未经校准的 AI 百分比。
- 平台只编辑学生已有内容，不生成虚假实验、数据、引用或经历。
- 不会为了迷惑检测器故意制造错别字或语病。
- 检测器效果必须按平台、版本、学科和文本长度单独校准。
- 局域网启动只允许绑定显式配置的私有 IP，并校验精确 Host / Origin 与客户端网段；不应使用路由器端口转发暴露公网。
- 局域网匿名会话和账户隔离只是小范围内测层，不等于生产级用户系统。
- 当前没有真实 Stripe/易支付接入、公网 Webhook 或签名校验，**不可收真钱**。
- 正式上线仍需要数据库备份与恢复演练、多实例任务协调、支付 HTTPS 回调、原始请求体验签、支付事件幂等和服务端金额校验。

## 结构

| 路径 | 用途 |
|---|---|
| `engine/humanizer_bilingual.py` | 中英逐段路由与统一的产品 API 响应 |
| `engine/humanizer_cn.py` | Humanizer-zh 分析、安全清理、多候选改写与验证 |
| `engine/guard.py` | 数字、引用、专名、术语和语义边界守卫 |
| `engine/docx_io.py` | DOCX 提取与写回 |
| `engine/pdf_io.py` | PDF 正文提取（只读） |
| `web/server.py` | 本地 HTTP API 与异步改写任务 |
| `web/workspace_store.py` | 按账户保存文稿、原文件和改写结果 |
| `web/billing.py` | 本地套餐、SQLite 额度账本与原子预占 |
| `web/trial_session.py` | 匿名会话、签名 Cookie 与 CSRF |
| `web/auth.py` | 邮箱密码、注册/重置验证、Google OAuth 与可撤销会话 |
| `platform-ui/` | 开心果绿中英双语 React 产品前端与 32 路由页面地图 |
| `web/index.html` | `/legacy` 无构建依赖回退工作台 |
| `tests/` | 守卫、文档、网页 API 与失效模式测试 |
| `研究笔记/` | 早期原理、竞品和检测器实验档案 |

## 来源与许可

核心编辑政策来自 `op7418/Humanizer-zh` commit `f4518a8`，该项目使用 MIT License。
商用或分发时必须保留对应版权和许可文本。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
