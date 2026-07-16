# V1.0 备份、恢复与灾备演练

本文是 V1.0 单机部署的数据保护手册。脚本位于：

- `scripts/backup.sh`：暂停写入服务，备份 PostgreSQL 和 MinIO，生成校验和并验证；
- `scripts/verify_backup.sh`：验证 SHA-256、PostgreSQL archive catalog 和 MinIO 对象数量；
- `scripts/restore.sh`：显式确认后替换 PostgreSQL/MinIO，清空 Redis并完成恢复后验证。

## 1. 数据分类

| 数据 | 权威来源 | 备份 | 恢复行为 |
|---|---|---|---|
| 租户、账号、会话、向量、审计、配置 | PostgreSQL | `pg_dump` custom format | 重建数据库并 `pg_restore` |
| 原始知识文档 | MinIO 应用 bucket | `mc mirror` | 清空应用 bucket 后镜像恢复 |
| Celery 队列/结果、限流和临时状态 | Redis | 不备份 | 恢复时 `FLUSHDB`，由系统重建 |
| JWT、加密密钥、数据库/存储口令 | `/etc/ai-customer-service/production.env` | 不放入数据备份 | 独立存入密码管理器/离线秘密备份 |
| 应用版本 | 不可变容器镜像 | 镜像仓库 | 恢复前将 `APP_IMAGE` 切到备份记录版本 |

Redis 不可用于保存无法重建的业务事实。恢复后可能丢失排队但尚未执行的知识任务，管理员应重新触发失败或中断的文档处理任务。

## 2. RPO、RTO 和一致性

V1.0 单机目标：

| 指标 | 目标 | 前提 |
|---|---|---|
| RPO | 不超过 24 小时 | 每晚成功备份并完成主机外复制 |
| RTO | 不超过 60 分钟 | 服务器可用、镜像可拉取、最近备份通过月度恢复演练 |

需要 6 小时 RPO 时，将 systemd timer 改为每 6 小时执行。需要分钟级 RPO 时，逻辑全量备份不够，应在 V1.1 以后增加 PostgreSQL WAL/PITR 和对象存储复制。

`backup.sh` 默认 `QUIESCE_WRITES=true`：记录原先正在运行的 API/Worker，最多等待 60 秒停止，然后依次备份 PostgreSQL 和 MinIO，最后恢复原运行状态。这会产生短暂停机，但避免备份期间出现“数据库已有文档记录而对象尚未写完”的跨存储不一致。

紧急情况下可设置 `QUIESCE_WRITES=false` 做在线备份，但 PostgreSQL 快照与 MinIO mirror 不是同一事务，只能作为尽力而为的副本，不计入正式 RPO。

## 3. 备份目录格式

每次备份创建独立目录：

```text
backup-YYYYMMDDTHHMMSSZ-PID/
├── postgres.dump
├── minio/bucket/**
├── metadata.env
├── compose-images.txt
└── SHA256SUMS
```

`metadata.env` 只保存版本和数量，不保存生产秘密。目录权限为 `0700`，文件不允许组或其他用户读取。脚本先写入 `.incomplete-*` 临时目录，只有验证通过后才原子重命名为正式备份目录。

## 4. 手动备份和校验

```bash
cd /opt/ai-customer-service/current
sudo ENV_FILE=/etc/ai-customer-service/production.env \
  BACKUP_ROOT=/var/backups/ai-customer-service \
  QUIESCE_WRITES=true \
  ./scripts/backup.sh
```

再次验证指定备份：

```bash
sudo ENV_FILE=/etc/ai-customer-service/production.env \
  ./scripts/verify_backup.sh \
  /var/backups/ai-customer-service/<backup-id>
```

备份成功不等于灾备完成。必须：

1. 将完整目录复制到另一个故障域；
2. 传输和远端存储均加密；
3. 远端再次执行 SHA-256 校验；
4. 保存至少一个月度恢复演练通过的备份；
5. 独立保管 `production.env` 中的加密密钥，不要把它复制进数据备份目录。

建议保留 7 个日备、4 个周备、6 个月备。删除前检查目录名和校验记录；脚本不会自动删除备份。

## 5. 定时备份

安装提供的 systemd unit：

```bash
sudo install -m 0644 deploy/systemd/ai-customer-service-backup.service \
  /etc/systemd/system/ai-customer-service-backup.service
sudo install -m 0644 deploy/systemd/ai-customer-service-backup.timer \
  /etc/systemd/system/ai-customer-service-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ai-customer-service-backup.timer
sudo systemctl list-timers ai-customer-service-backup.timer
```

立即试跑并检查日志：

```bash
sudo systemctl start ai-customer-service-backup.service
sudo systemctl status ai-customer-service-backup.service --no-pager
sudo journalctl -u ai-customer-service-backup.service -n 200 --no-pager
```

systemd unit 假设当前 release 软链接为 `/opt/ai-customer-service/current`。如目录不同，安装前修改 `ExecStart`。

备份完成后应由独立同步任务上传到加密的远端存储，并对失败告警。不要让同步任务删除本机源目录。

## 6. 生产恢复

### 6.1 恢复前检查

