# AI 客服平台 V1.0 开发与验收计划

## 1. 第一版定义

V1.0 不是完整客服 SaaS，也不是通用 Agent 编排平台。它是一个与商城、博客等具体业务系统解耦的多租户 AI 客服核心版，用来证明平台核心能力可以独立运行、测试和部署。

第一版必须完成以下闭环：

```text
平台创建两个相互隔离的演示租户
  -> 在后台配置可用模型
  -> 创建并绑定租户知识库
  -> 中立示例网站接入 Widget
  -> 用户在英文与简体中文之间切换
  -> 用户进行知识问答
  -> AI 返回带来源的回答或明确拒答
  -> 复杂问题转人工客服
  -> 管理员查看会话、用量和问题数据
```

V1.0 不接入 `go-mall` 或博客。两个演示租户使用不同知识库和应用凭据，用于验证平台没有写死业务领域并且租户隔离有效。博客知识源在 V1.1 验收，商城实时查询工具在 V1.2 验收。

预计单人开发时间为 25 个有效工作日，约 5 周。时间是估算，是否完成只根据验收标准判断。

## 2. 产品目标

### 2.1 用户目标

- 接入方开发者可以只依据文档，在 30 分钟内把基础 Widget 接入一个中立 Web 页面。
- 租户管理员可以在后台完成应用、模型、知识库和客服成员的基础配置。
- 租户管理员、客服和最终用户可以在英文与简体中文之间切换，刷新页面后保持选择。
- 最终用户可以获得有来源、可拒答、可转人工的客服回复。
- 人工客服能够看到历史对话和 AI 摘要，接管后 AI 停止自动回复。
- 两个演示租户的数据、凭据、知识库、会话和用量完全隔离。

### 2.2 版本验收边界

V1.0 是否完成只由本文件第 9 至 11 节的技术验收决定。以下工作可以并行进行，但不计入 V1.0 完成条件：

- 访谈至少 5 个可能使用 AI 客服的电商或 SaaS 团队。
- 获得真实项目的试用意愿。
- 至少 1 个试用方明确接受某个付费方案、实施费用或私有部署报价。
- 记录试用方当前每月咨询量、重复问题比例、人工响应时间和可接受预算。

这些结果属于产品决策门禁，只决定是否值得进入商业化版本，不得用来替代或否定已通过的版本技术验收。各版本范围和验收见 [`version-roadmap.md`](version-roadmap.md)。

## 3. 第一版范围

### 3.1 必须完成

#### 多租户与接入

- Tenant、Application 和应用凭据。
- `platform_admin`、`tenant_admin`、`agent` 三种固定角色。
- 通过初始化命令创建首个平台管理员，由平台管理员创建和停用租户；第一版不开放匿名注册租户。
- 接入方后端换取短期 Customer Token。
- 所有业务数据、缓存、任务、对象路径和向量检索按租户隔离。
- 应用允许来源域名和基础速率限制。

#### 模型与对话

- Fake Chat Provider 和 Fake Embedding Provider。
- OpenAI-compatible Chat Provider 和 Embedding Provider，兼容可配置 Base URL 和模型名。
- 平台托管账号和租户 BYOK 使用同一 Provider 协议。
- 后台添加配置、测试连通性、激活和停用。
- 创建会话、读取消息和 SSE 流式回复。
- 模型调用的 Token、耗时、状态和费用估算。

第一版只允许每个应用配置一个活动对话模型。每个知识库固定一个 Embedding 模型、维度和版本，V1.0
不允许原地切换；需要更换时新建知识库、重新入库并切换应用绑定，确认后再停用旧库。后续若增加原地切换，必须通过可恢复的重建索引任务完成。第一版不实现主备模型自动路由、复杂发布版本和无感回滚。

#### 知识库与 RAG

