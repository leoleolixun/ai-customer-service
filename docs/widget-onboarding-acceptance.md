# Widget 30 分钟接入与验收

本文供未参与客服平台开发的接入方使用。V1.0 接入验收从接入方拿到以下四项信息后开始计时，全程只依据
本文操作，不依赖平台开发者口头说明：

- 已部署平台地址，例如 `https://support.example.com`；
- 管理端创建的应用 ID；
- 仅供接入方后端保存的应用 API Key；
- 已加入应用允许来源列表的待接入网站 Origin。

应用 API Key 不得进入 HTML、浏览器 JavaScript、截图或验收 JSON。浏览器只能调用接入方自己的 Token
端点并获得短期 Customer Token。

## 1. 开始计时

在冻结候选的干净 Git 工作区执行。镜像摘要必须使用部署候选的完整 `sha256`：

```bash
uv run python scripts/onboarding_acceptance.py start \
  --reviewer '<独立接入人姓名>' \
  --image-digest 'sha256:<64 位摘要>' \
  --output /tmp/widget-onboarding-start.json
```

该命令记录开始时间、Commit、镜像摘要和接入人，不会保存任何密钥。已有输出不会被覆盖。

## 2. 后端签发短期 Token

在待接入网站后端增加一个仅供已登录用户调用的 `/api/support-token` 路由。以下 FastAPI 示例中的
`current_user.id` 必须来自服务端登录会话，不能接受浏览器提交的任意用户 ID：

```python
import os

import httpx
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get('/api/support-token')
async def support_token(current_user=Depends(require_current_user)):
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{os.environ['SUPPORT_BASE_URL']}/v1/customer-tokens",
            headers={
                'X-API-Key': os.environ['SUPPORT_APPLICATION_API_KEY'],
                'Origin': os.environ['SUPPORT_APPLICATION_ORIGIN'],
            },
            json={'external_user_id': str(current_user.id)},
        )
    response.raise_for_status()
    return response.json()
```

将四项配置放在接入方服务器的 Secret 或环境配置中。不要把 API Key 写进仓库或前端构建变量。

## 3. 网页加载 Widget

把以下代码放在新 Web 页面关闭 `</body>` 标签前。`application-id` 是公开应用 ID，不是 Secret：

```html
<ai-support-widget
  id="support-widget"
  base-url="https://support.example.com"
  application-id="<application UUID>"
  session-key="current-user"
  language="zh-CN"
></ai-support-widget>
<script src="https://support.example.com/widget/ai-support-widget.js"></script>
<script>
  document.querySelector('#support-widget').tokenProvider = async () => {
    const response = await fetch('/api/support-token', { credentials: 'include' });
    if (!response.ok) throw new Error('Support token request failed');
    return (await response.json()).access_token;
  };
</script>
```

生产站点使用严格 CSP 时，把初始化代码移入允许加载的外部 JavaScript 文件，并将平台域名加入
`script-src` 和 `connect-src`。平台应用的允许来源必须精确包含当前页面 Origin。

## 4. 完成对话并保存证据

1. 在桌面浏览器打开新页面，确认 Widget 可见。
2. 切换英文和简体中文并刷新，确认语言选择保留。
3. 发送一个知识库中有答案的问题，确认收到完整回复和引用来源。
4. 在浏览器 Network 中确认只出现短期 Customer Token，没有应用 API Key。
5. 使用 375px 视口确认 Widget 可以打开、输入和查看引用。
6. 记录管理端“会话记录”页面显示的 Conversation UUID，并分别保存桌面和 375px 页面中包含有效回复的
   两张截图。截图不得包含密钥。

## 5. 停止计时并生成报告

网页必须仍可从 `--page-url` 访问。结束命令会下载页面源码和页面引用的 Widget Bundle，验证元素、Bundle
地址及非空响应，扫描常见应用 Secret 痕迹，计算截图摘要，并拒绝超过 30 分钟、候选 Commit 改变或
工作区存在跟踪文件修改的结果：

```bash
uv run python scripts/onboarding_acceptance.py finish \
  --state /tmp/widget-onboarding-start.json \
  --page-url 'https://host.example.com/help' \
  --conversation-id '<完成对话的 UUID>' \
  --desktop-evidence /tmp/widget-conversation-desktop.png \
  --mobile-evidence /tmp/widget-conversation-mobile.png \
  --output /tmp/widget-onboarding-report.json
```

验收负责人随后在管理端按 Conversation UUID 核对消息、引用、应用和租户，并把报告、截图摘要和核对结论
写入冻结候选的版本验收记录。脚本通过只能证明页面结构、候选一致性和计时满足要求，不能替代独立接入人
实际操作，也不能替代管理端会话核对。
