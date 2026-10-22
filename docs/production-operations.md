# RightThesis 生产运维说明

## 上线前与日常备份

数据库位于服务器私有 `BILLING_DB`，包含账户、论文、任务、订单和账本。**永远不要用代码同步覆盖 `data/` 或 `.env`。**先为备份生成独立 32 字节密钥，密钥仅创建一次：

```sh
python3 scripts/backup_database.py init-key --key-file /home/admin/.config/rightthesis/backup.key
python3 scripts/backup_database.py backup --database /home/admin/rightthesis/data/billing.sqlite3 --output-dir /home/admin/rightthesis-backups --key-file /home/admin/.config/rightthesis/backup.key
```

`init-key` 在密钥已存在时拒绝覆盖。备份程序使用 SQLite 在线备份 API、AES-GCM 加密，且在发布档案前进行解密及 `PRAGMA integrity_check`。档案和密钥必须分别保存在服务器之外；复制后再次运行 `verify`。不要把密钥、数据库或备份加入 Git。服务器定时任务配置在 `deploy/rightthesis-backup.service` 和 `.timer`，每天 02:35 运行；检查 `systemctl status rightthesis-backup.timer` 与 `journalctl -u rightthesis-backup.service`。单独的服务器定时备份不抵御磁盘故障，下节的 OSS 副本用于抵御此类故障。

### 加密备份上传阿里云 OSS

`deploy/rightthesis-oss-upload.service` 和 `.timer` 将在每天 02:50 上传 6 小时内的最新加密备份到香港私有 Bucket `rightthesis-backup-jude-2026` 的 `rightthesis-backups/` 前缀。上传前再次解密校验，不上传原始 SQLite 或 `backup.key`。与主服务器同在香港地域不构成跨地域容灾；务必把解密密钥另存于安全地点，并定期进行下载及还原演练。

2026-10-20 02:35 的首次自动备份与 02:50 的自动 OSS 上传均成功。上传成功后程序会在本地备份目录写 `oss-upload-receipt.json`，每日 03:05 的 `rightthesis-backup-health.timer` 核验新近备份、回执名称、SHA-256，并用独立密钥把最新本地加密档案恢复到临时目录、执行 SQLite 完整性检查；它不会触碰在线数据库。备份、上传或健康检查失败时由 `rightthesis-backup-alert@.service` 使用现有 SMTP 给 `ADMIN_EMAILS` 发邮件。部署或改动后应手动测试一次告警邮件；邮箱本身故障时告警会失败，仍须定期查看 systemd 日志。上传凭据只有写权限，这项日常检查**不能证明 OSS 对象可下载**；仍需按下方说明定期用独立身份做 OSS 下载及还原演练。用户已选择**暂不跨地域、暂不自动删除旧备份**；应关注 OSS 存储费用，并在制定删除申请与恢复窗口后再配置生命周期规则，切勿自行清理历史档案。

`GET /health` 和 `HEAD /health` 会检查 SQLite 可读且核心表存在；公网账户模式下还检查模型和已选 Stripe 通道是否已配置。异常返回 503。它是在线服务就绪检查，不向 Stripe、邮件或模型服务发起实时外部请求，因此不能代替独立支付对账与备份恢复告警。

在阿里云 RAM 中创建仅供程序使用的用户 `rightthesis-backup-uploader`，不要授予控制台登录或 `AliyunOSSFullAccess`。创建自定义权限策略并只授予该用户：

```json
{
  "Version": "1",
  "Statement": [{
    "Effect": "Allow",
    "Action": "oss:PutObject",
    "Resource": "acs:oss:*:*:rightthesis-backup-jude-2026/rightthesis-backups/*"
  }]
}
```

为该用户创建程序访问 AccessKey，并仅在服务器私有文件 `/home/admin/.config/rightthesis/oss.env` 中填写 `OSS_ACCESS_KEY_ID=...` 和 `OSS_ACCESS_KEY_SECRET=...` 两行，文件权限 `0600`。**不要把密钥发到聊天、写进 Git、放进网页或截图。**配置好后先手动启动并检查日志：

```sh
sudo systemctl start rightthesis-oss-upload.service
sudo systemctl status rightthesis-oss-upload.service --no-pager
sudo journalctl -u rightthesis-oss-upload.service -n 30 --no-pager
```

只有看到上传成功，并在 OSS 控制台确认 `rightthesis-backups/` 中存在对应 `.rtbk` 对象后，才运行 `sudo systemctl enable --now rightthesis-oss-upload.timer`。后续检查 `systemctl list-timers rightthesis-oss-upload.timer`。此写入专用凭据没有读取或删除权限；独立校验云端对象必须使用有读取权限的管理员身份，通过控制台下载后用**另一份**备份密钥运行 `verify` 和 `restore`。Bucket 版本控制及保留策略需结合隐私删除申请、存储费用和恢复要求单独制定。