- 每个租户可以创建多个知识库并绑定到应用。
- 支持上传 UTF-8 TXT、Markdown 和可提取文本的 PDF。
- 文档异步解析、清洗、分块、Embedding 和版本化。
- PostgreSQL + pgvector 向量检索。
- 中文关键词检索和向量检索的混合召回。
- 结果融合、引用、低证据拒答和转人工建议。
- 文档更新、停用和删除后旧索引失效。
- 固定评估集和评估报告。

#### 人工接管

- 用户主动申请转人工。
- AI 自动触发转人工建议。
- FIFO 待接管列表、客服接受、回复和关闭。
- 数据库锁或等价机制防止两名客服同时接受。
- 人工模式下禁止 AI 自动发送回复。
- 接管时生成可核对的会话摘要。

#### 接入界面

- JavaScript SDK。
- 可嵌入 Web Widget，支持桌面和移动宽度。
- 管理后台、客服工作台、中立示例站点和 Widget 支持英文与简体中文切换。
- Widget 所选语言传递到消息请求，规则回复和模型回答使用所选语言；未指定语言时兼容既有英文接入。
- 最小管理后台：平台租户、登录、应用、模型、知识库、文档、成员、用量。
- 最小客服工作台：待接管列表、会话详情、回复、关闭。
- 接入示例和生成的 OpenAPI 文档。

#### 运行与部署

- Docker Compose 启动 API、Worker、PostgreSQL、Redis 和 MinIO。
- Alembic migration、结构化日志、健康检查和请求 ID。
- CI 执行静态检查、自动化测试、迁移检查、OpenAPI Diff 和 Secret 扫描。
- 一份本地启动文档和一份单机生产部署文档。

### 3.2 第一版明确不做

- 微信、WhatsApp、邮件、电话和社交媒体渠道。
- OCR、扫描 PDF、复杂表格和图片知识理解。
- 自动退款、取消订单、修改地址等写操作。
- 完整工单、SLA、技能组、自动分配和客服绩效系统。
- 可视化工作流和任意 Agent 编排。
- 多模型自动路由、模型竞价和复杂故障切换。
- SSO、企业组织架构、细粒度自定义 RBAC。
- Webhook 管理平台和连接器市场。
- 自动订阅、在线支付、发票和复杂账单。
- 博客文章、CMS 或其他业务内容源的自动同步；该能力进入 V1.1。
- 实时业务工具、商城商品/订单查询和 `go-mall` 接入；该能力进入 V1.2。
- OpenAPI 自动导入、MCP 适配和连接器市场；该能力进入 V1.3。
- 向量数据库集群、微服务、Kubernetes 和多地域部署。
- 模型微调、自研 Embedding 或自研 Reranker。

## 4. 第一版技术决策

| 分类 | 选择 | 第一版原因 |
| --- | --- | --- |
| Python | Python 3.12+、`uv`、`pyproject.toml` | 依赖和环境统一 |
| API | FastAPI、Pydantic 2 | 类型校验和 OpenAPI |
| ORM | SQLAlchemy 2 Async | API 异步 IO |
| Migration | Alembic | Schema 可追踪 |
| 数据库 | PostgreSQL + pgvector | 业务数据和向量统一维护 |
| 缓存 | Redis | 限流、短期状态、任务 Broker |
| Worker | Celery + Redis | 文档处理和离线任务可靠执行 |
| 对象存储 | S3 接口，本地使用 MinIO | 本地和云端统一协议 |
| 模型接入 | Fake + OpenAI-compatible Chat/Embedding Provider | 分离对话与向量能力，用统一协议覆盖首批供应商 |
| HTTP | HTTPX Async | 模型调用和受控外部资源下载 |
| 后端测试 | pytest、pytest-asyncio | 单元和集成测试 |
| 质量 | Ruff、mypy | 格式、Lint 和类型检查 |
| 管理端 | React + TypeScript + Vite | 与现有商城管理端技术一致 |
| Widget | TypeScript + Vite | 可独立打包和嵌入 |
| 前端测试 | Vitest + Playwright | 组件和核心 E2E |

