# AI Customer Service

面向国内电商、内容站点和 SaaS 系统的可复用 AI 客服平台。项目使用 FastAPI 构建，V1.0 聚焦多租户、可引用知识问答、最小人工接管和快速 Widget 接入，不与博客、商城或其他具体业务系统耦合。

## 项目目标

- 业务系统可以通过 REST API、SSE、JavaScript Widget 或服务端 SDK 快速接入。
- 每个租户可以创建和管理自己的多个知识库、文档与检索策略，并按需绑定到一个或多个应用。
- 每个租户拥有独立的应用、密钥、工具、会话、模型策略和用量数据。
- AI 只能通过经过授权和审计的工具访问订单、物流、售后等业务能力。
- 知识库回答提供来源；证据不足时拒绝编造并支持转人工。
- 人工客服能够接管会话，查看 AI 摘要，并在结束后选择是否恢复 AI。
- 模型供应商账号、活动模型和租户自带密钥通过管理后台配置，敏感凭据加密保存。
- 模型、Embedding、对象存储和业务系统均通过适配层接入，避免供应商锁定。

## V1.0 形态

V1.0 是可独立运行和验收的模块化单体，不是完整客服 SaaS：

- FastAPI API 服务
- 独立 Worker
- PostgreSQL + pgvector
- Redis
- S3 兼容对象存储
- Fake Chat/Embedding Provider 和可后台配置的 OpenAI-compatible Provider
- 租户 BYOK、活动对话模型、知识库固定 Embedding 版本和模型调用用量记录
- 向量与中文关键词混合检索、来源引用和无答案拒答
- 最小管理后台、人工客服工作台和 JavaScript Widget
- FastAPI 自动生成并由 CI 检查的 OpenAPI 契约

V1.0 使用两个中立演示租户验证隔离、知识问答、拒答和人工接管。博客内容同步进入 V1.1，商城的 `product.search` 和 `order.get` 只读工具进入 V1.2；平台始终不直接访问商城数据库。主备模型路由、自动计费、完整工单/SLA、多渠道和可视化工作流不进入 V1.0。

## 开发文档

- [项目开发规则](AGENTS.md)
- [版本路线与逐版验收](docs/version-roadmap.md)
- [V1.0 开发计划与验收](docs/v1-development-plan.md)
- [总开发计划](docs/development-plan.md)
- [长期架构蓝图](docs/architecture-blueprint.md)
- [RAG 固定评估集与评估工具](docs/evaluation.md)
- [开发性能基线](docs/performance.md)
- [Worker 恢复检查](docs/worker-recovery.md)
- [单机部署与回滚](docs/deployment.md)
- [备份与恢复](docs/backup-restore.md)

## 本地启动

前置环境：Python 3.12+、`uv`、Node.js 22+、Docker 和 Docker Compose。

```bash
cp .env.example .env
uv sync --all-groups
npm ci
docker compose up -d postgres redis minio minio-init
uv run alembic upgrade head
```

启动后端、Worker、管理端和演示站点：

```bash
# 终端 1
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2
uv run celery -A app.workers.celery_app worker --loglevel=INFO

# 终端 3
npm run dev:admin

# 终端 4
npm run dev:demo
```

默认地址：

- API 文档：`http://localhost:8000/docs`
- 管理端：`http://localhost:5173`
- Widget 演示站：`http://localhost:5174`

生产镜像会把管理端挂载到 `/console/`，并在 `/sdk/` 和 `/widget/` 提供已构建的接入产物；开发模式仍使用
独立 Vite 服务以获得热更新。

创建两个隔离的中立演示租户：

```bash
uv run python scripts/seed_demo.py
```

命令会安全提示输入演示管理员密码。非交互环境可通过受保护的 Secret 管道传入标准输入并增加
`--password-stdin`，不要把密码直接写入命令参数、环境变量或 shell history。命令只在首次创建应用凭据时
输出完整 API Key。不要把命令输出、`.env` 或真实密钥提交到 Git。
如果本机设置了 HTTP 代理，并且 MinIO 使用本地地址，执行命令前设置
`NO_PROXY=localhost,127.0.0.1` 和 `no_proxy=localhost,127.0.0.1`，避免本地对象存储请求被代理转发。

## 开发检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app scripts examples tests
uv run pytest
npm run typecheck
npm run test:frontend
npm run test:e2e
uv run python scripts/check_secrets.py
```

开发中的单项检查和每周阶段检查只用于发现遗漏，不构成版本验收。V1.0 冻结范围全部开发完成后，才按照
[`docs/v1-development-plan.md`](docs/v1-development-plan.md) 第 9 至 11 节执行一次完整版本验收并生成独立记录。

## 当前状态

V1.0 核心功能已经实现，当前处于功能收口和正式验收前准备阶段。后端质量检查、固定评估集、管理端、
客服工作台、SDK、Widget、部署与备份脚本均已建立；真实 PostgreSQL/pgvector 集成、150 条 RAG 开发评估、
1 万分块性能基线和 Worker 离线排队/幂等重放检查已经完成。真实模型联调、独立人工复核、最终部署环境的
并发/恢复演练和整版验收仍需完成。因此当前版本尚未通过正式验收，也尚未发布。
