# V1.0 Worker 恢复与幂等检查

## 1. 检查目标

本检查验证：

- Worker 停止时，Redis 中的知识入库任务不会丢失；
- Worker 重新启动后，排队任务可以完成；
- 完成后的同一任务被再次投递时，不增加处理次数，也不重复生成 Chunk；
- Celery 开启 late acknowledgement、Worker 丢失重投和最多 3 次指数退避重试。

## 2. 操作步骤

先停止 Worker，保持 PostgreSQL、Redis、MinIO 和 API 可用，然后入队探针：

```bash
NO_PROXY=localhost,127.0.0.1 \
no_proxy=localhost,127.0.0.1 \
uv run python scripts/worker_recovery_probe.py enqueue \
  --state /tmp/ai-cs-worker-recovery.json
```

确认 Redis 的 `celery` 队列存在待处理消息，再启动 Worker：

```bash
uv run celery -A app.workers.celery_app worker --loglevel=INFO --concurrency=1
```

在另一个终端等待完成，并重复投递同一任务验证幂等：

```bash
NO_PROXY=localhost,127.0.0.1 \
no_proxy=localhost,127.0.0.1 \
uv run python scripts/worker_recovery_probe.py verify \
  --state /tmp/ai-cs-worker-recovery.json \
  --timeout 60 \
  --replay
```

预期 `passed=true`、`idempotent_replay=true`，并且两次快照的 `attempts` 与 `chunk_count` 相同。

## 3. 版本验收边界

这项开发检查证明离线排队和已完成任务重放安全。正式版本验收还应在最终部署环境杀死一个正在执行任务的
Worker 子进程，确认主进程将未确认任务重投，并记录日志、任务 ID 和最终数据库状态。只有当前版本全部
开发完成后，这些结果才写入 V1.0 独立验收记录。
