# `@ai-support/sdk`

浏览器端 TypeScript SDK，负责客户会话、SSE 流式回复、引用、反馈和人工接管。业务系统仍应在自己的
服务端使用应用凭证签发短期客户 Token，不能把应用 API Key 发送到浏览器。

## 1. 服务端签发客户 Token

业务后端保存管理端创建的应用凭证，并代替浏览器调用：

```http
POST /v1/customer-tokens
X-API-Key: acs_xxx.secret
Origin: https://shop.example.com
Content-Type: application/json

{"external_user_id":"customer-123"}
```

`external_user_id` 必须是当前业务系统中稳定且不可猜测为其他用户的标识。业务后端只把返回的
`access_token` 和过期时间交给已登录的当前用户。Token 到期后重新向业务后端获取，不在前端保存应用凭证。

## 2. 创建客户端

```ts
import { SupportApiError, SupportClient } from '@ai-support/sdk';

const client = new SupportClient({
  baseUrl: 'https://support.example.com',
  getToken: () => fetch('/api/support-token').then(async (response) => {
    if (!response.ok) throw new Error('support token failed');
    return (await response.json()).access_token;
  }),
  getLocale: () => document.documentElement.lang === 'zh-CN' ? 'zh-CN' : 'en',
});
```

`getToken` 会在每次请求前调用，因此宿主可以自行缓存未过期 Token，并在 401 后刷新。生产环境必须把宿主
Origin 加入应用允许列表，并通过 HTTPS 调用客服服务。

## 3. 会话和历史消息

```ts
const session = await client.createSession();
const latest = await client.listMessages(session.id, { limit: 50 });
const previous = latest.length
  ? await client.listMessages(session.id, { limit: 50, before: latest[0].id })
  : [];
```

消息页按时间正序返回，但默认选择最新一页。`before` 使用当前页第一条消息 ID，继续读取更早消息。宿主可把
会话 ID 保存在当前用户隔离的存储中；切换账号时必须清除，不能在不同用户之间复用。

## 4. SSE 和幂等

```ts
const idempotencyKey = crypto.randomUUID();

for await (const event of client.streamMessage(session.id, '退货期限是多久？', idempotencyKey)) {
  if (event.type === 'message.started') console.log(event.data.message_id);
  if (event.type === 'message.delta') renderDelta(event.data.delta);
  if (event.type === 'message.completed') renderMessage(event.data);
  if (event.type === 'message.error') renderLocalizedError(event.data.code);
}
```

同一次用户提交在网络重试时复用同一幂等键。收到 `idempotent_message_incomplete` 表示原请求仍在处理或已失败，
应先刷新消息历史；只有用户明确重新提交时才生成新键。SSE 事件顺序是 `message.started`、零到多个
`message.delta`、最后一个 `message.completed` 或 `message.error`。

## 5. 引用、反馈和人工接管

```ts
const source = await client.getCitationSource(session.id, citationId);
await client.submitFeedback(session.id, messageId, 'helpful');

const handoff = await client.requestHandoff(session.id, 'customer_requested_handoff');
if (handoff.status === 'pending' || handoff.status === 'accepted') {
  await client.sendHumanMessage(session.id, '我需要人工确认');
}
```

引用文件来自租户已绑定知识库，仍应按不可信内容展示。进入人工模式后停止调用 AI 消息接口，轮询会话历史和
转人工状态，直到人工会话关闭。

## 6. 错误处理

```ts
try {
  await client.getSession(sessionId);
} catch (error) {
  if (error instanceof SupportApiError) {
    console.error(error.status, error.code, error.requestId);
  }
}
```

界面应按稳定的 `code` 做本地化，不直接向最终用户显示服务端英文 `message`。日志可以记录 `requestId`，但不得
记录客户 Token、应用凭证、Provider API Key 或完整敏感对话。
