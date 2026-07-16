# V1.0 单机生产部署、升级与回滚

本文用于在一台 Linux 服务器上运行 AI 客服 V1.0。部署单元包括 API、Worker、PostgreSQL/pgvector、Redis 和 MinIO；主机 Nginx 提供 TLS。开发用 `docker-compose.yml` 不参与生产，生产统一使用 `deploy/compose.production.yml`。

备份与灾备演练见 [backup-restore.md](backup-restore.md)。

## 1. 部署边界

- PostgreSQL 保存租户、身份、模型配置、会话、知识元数据、向量和审计数据，是权威数据。
- MinIO 保存上传的知识文档，是权威数据。
- Redis 保存 Celery 队列/结果、限流等短期状态，不是权威数据，不进入备份。
- API 仅发布到主机 `127.0.0.1:8000`，数据库、Redis、MinIO 不发布主机端口。
- 同一应用镜像包含管理后台、客服工作台、JavaScript SDK 和 Widget 静态产物；API 分别在
  `/console/`、`/sdk/` 和 `/widget/` 提供，不需要在服务器维护第二份前端发布目录。
- Nginx 是唯一公网入口，SSE 关闭代理缓冲。
- V1.0 是单机部署，不提供主机故障自动切换或零停机迁移。

## 2. 服务器要求

建议起步规格为 4 vCPU、8 GiB 内存、100 GiB SSD，操作系统为受支持的 64 位 Linux。安装并启用：

- Docker Engine 26 或更高版本；
- Docker Compose Plugin 2.24 或更高版本；
- Nginx、Certbot、`curl`、`openssl`、`sha256sum`；
- 域名 A/AAAA 记录已指向服务器；
- 防火墙只对公网开放 SSH、80、443。

检查：

```bash
docker version
docker compose version
nginx -v
certbot --version
```

启用 Docker 和 Nginx 开机启动：

```bash
sudo systemctl enable --now docker
sudo systemctl enable nginx
```

## 3. 目录与发布物

推荐目录：

```text
/opt/ai-customer-service/
├── releases/<release-id>/     # 当前版本代码、compose 和脚本
└── current -> releases/<release-id>
/etc/ai-customer-service/
└── production.env             # 仅 root 可读，不进 Git
/var/backups/ai-customer-service/
```

初始化：

```bash
sudo install -d -m 0755 /opt/ai-customer-service/releases
sudo install -d -m 0700 /etc/ai-customer-service
sudo install -d -m 0700 /var/backups/ai-customer-service
```

将经过 CI 的 release 源码放进 `/opt/ai-customer-service/releases/<release-id>`，再更新软链接：

```bash
sudo ln -sfn /opt/ai-customer-service/releases/<release-id> \
  /opt/ai-customer-service/current
cd /opt/ai-customer-service/current
```

应用镜像必须使用不可变版本号或 digest，禁止生产使用 `latest`：

```bash
docker build --pull -t ghcr.io/<owner>/ai-customer-service:1.0.0 .
docker push ghcr.io/<owner>/ai-customer-service:1.0.0
```

也可以由 CI 构建并推送，服务器只执行 `docker compose pull`。

## 4. 生产配置与秘密

安装模板：

```bash
cd /opt/ai-customer-service/current
sudo install -m 0600 .env.production.example \
  /etc/ai-customer-service/production.env
sudoedit /etc/ai-customer-service/production.env
```

至少替换 `APP_IMAGE`、所有 `replace_with...`、域名和 CORS。口令使用 URL 安全的十六进制字符，因为 Compose 会用 PostgreSQL/Redis 口令拼接连接 URL：

```bash
openssl rand -hex 32  # PostgreSQL
openssl rand -hex 32  # Redis
openssl rand -hex 32  # MinIO root
openssl rand -hex 32  # MinIO application user
openssl rand -hex 32  # JWT secret
openssl rand -hex 32  # credential pepper
openssl rand -base64 32 | tr '+/' '-_'  # Fernet APP_ENCRYPTION_KEY
```

生产要求：

- `APP_JWT_SECRET`、`APP_CREDENTIAL_PEPPER`、数据库和存储口令彼此不同；
- `APP_ENCRYPTION_KEY` 一旦丢失，数据库中的模型供应商 API Key 无法解密；必须纳入独立秘密备份；
- `APP_CORS_ORIGINS` 是 JSON 数组，只列出真实接入页面，例如 `["https://support.example.com","https://www.example.com"]`；
- `APP_CORS_ORIGINS` 只控制管理后台等员工接口。Widget 的聊天路径允许动态跨域预检，但实际请求会根据
  Customer Token 中的应用身份再次校验后台维护的 `allowed_origins`；新增客户站点不需要修改部署配置。