恢复演练只写入一个不存在的新路径，不替换在线数据库：

```sh
python3 scripts/backup_database.py restore --archive /path/to/archive.rtbk --destination /path/to/new/restored.sqlite3 --key-file /path/to/backup.key
```

## 支付与对账

以 `GET /api/config` 的 `payment.live` 和 `payment.checkout_enabled` 判断当前环境是否开放正式收银台。真实付款与额度发放只接受已验签且从 Stripe 实时读取核对的事件，或由服务端使用正式密钥直接向 Stripe 读取核对的对象。用户查询待付款订单时会尝试恢复漏送的成功回调；每小时的 `rightthesis-stripe-reconcile.timer` 先关闭所有账户已过期或未创建成功的本地结账记录，再独立核对全部正式待处理与已付订单、补记漏送成功退款，并检查已知付款的争议。已过期订单仍会接受迟到但经过验证的付款事件。2026-10-22，正式受限密钥的 Checkout Sessions、Events、Refunds、Disputes 读取权限均已通过 `scripts/stripe_live_preflight.py` 核查；service 已移除临时的 `--skip-disputes`。对账失败或发现未解决争议时触发管理员告警邮件；证据提交和最终处置仍需人工在 Stripe 后台处理。管理员 `/admin/orders` 可查看最近 100 笔或按完整订单号查旧订单；净收入包含部分退款订单的剩余实收金额。如出现“需复核”，先检查事件交付、定时对账与服务日志，**不要直接修改 SQLite 额度**。

正式环境的管理员邮箱通过服务器私有 `ADMIN_EMAILS` 配置，多个邮箱以逗号分隔；未配置时全局订单和隐私申请 API 均拒绝访问。管理员退款入口默认关闭；须另建一枚 **Stripe 正式受限密钥**，只给 `Refunds: Write`，放入服务器私有 `STRIPE_REFUND_SECRET_KEY`（不发送到聊天、不进 Git、不替换现有收款/对账密钥），重启服务后开放。后台仅允许对已支付的正式 Stripe 订单按分发渠道退款：选择全部或部分金额、填原因和内部备注、输入完整订单号并二次确认；所有真实退款都由管理员主动提交。提交前服务器向 Stripe 核对已有退款和未解决争议，并持久化一次操作编号阻止重试造成重复退款。提交结果不确定时会锁住该订单，请先在 Stripe 后台核对，不能用新编号强行再次提交。只有 Stripe 确认成功后才冲正尚未使用的额度；Stripe 后续标记失败则恢复仍有效、未使用的额度。签名端点建议订阅 `refund.created`、`refund.updated`、`refund.failed`，定时对账可补记漏送状态。首次启用前先用小额真实订单验收完整退款链路，并核对 Stripe 交易、本站订单和额度；此测试会发生真实资金流。

## 数据导出与删除申请

用户可在 `/app/settings/account` 下载包含个人资料、文稿、任务、订单与额度流水的 JSON；密码哈希、会话令牌和验证码不导出。用户输入当前账户邮箱后可提交删除申请，处理前可取消。旧的 `/app/settings/privacy` 链接会跳转到账号设置。管理员只读页 `/admin/privacy` 展示待处理申请。

每次服务端保存且正文有变化时写入账户级文稿快照；旧文稿仅补录原稿与启用时的当前稿，不声称能恢复更早的中间修改。隐私导出包含快照，完成账户删除时一并移除；旧加密备份仍可能含删除前正文。

扫描 PDF 使用服务器本机 `pdftoppm` 与 Tesseract（简体中文、英文），不将页面送往外部 OCR 服务。仅对没有文字层且含图像的页面 OCR，每份最多 20 页，单次总耗时最多 8 分钟；OCR 结果可能误读专名、公式、表格和引文，仍只用于 PDF 诊断，不能写回原 PDF。安装依赖：`sudo apt-get install --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng`。

运营人员处理申请前，应先核对客服沟通记录、订单状态、运行任务和未用付费额度，制作并验证 24 小时内的新近备份。命令会拒绝待付款、运行任务或未用付费额度仍存在的账户：

```sh
python3 scripts/privacy_requests.py --database /home/admin/rightthesis/data/billing.sqlite3 list
python3 scripts/privacy_requests.py --database /home/admin/rightthesis/data/billing.sqlite3 fulfill --request-id pr_EXAMPLE --verified-backup /home/admin/rightthesis-backups/EXAMPLE.rtbk --key-file /home/admin/.config/rightthesis/backup.key
```

处理后，所有登录会话失效，身份、文稿与改写结果移除；订单和账本仍以不含邮箱的账户标识保留。旧加密备份可能包含删除前内容，轮换策略与恢复时的重复删除核对必须纳入运维流程。