FastAPI/Pydantic 生成的 OpenAPI 是单一事实来源。仓库保存导出的 OpenAPI 快照用于 Diff 和生成 SDK，不手工维护另一份平行接口定义。

## 5. 最小数据模型

第一版只建立支撑闭环的模型：

| 领域 | 模型 |
| --- | --- |
| 租户 | `Tenant`、`Application`、`ApiCredential` |
| 员工 | `StaffUser`、`TenantMembership` |
| 模型 | `AIProviderAccount`、`AIModelConfig`，通过 `purpose` 区分 Chat 和 Embedding |
| 对话 | `EndUser`、`Conversation`、`Message`、`Citation` |
| 知识库 | `KnowledgeBase`、`KnowledgeBaseBinding`、`KnowledgeDocument`、`KnowledgeChunk`、`IngestionJob` |
| 人工 | `HandoffRequest` |
| 用量 | `AIUsageRecord`、`AuditLog` |

以下模型推迟：`Integration`、`ContentSource`、`SyncJob`、`ToolDefinition`、`ToolBinding`、`ToolInvocation`、`SupportTicket`、`WebhookEndpoint`、`WebhookDelivery`、自定义角色表、模型路由策略、配置发布版本、复杂套餐账单。

除 `Tenant` 自身和明确的平台级账号外，第一版所有租户拥有的业务模型都保存 `tenant_id`。平台/租户共用模型使用 `scope`、可空 `tenant_id` 和 Check Constraint 保证归属合法。即使部分租户可以通过父表 Join 推导，也保留直接租户字段，以便权限查询、索引、审计和隔离测试保持明确。

## 6. 第一版 API 边界

### 6.1 平台、管理认证和应用

```http
POST   /v1/platform/tenants
GET    /v1/platform/tenants
PATCH  /v1/platform/tenants/{id}
POST   /v1/platform/tenants/{id}/admins
POST   /v1/admin/auth/login
POST   /v1/admin/auth/change-password
GET    /v1/admin/me
POST   /v1/admin/applications
GET    /v1/admin/applications
PATCH  /v1/admin/applications/{id}
POST   /v1/admin/applications/{id}/credentials
GET    /v1/admin/applications/{id}/credentials
DELETE /v1/admin/applications/{id}/credentials/{credential_id}
POST   /v1/admin/members
GET    /v1/admin/members
PATCH  /v1/admin/members/{membership_id}
POST   /v1/customer-tokens
```

### 6.2 模型配置

```http
POST   /v1/admin/ai/provider-accounts
GET    /v1/admin/ai/provider-accounts
POST   /v1/admin/ai/provider-accounts/{id}/test
POST   /v1/admin/ai/model-configs
GET    /v1/admin/ai/model-configs
POST   /v1/admin/ai/model-configs/{id}/activate
POST   /v1/admin/ai/model-configs/{id}/deactivate
```

### 6.3 知识库

```http
POST   /v1/admin/knowledge-bases
GET    /v1/admin/knowledge-bases
PATCH  /v1/admin/knowledge-bases/{id}
POST   /v1/admin/knowledge-bases/{id}/documents
GET    /v1/admin/knowledge-bases/{id}/documents
GET    /v1/admin/knowledge-bases/{id}/documents/{document_id}
POST   /v1/admin/knowledge-bases/{id}/documents/{document_id}/retry
DELETE /v1/admin/knowledge-bases/{id}/documents/{document_id}
PUT    /v1/admin/knowledge-bases/{id}/applications/{application_id}
DELETE /v1/admin/knowledge-bases/{id}/applications/{application_id}
GET    /v1/admin/knowledge-bases/{id}/applications
POST   /v1/admin/knowledge-bases/{id}/search
```

### 6.4 对话

