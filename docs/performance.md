# V1.0 性能与并发基线

## 1. 目的

`scripts/performance_baseline.py` 用于在固定环境中重复检查 V1.0 单机性能目标：

- 约 10,000 个 Chunk 的混合检索 P95 小于 500ms；
- 不包含模型生成的普通管理 API P95 小于 300ms；
- 两个租户交错执行 20 路并发 SSE，不发生消息、会话或引用串流。

脚本生成的性能知识库不会绑定任何应用，因此不会改变演示站点和固定 RAG 数据集的检索结果。

## 2. 前置条件

1. PostgreSQL 及 pgvector、Redis、MinIO 已启动；
2. 已执行 `uv run alembic upgrade head`；
3. 已执行 `scripts/seed_demo.py` 创建 `demo-retail` 和 `demo-saas`；
4. API 正在 `http://127.0.0.1:8000` 运行。

本机设置 HTTP 代理时，应确保 `NO_PROXY` 和 `no_proxy` 包含 `localhost,127.0.0.1`。

## 3. 运行

```bash
NO_PROXY=localhost,127.0.0.1 \
no_proxy=localhost,127.0.0.1 \
uv run python scripts/performance_baseline.py \
  --chunks 10000 \
  --retrieval-requests 100 \
  --api-requests 100 \
  --sse-concurrency 20 \
  --output /tmp/ai-cs-performance.json \
  --enforce
```

第一次运行会创建专用性能知识库和 10,000 个合成 Chunk。后续以相同 `--chunks` 重跑时会复用；数量
不一致时脚本会中止，避免静默删除已有数据。

## 4. 结果解释

输出中的 `passed=true` 只说明本次开发基线达到脚本内门槛。它不等于 V1.0 已完成正式验收。
版本冻结后必须在最终验收环境重新运行，保存主机规格、数据库版本、进程配置、Commit、原始 JSON 和失败
日志，再把结果纳入该版本的独立验收记录。

Fake Provider 只用于排除供应商网络和生成耗时，不能证明真实模型首 Token 延迟。真实 Provider 的少量
Smoke Test 和首 Token P95 必须单独记录。

## 5. 真实 Provider Smoke Test

真实模型验收使用 `scripts/real_provider_smoke.py`。API Key 只从进程环境变量读取，不能放入命令参数、
输出文件或 Git。下面示例执行 10 次流式对话，并以 5 秒首 Token P95 作为门槛：

```bash
(
read -r -s -p "Provider API Key: " AI_CS_PROVIDER_API_KEY
export AI_CS_PROVIDER_API_KEY
printf '\n'
uv run python scripts/real_provider_smoke.py \
  --base-url https://provider.example.com/v1 \
  --chat-model provider-chat-model \
  --samples 10 \
  --first-token-target-ms 5000 \
  --output /tmp/ai-cs-real-provider.json \
  --enforce
)
```

供应商同时提供兼容的 Embedding API 时，增加：

```text
--embedding-model provider-embedding-model --embedding-dimensions 1024
```

脚本先请求 `/models`，再测量每次流式请求的首 Token 和完成耗时；可选 Embedding 检查只记录返回向量数、
维度和数值是否有限。报告不会保存 API Key、回答正文或向量值。发布记录必须注明供应商、模型、运行区域、
样本数和未达到 5 秒目标时的网络或供应商原因。该脚本验证 Provider 协议和供应商延迟，完整平台链路还要
在管理后台激活同一 Chat 模型，并通过 Widget 完成一次带引用问答。
