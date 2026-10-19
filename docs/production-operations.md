# RightThesis 生产运维说明

## 上线前与日常备份

数据库位于服务器私有 `BILLING_DB`，包含账户、论文、任务、订单和账本。**永远不要用代码同步覆盖 `data/` 或 `.env`。**先为备份生成独立 32 字节密钥，密钥仅创建一次：

```sh
python3 scripts/backup_database.py init-key --key-file /home/admin/.config/rightthesis/backup.key
python3 scripts/backup_database.py backup --database /home/admin/rightthesis/data/billing.sqlite3 --output-dir /home/admin/rightthesis-backups --key-file /home/admin/.config/rightthesis/backup.key
```

`init-key` 在密钥已存在时拒绝覆盖。备份程序使用 SQLite 在线备份 API、AES-GCM 加密，且在发布档案前进行解密及 `PRAGMA integrity_check`。档案和密钥必须分别保存在服务器之外；复制后再次运行 `verify`。不要把密钥、数据库或备份加入 Git。服务器定时任务配置在 `deploy/rightthesis-backup.service` 和 `.timer`，每天 02:35 运行；检查 `systemctl status rightthesis-backup.timer` 与 `journalctl -u rightthesis-backup.service`。还需要另行配置云端异地目标或定期拉取，**定时备份本身不是异地备份**。

### 加密备份上传阿里云 OSS

`deploy/rightthesis-oss-upload.service` 和 `.timer` 将在每天 02:50 上传 6 小时内的最新加密备份到香港私有 Bucket `rightthesis-backup-jude-2026` 的 `rightthesis-backups/` 前缀。上传前再次解密校验，不上传原始 SQLite 或 `backup.key`。与主服务器同在香港地域不构成跨地域容灾；务必把解密密钥另存于安全地点，并定期进行下载及还原演练。

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

以 `GET /api/config` 的 `payment.live` 和 `payment.checkout_enabled` 判断当前环境是否开放正式收银台。真实付款与额度发放只接受已验签且从 Stripe 实时读取核对的事件。退款应在 Stripe 中操作；本地按成功退款累计金额调整未用额度。管理员只读页 `/admin/orders` 展示最近 100 笔订单、平台累计退款和已收到的 Stripe 回调累计退款；“本地一致”**不能发现未送达的 Stripe 事件**，仍需定期在 Stripe 后台核对。如出现“需复核”，先检查事件交付与服务日志，**不要直接修改 SQLite 额度**。银行卡争议目前仍需在 Stripe 后台人工处理。

正式环境的管理员邮箱通过服务器私有 `ADMIN_EMAILS` 配置，多个邮箱以逗号分隔；未配置时全局订单和隐私申请 API 均拒绝访问。此配置不授予任何退款或修改额度的接口权限。

## 数据导出与删除申请

用户可在 `/app/settings/privacy` 下载包含个人资料、文稿、任务、订单与额度流水的 JSON；密码哈希、会话令牌和验证码不导出。用户输入当前账户邮箱后可提交删除申请，处理前可取消。管理员只读页 `/admin/privacy` 展示待处理申请。

运营人员处理申请前，应先核对客服沟通记录、订单状态、运行任务和未用付费额度，制作并验证 24 小时内的新近备份。命令会拒绝待付款、运行任务或未用付费额度仍存在的账户：

```sh
python3 scripts/privacy_requests.py --database /home/admin/rightthesis/data/billing.sqlite3 list
python3 scripts/privacy_requests.py --database /home/admin/rightthesis/data/billing.sqlite3 fulfill --request-id pr_EXAMPLE --verified-backup /home/admin/rightthesis-backups/EXAMPLE.rtbk --key-file /home/admin/.config/rightthesis/backup.key
```

处理后，所有登录会话失效，身份、文稿与改写结果移除；订单和账本仍以不含邮箱的账户标识保留。旧加密备份可能包含删除前内容，轮换策略与恢复时的重复删除核对必须纳入运维流程。