```http
POST /v1/chat/sessions
GET  /v1/chat/sessions/{id}
GET  /v1/chat/sessions/{id}/messages
GET  /v1/chat/sessions/{id}/citations/{citation_id}/source
POST /v1/chat/sessions/{id}/messages
POST /v1/chat/sessions/{id}/handoff
GET  /v1/chat/sessions/{id}/handoff
POST /v1/chat/sessions/{id}/human-messages
POST /v1/chat/sessions/{id}/feedback
```

`POST /messages` 使用 Fetch Streaming 消费 SSE，不依赖浏览器只支持 GET 的原生 `EventSource`。

### 6.5 人工客服

```http
GET  /v1/admin/handoffs
POST /v1/admin/handoffs/{id}/accept
GET  /v1/admin/handoffs/{id}/messages
POST /v1/admin/handoffs/{id}/messages
POST /v1/admin/handoffs/{id}/close
```

### 6.6 用量

```http
GET /v1/admin/usage/summary
GET /v1/admin/usage/model-calls
GET /v1/admin/audit-logs
GET /v1/admin/feedback
```

## 7. RAG 实现方案

### 7.1 入库

```text
上传文件
  -> 校验租户、类型、大小和配额
  -> 保存原文件和 KnowledgeDocument
  -> 投递幂等 IngestionJob
  -> 提取文本
  -> 规范化和去重
  -> 按标题、列表和段落结构分块
  -> 生成关键词检索文本
  -> 生成 Embedding
  -> 原子发布新文档版本
```

第一版分块初始参数：

- 目标大小 300 到 600 tokens。
- 相邻块重叠约 10%。
- 标题、章节路径和来源信息附加到每个块。
- FAQ 的问题和答案保持在同一块。
- 表格按行或逻辑区域处理，不能直接按固定字符切断。

这些只是初始值，必须根据评估集调整，不作为所有租户永久固定配置。

### 7.2 索引

每个 Chunk 至少保存：

```text
tenant_id
knowledge_base_id
document_id
document_version
content
heading_path
source_url_or_file
content_hash
embedding_model
embedding_version
embedding_dimension
chunking_version
lexical_text
status
```

关键词索引使用应用层中文分词后的 `lexical_text` 和 PostgreSQL `tsvector`。商品型号、错误码和政策名称等精确字段同时保留为 metadata，避免仅依赖语义相似度。

### 7.3 检索

```text
用户问题
  -> 从认证上下文取得 tenant_id 和 application_id
  -> 解析应用已绑定知识库
  -> 查询规范化
  -> 向量召回 Top 20
  -> 关键词召回 Top 20
  -> RRF 融合和去重
  -> 可选 Rerank
  -> 选择 3 到 6 个证据块
  -> 证据门控
  -> 生成回答或拒答
```

- 所有召回查询在数据库层包含租户、知识库绑定、文档状态和版本过滤。
- 不使用一个固定相似度阈值假装适合所有模型，阈值通过评估集标定。
- 第一版默认不启用 Reranker；只有评估结果有明确提升时才开启。
- 引用保存文档、Chunk、版本、片段和检索分数，返回给用户的引用必须能定位原文。

### 7.4 生成和拒答

模型输入明确区分系统规则、用户问题和不可信知识片段。回答策略：

- 证据充分且一致：根据证据回答并引用。
- 证据不足：明确说明知识库没有可靠答案。
- 证据冲突：说明存在冲突并建议人工确认。
- 涉及知识库之外的动态业务数据：明确说明当前无法可靠查询，并建议转人工，不使用文档猜测。
- 涉及退款、投诉和敏感写操作：转人工。

## 8. 五周开发计划

### 第 1 周：工程基础、多租户和认证

#### 完成内容

- 初始化 `uv`、FastAPI、SQLAlchemy、Alembic、pytest、Ruff 和 mypy。
- Docker Compose 启动 PostgreSQL/pgvector、Redis 和 MinIO。
- 建立模块化单体目录、统一配置、日志、错误处理和健康检查。
- 创建 Tenant、Application、Credential、StaffUser 和 Membership。
- 增加首个平台管理员初始化命令和平台租户管理 API。
- 实现管理员登录、应用管理、API Credential 和 Customer Token。
- 建立 OpenAPI 快照、CI 和 Fake Provider 骨架。