- `APP_ALLOW_PRIVATE_PROVIDER_URLS=false`，除非经过 SSRF 风险审查；
- 真实配置不得位于仓库内，也不得出现在日志、工单或聊天中；
- `/etc/ai-customer-service/production.env` 所有者为 root、权限为 `0600`；
- PostgreSQL、Redis、MinIO 和应用镜像都应在正式上线前记录测试过的 tag/digest。应用镜像必须固定版本。
- `.env.production.example` 固定了开发时验证的 MinIO release 标签；升级这些基础镜像必须作为显式变更完成测试，
  正式部署记录还应保存实际拉取到的 digest。

检查文件权限和占位符：

```bash
sudo stat -c '%U %G %a %n' /etc/ai-customer-service/production.env
if sudo grep -En 'replace_with|example\.com|ghcr\.io/example' \
  /etc/ai-customer-service/production.env; then
  echo '生产配置仍含占位符' >&2
  exit 1
fi
```

不要执行 `source production.env`。配置含 JSON，且生产文件应被当作数据而不是 shell 脚本。

## 5. 首次启动和迁移

后续命令均在发布目录执行：

```bash
cd /opt/ai-customer-service/current
ENV_FILE=/etc/ai-customer-service/production.env
COMPOSE_FILE=deploy/compose.production.yml
dc() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }
```

先校验 Compose；`config --quiet` 不打印展开后的秘密：

```bash
dc config --quiet
dc pull postgres postgres-tools redis minio minio-init minio-client api worker migrate
```

首次部署按以下顺序执行：

```bash
dc up -d postgres redis minio
dc run --rm minio-init
dc run --rm migrate
dc up -d api worker
dc ps
```

迁移必须作为独立的一次性任务完成，不能让每个 API/Worker 启动时自动迁移。

验证：

```bash
curl --fail --show-error http://127.0.0.1:8000/health/live
curl --fail --show-error http://127.0.0.1:8000/health/ready
dc run --rm --no-deps migrate alembic current
dc logs --tail=100 api worker
```

首次创建平台管理员：

```bash
read -r -s -p 'Initial admin password: ' ADMIN_PASSWORD
printf '\n'
printf '%s\n' "$ADMIN_PASSWORD" | dc run --rm --no-deps -T \
  migrate python scripts/bootstrap_admin.py \
  --email admin@example.com \
  --display-name 'Platform Admin' \
  --password-stdin
unset ADMIN_PASSWORD
```

该命令只运行一次。密码通过标准输入传给容器，不写入进程参数、环境文件或 shell 历史；创建后应立即登录
`/console/`，使用侧栏账户区的“Change password”操作轮换密码。

## 6. Nginx 和 TLS

以下示例假设 API 主机端口仍为 8000。若修改 `APP_PORT`，同步修改 Nginx upstream。

```bash
export DOMAIN=support.example.com
sudo install -d -m 0755 /var/www/certbot
sudo sed "s/support\.example\.com/${DOMAIN}/g" \
  deploy/nginx/acme-bootstrap.conf \
  | sudo tee /etc/nginx/conf.d/ai-customer-service-acme.conf >/dev/null
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email ops@example.com --agree-tos --no-eff-email
```

证书签发后切换正式配置：

```bash
sudo rm -f /etc/nginx/conf.d/ai-customer-service-acme.conf
sudo sed "s/support\.example\.com/${DOMAIN}/g" \
  deploy/nginx/ai-customer-service.conf \
  | sudo tee /etc/nginx/conf.d/ai-customer-service.conf >/dev/null
sudo nginx -t
sudo systemctl reload nginx
curl --fail --show-error "https://${DOMAIN}/health/ready"
curl --fail --show-error "https://${DOMAIN}/console/" >/dev/null
curl --fail --show-error "https://${DOMAIN}/widget/ai-support-widget.js" >/dev/null
sudo certbot renew --dry-run
```

模板已为 SSE 设置 `proxy_buffering off`、一小时读写超时，并限制上传请求体为 25 MiB。证书续期使用 webroot，不要求停止 Nginx。

## 7. 上线验证

至少完成以下检查并记录时间、镜像和执行人：

```bash
dc ps
curl --fail --show-error "https://${DOMAIN}/health/live"
curl --fail --show-error "https://${DOMAIN}/health/ready"
curl --fail --show-error "https://${DOMAIN}/openapi.json" >/dev/null
curl --fail --show-error "https://${DOMAIN}/console/" >/dev/null
curl --fail --show-error "https://${DOMAIN}/sdk/index.js" >/dev/null
curl --fail --show-error "https://${DOMAIN}/widget/ai-support-widget.js" >/dev/null
dc run --rm --no-deps migrate alembic current
dc logs --since=10m api worker
```

