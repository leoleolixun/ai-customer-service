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