#### 阶段完成检查

- 一条命令启动本地全部依赖。
- 首个平台管理员可以创建、停用和重新启用租户。
- 两个租户可以创建同名应用。
- 使用租户 A 凭据无法读取或修改租户 B 的应用。
- 浏览器端拿不到应用 Secret。
- Alembic 在空库和升级路径均能执行。

### 第 2 周：模型配置、会话和流式输出

#### 完成内容

- Chat/Embedding Provider 接口、对应 Fake Provider 和 OpenAI-compatible Provider。
- 供应商账号加密保存、脱敏展示、连通性测试和激活。
- Conversation、Message 和 AIUsageRecord。
- 创建会话、消息历史和 Fetch Streaming SSE。
- 请求幂等、客户端断开处理、超时和基础限流。
- 管理后台的登录、应用和模型配置页面。

#### 阶段完成检查

- Fake Provider E2E 可以稳定输出完整 SSE 事件序列。
- 管理员不修改 YAML、不重启服务即可激活已测试模型。
- 新知识库绑定活动 Embedding 配置后才能开始入库，模型版本变化不会混用旧向量。
- 数据库、日志和 API 均不出现完整模型 API Key。
- 重复幂等请求只生成一条 AI 消息。
- 客户端断开后消息不会永久停留在 `generating`。

### 第 3 周：知识库和可评估 RAG

#### 完成内容

- KnowledgeBase、Binding、Document、Chunk 和 IngestionJob。
- TXT、Markdown、文本 PDF 上传和对象存储。
- Celery 文档解析、分块、Embedding 和索引任务。
- pgvector 向量召回、中文关键词召回和 RRF 融合。
- 引用、证据门控、拒答和文档版本切换。
- 知识库管理页面和检索调试页面。
- 建立第一批至少 100 条评估数据。

#### 阶段完成检查

- 文档上传后可观察每个处理阶段和失败原因。
- 更新文档后旧版本不再参与检索。
- 所有知识回答包含可打开的来源。
- 跨租户和未绑定知识库检索均返回零结果。
- 基础评估达到第 10 节的最低指标。

### 第 4 周：人工接管、管理端和 Widget

#### 完成内容

- HandoffRequest、人工接管状态机和会话摘要。
- 用户申请转人工、待接管队列、原子接受、人工回复和关闭。
- 可核对的提取式会话摘要和人工模式状态机。
- 最小客服工作台。
- JavaScript SDK 和可嵌入 Widget。
- 管理后台、客服工作台、中立示例站点和 Widget 的英文/简体中文切换及语言持久化。
- 登录用户 Token 初始化、匿名访客限制和来源域名校验。

#### 阶段完成检查

- 两名客服不能同时接受同一个 Handoff。
- 人工接管期间 AI 自动回复数量为零。
- PC 和 375px 移动宽度都可以完成对话、查看引用和申请转人工。
- PC 和 375px 移动宽度都可以切换英文/简体中文，界面无重叠且规则回复使用所选语言。
- 浏览器只获得短期 Customer Token，不出现应用 Secret。
- 接管、回复和关闭操作均有租户、客服和会话审计记录。

### 第 5 周：中立示例与版本开发收口

#### 完成内容

- 管理端用量摘要和问题反馈入口。
- 创建两个知识内容不同的演示租户和中立接入示例。
- 补齐 E2E、安全、隔离、性能、恢复检查工具和部署文档。
- 完成固定 RAG 数据集、运行器和独立人工复核工作表工具。
- 对照第 3、6、9 至 12 节逐项确认开发范围，没有未实现接口、页面、脚本或文档。
- 冻结待验收 Commit 和构建产物，停止在该版本中加入新功能。