业务验证还应覆盖：管理员登录、创建测试租户/应用、上传一份文档、Worker 完成索引、Widget SSE 回答带引用、无证据拒答、转人工和租户隔离。生产验证使用专门的验收租户，不使用真实客户数据。

创建两个中立演示租户后，可以在 API 容器内执行真实 HTTP Smoke 流程。脚本会安全提示演示管理员密码，验证
两租户的引用回答、引用原文、拒答、人工接管和跨租户隔离，并自动吊销临时应用凭据：

```bash
dc exec api python scripts/smoke_v1.py --base-url http://127.0.0.1:8000
```

该命令在开发阶段只用于发现问题。只有待验收版本、镜像和环境冻结后重新执行并保存结果，才可以作为该版本
正式验收记录的一部分。

## 8. 日常运行

查看状态和日志：

```bash
dc ps
dc logs --since=30m api
dc logs --since=30m worker
docker system df
df -h
```

Compose 已设置容器日志轮转。至少监控：

- `/health/ready` 连续失败（该检查覆盖 PostgreSQL、Redis 和 MinIO Bucket）；
- 磁盘使用率超过 70%/85%；
- API 5xx、429 和 SSE 断开率；
- Worker 队列积压和任务失败；
- PostgreSQL 连接数、慢查询和备份失败；
- MinIO 容量和对象读取错误；
- TLS 到期时间。

不要运行 `docker compose down -v`，其中 `-v` 会删除全部权威数据卷。

## 9. 升级

升级使用不可变镜像，单机模式接受短暂停机。准备新 release 目录，但先让 `current` 和生产环境文件仍指向旧版本/旧镜像。

1. 记录旧 `APP_IMAGE`、Git commit 和 Alembic revision，并在 Nginx/上游进入维护状态。
2. 停止 API/Worker，用旧版本执行升级前备份，并将备份复制到主机外。
3. 更新 `current` 到新 release，并把 `APP_IMAGE` 改为新不可变 tag。
4. 拉取新镜像、迁移、启动并验证。

```bash
cd /opt/ai-customer-service/current
ENV_FILE=/etc/ai-customer-service/production.env
COMPOSE_FILE=deploy/compose.production.yml
dc() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }

dc stop -t 60 api worker
ENV_FILE="$ENV_FILE" BACKUP_ROOT=/var/backups/ai-customer-service \
  ./scripts/backup.sh

# 更新 current 和 production.env 的 APP_IMAGE 后：
dc config --quiet
dc pull api worker migrate
dc run --rm migrate
dc up -d api worker
curl --fail --show-error http://127.0.0.1:8000/health/ready
dc run --rm --no-deps migrate alembic current
```

只有健康检查和业务冒烟测试通过后才结束变更窗口。保留旧镜像、旧 release 和升级前备份，直到观察期结束。

## 10. 回滚

### 10.1 仅应用回滚

只在新迁移经过评审、明确向后兼容时使用：

1. 将 `APP_IMAGE` 改回旧不可变 tag；
2. 将 `current` 指回对应旧 release；
3. `dc up -d api worker`；
4. 验证健康和业务流程。

不要自动执行 `alembic downgrade`。每条 downgrade 必须在 PostgreSQL 副本上单独演练后才能用于生产。

### 10.2 数据回滚

迁移不向后兼容、迁移失败后状态不明，或新版本已写入不兼容数据时：

1. 停止 API/Worker；
2. 将 `APP_IMAGE` 和 `current` 切回升级前版本；
3. 使用升级前备份执行 `scripts/restore.sh`；
4. 完成健康、Alembic revision、MinIO 对象数和业务验证。

```bash
BACKUP=/var/backups/ai-customer-service/<upgrade-backup-id>
ENV_FILE=/etc/ai-customer-service/production.env \
  ./scripts/restore.sh "$BACKUP"
```

恢复会要求输入 `RESTORE <backup-id>`。数据回滚会丢失该备份完成后产生的业务数据，必须由业务负责人确认。

## 11. 已知限制

- 单机损坏会造成服务中断，RTO 依赖服务器、镜像和备份可用性。
- PostgreSQL 仅做逻辑全量备份，V1.0 未配置 WAL/PITR。
- MinIO 是单节点，未提供纠删码或跨区域复制。
- Redis 不恢复；恢复后登录短状态、限流计数、Celery 队列/结果会重置。
- 备份目录默认未由脚本加密，必须放在加密磁盘，并复制到加密的主机外存储。
- 应用密钥轮换、数据库高可用、零停机升级和 Kubernetes 不属于 V1.0 单机交付。