- 已宣布维护窗口并阻止外部流量；
- 已确认要恢复的 backup ID、创建时间和业务数据损失窗口；
- `verify_backup.sh` 通过；
- `production.env` 的 `APP_IMAGE` 与备份 `APPLICATION_IMAGE` 相同；
- 对应不可变镜像仍可拉取；
- 磁盘剩余空间足够容纳当前数据、安全备份和恢复数据；
- 明确恢复 PostgreSQL 与 MinIO 不是跨系统原子操作，失败时保持 API/Worker 停止并人工处理。

### 6.2 执行恢复

交互执行：

```bash
cd /opt/ai-customer-service/current
sudo ENV_FILE=/etc/ai-customer-service/production.env \
  BACKUP_ROOT=/var/backups/ai-customer-service \
  ./scripts/restore.sh \
  /var/backups/ai-customer-service/<backup-id>
```

脚本要求输入：

```text
RESTORE <backup-id>
```

非交互执行必须显式传完整确认字符串：

```bash
sudo ENV_FILE=/etc/ai-customer-service/production.env \
  ./scripts/restore.sh \
  /var/backups/ai-customer-service/<backup-id> \
  --confirm "RESTORE <backup-id>"
```

默认步骤：

1. 验证全部校验和和备份结构；
2. 比较备份与当前 `APP_IMAGE`；
3. 停止 API/Worker；
4. 在停止写入的状态下创建当前状态安全备份；
5. 删除并重建应用 PostgreSQL 数据库，恢复 custom dump；
6. 清空并恢复 MinIO 应用 bucket；
7. 清空 Redis DB 0；
8. 启动 MinIO 初始化、API 和 Worker；
9. 校验 readiness、Alembic revision 和 MinIO 对象数量。

只有在全新隔离演练环境中才使用 `--skip-safety-backup`。`--allow-image-mismatch` 只允许在已证明数据库向后/向前兼容时使用，并需记录审批。

恢复脚本失败会让 API/Worker 保持停止，防止部分恢复状态对外提供服务。不要在原因未确认前手工启动。

### 6.3 恢复后业务验证

```bash
ENV_FILE=/etc/ai-customer-service/production.env
COMPOSE_FILE=deploy/compose.production.yml
dc() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }

dc ps
curl --fail --show-error http://127.0.0.1:8000/health/live
curl --fail --show-error http://127.0.0.1:8000/health/ready
dc run --rm --no-deps migrate alembic current
dc logs --since=15m api worker
```

再用验收租户验证：管理员登录、应用凭据、文档下载/检索、带引用问答、无答案拒答和人工接管。检查恢复时间点之后的数据是否按已批准的 RPO 丢弃。

## 7. 隔离恢复演练

至少每月演练一次，并在版本发布前演练。演练使用新的 Compose project 和独立卷，不能连接生产卷。

1. 复制生产配置到内存/临时目录，修改项目名和 API 端口：

```bash
sudo cp /etc/ai-customer-service/production.env /run/ai-cs-drill.env
sudo chmod 0600 /run/ai-cs-drill.env
sudo sed -i \
  -e 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME=ai-customer-service-drill/' \
  -e 's/^APP_PORT=.*/APP_PORT=18000/' \
  /run/ai-cs-drill.env
grep '^COMPOSE_PROJECT_NAME=ai-customer-service-drill$' /run/ai-cs-drill.env
```

2. 验证备份并恢复到隔离 project：

```bash
cd /opt/ai-customer-service/current
BACKUP=/var/backups/ai-customer-service/<backup-id>
BACKUP_ID="$(awk -F= '$1 == "BACKUP_ID" {print substr($0, 11)}' "$BACKUP/metadata.env")"

sudo ENV_FILE=/run/ai-cs-drill.env \
  BACKUP_ROOT=/var/backups/ai-customer-service-drill \
  ./scripts/restore.sh "$BACKUP" \
  --skip-safety-backup \
  --confirm "RESTORE ${BACKUP_ID}"
```

3. 验证隔离实例：

```bash
curl --fail --show-error http://127.0.0.1:18000/health/ready
docker compose --env-file /run/ai-cs-drill.env \
  -f deploy/compose.production.yml ps
```

执行一组只读业务冒烟测试，并记录：开始时间、ready 时间、总恢复耗时、PostgreSQL revision、MinIO 对象数、抽样文档 SHA-256 和失败项。

4. 仅在再次确认 project 名后删除演练卷：

```bash
grep -qx 'COMPOSE_PROJECT_NAME=ai-customer-service-drill' /run/ai-cs-drill.env
docker compose --env-file /run/ai-cs-drill.env \
  -f deploy/compose.production.yml down -v --remove-orphans
sudo shred -u /run/ai-cs-drill.env
```

`down -v` 只允许用于名称已确认的隔离演练 project，绝不能对生产配置执行。

## 8. 演练验收记录

每次演练至少记录：

```text
版本/APP_IMAGE：
备份 ID：
备份创建时间：
演练日期与执行人：
环境：隔离 Compose project
checksum 校验：通过/失败
PostgreSQL archive 校验：通过/失败
PostgreSQL revision：
MinIO 期望/实际对象数：
readiness：通过/失败
业务冒烟：通过/失败
实际 RPO：
实际 RTO：
问题与修复：
结论：可恢复/不可恢复
```

只有实际执行恢复并完成业务抽样，才可以把该备份和流程标记为“可恢复”。单独执行 `verify_backup.sh` 只是完整性检查，不等于恢复演练。