#### 阶段完成检查

- 一个新示例站点在 30 分钟内完成基础接入。
- PC 和移动宽度下完成对话、引用和转人工流程。
- 两个演示租户不修改平台核心代码即可独立接入，并且跨租户访问成功数为零。
- 第 10 节的每项指标都有可重复执行的测试、脚本或人工检查步骤。
- 第 11 节的每项发布门禁都有明确证据来源，V1.0 可以进入正式版本验收。

本周结束只表示“V1.0 开发范围已经完成并可验收”，不表示版本已经验收通过，不创建
`docs/acceptance/v1.0.md`，也不发布 Tag。

### V1.0 开发完成后：整版正式验收

只有第 1 至第 5 周承诺的开发范围全部完成并冻结后，才开始正式验收：

1. 固定 Git Commit、构建产物和验收环境，后续修复必须形成新的待验收 Commit。
2. 一次性执行第 9 节完整测试矩阵、第 10 节量化验收和第 11 节发布门禁。
3. 使用真实 OpenAI-compatible 模型执行发布前 Smoke Test，并由独立评审人完成至少 30 条人工复核。
4. 在最终部署环境执行并发、Worker 中断恢复、备份、恢复和回滚演练。
5. 把真实结果写入 `docs/acceptance/v1.0.md`；任一门禁不通过则结论为“不通过”，修复后重新验收受影响项和必要回归项。
6. 全部通过后才能把 V1.0 标记为完成并发布 `v1.0.0` Tag。

开发期间取得的单元测试、RAG 基线或性能基线可以作为问题发现依据，但不能直接冒充冻结版本在正式环境中的
验收结果。

## 9. 测试计划

| 测试层 | 必测内容 | 执行时机 |
| --- | --- | --- |
| 单元测试 | 状态机、权限、分块、RRF、证据门控、费用 | 开发中和 CI |
| Repository 集成 | PostgreSQL、pgvector、事务、索引、唯一约束 | CI |
| Redis/Worker 集成 | 幂等任务、重试、缓存隔离、失败恢复 | CI |
| API 契约 | OpenAPI、Problem Details、幂等、分页、SSE 顺序 | CI |
| Provider 契约 | Fake 和 OpenAI-compatible 行为一致性 | CI 使用 Fake；真实模型手动 |
| 多租户隔离 | API、DB、Redis、对象存储、任务、向量检索 | CI，发布强制 |
| E2E | Widget、RAG 引用、拒答、人工接管、英文/简体中文切换 | 里程碑和发布前 |
| 安全 | SSRF、上传限制、Prompt 注入、Secret 泄漏 | 发布前 |
| 性能 | 检索、并发 SSE、Worker 积压和恢复 | 发布前 |

普通 CI 不调用收费模型。发布前手动运行少量真实模型 Smoke Test，并记录供应商、模型、时间和结果。

## 10. 量化验收标准

### 10.1 RAG 数据集

发布前评估集不少于 150 条：

| 类型 | 最少数量 |
| --- | ---: |
| 有明确知识答案 | 90 |
| 知识库没有答案，必须拒答 | 30 |
| 文档冲突或过期 | 10 |
| 必须转人工 | 10 |
| Prompt 注入或越权 | 10 |

每条数据保存问题、租户、应用、预期来源、关键事实、是否应拒答、是否应转人工和风险等级。

### 10.2 AI 和 RAG 指标

| 指标 | 第一版门槛 |
| --- | ---: |
| 正确来源 `Recall@20` | `>= 90%` |
| 正确来源 `Hit@5` | `>= 85%` |
| 回答关键事实正确率 | `>= 90%` |
| 引用能够支持回答 | `>= 95%` |
| 无答案正确拒答率 | `>= 95%` |
| 应转人工识别率 | `>= 95%` |
| 严重错误回答 | `0` |

严重错误包括编造业务处理结果、错误承诺金额、泄漏其他租户或用户数据，以及把知识库中不存在的内容表述为确定事实。

自动评估用于回归，发布报告至少人工复核 30 条，并记录不一致案例。不能只使用同一个被测模型给自己评分。

### 10.3 安全和隔离指标

- 跨租户 API、数据库、缓存、文件和向量访问成功数为 `0`。
- Git、日志、错误响应和 OpenAPI 示例中的真实 Secret 数为 `0`。
- 人工接管期间 AI 自动回复数为 `0`。

### 10.4 性能基线

性能基线在约 10,000 个 Chunk 的测试库上执行：

- 混合检索 P95 小于 500ms。
- 不包含模型耗时的普通 API P95 小于 300ms。
- 20 个并发 SSE 会话没有消息串流、状态错乱或连接泄漏。
- 选定测试模型的首 Token P95 目标小于 5 秒，若供应商网络无法达到必须记录原因。
- Worker 进程重启后未完成的幂等任务可以继续或安全重试。

性能目标是单机试点基线，不代表企业 SLA。

### 10.5 接入验收

- 接入文档从零操作一次，全程不依赖开发者口头说明。
- 新 Web 页面在 30 分钟内显示 Widget 并完成一次对话。
- Secret 仅存在接入方后端，浏览器只获得短期 Customer Token。
- Widget 可在桌面和 375px 宽度移动视口正常使用。
- 管理后台、客服工作台、中立示例站点和 Widget 的英文/简体中文静态文案均有覆盖；语言选择在刷新后保留。
- Widget 使用 `language="zh-CN"` 或界面切换中文后，消息请求携带 `zh-CN`，规则拒答返回简体中文。
- 第二租户接入不需要修改客服平台核心代码。

## 11. 发布门禁

以下任一项不满足，不发布第一版：

- Ruff、mypy、后端测试、前端类型检查和核心 E2E 通过。
- Alembic 空库迁移和上一版本升级测试通过。
- OpenAPI 快照无未说明的破坏性变化。
- 多租户隔离、认证和权限测试全部通过。
- RAG 指标达到最低门槛，没有严重错误回答。
- 没有真实密钥、客户文件或生产会话进入 Git。
- 生产关闭 Debug、默认密码和匿名管理入口。
- 数据库与对象存储完成备份和恢复演练。
- 有部署、升级、回滚和已知限制说明。
- 两个独立演示租户的 E2E 均通过。
- 英文和简体中文的管理端、示例站点与 Widget 核心 E2E 均通过。

## 12. 第一版交付物

- 可运行的 FastAPI API 和 Celery Worker。
- PostgreSQL/pgvector、Redis 和 MinIO 本地环境。
- 支持英文/简体中文切换的最小管理后台、客服工作台、JavaScript SDK 和 Widget。
- OpenAPI 快照与接入示例。
- 中立示例站点和最小接入示例。
- 两租户隔离测试报告。
- RAG 评估数据集、基线结果和已知失败案例。
- 单机部署、备份、恢复和回滚文档。
- V1.0 版本验收记录，包含版本号、Commit、环境、测试命令、结果、指标、已知限制和发布结论。

## 13. 第一版之后的决策

V1.0 通过本文件验收后即视为该版本完成。是否启动后续版本再根据产品优先级和真实数据决定：

- 如果知识问答准确但接入困难，优先改进 SDK、Widget 和文档。
- 如果检索召回不足，先优化文档清洗、混合检索和评估，再增加 Reranker。
- 如果需要先接入内容站点，进入 V1.1，建设通用内容源并接入博客。
- 如果客户主要需要业务实时查询，进入 V1.2，建设只读工具连接器和权限体系。
- 如果人工接管需求强，扩展队列、技能组、SLA 和工单。
- 如果至少有稳定付费试点，再开发套餐、计费、Webhook 和企业功能。
- 如果免费产品已经满足目标用户且没有付费意愿，停止通用 SaaS 扩张，保留为商城内部能力或垂直交付工具。
