# Widget host example

This small host keeps the application API key on the server and gives the browser only a
short-lived Customer Token.

```bash
npm run build -w @ai-support/demo
export SUPPORT_PLATFORM_URL=http://localhost:8000
export SUPPORT_APPLICATION_API_KEY='acs_...'
export SUPPORT_APPLICATION_ORIGIN=http://localhost:8081
export SUPPORT_DEMO_USER_ID=neutral-demo-user
uv run uvicorn examples.widget_host.main:app --port 8081
```

Open `http://localhost:8081`. The configured origin must also be present in the application's
allowed origins.

`SUPPORT_DEMO_USER_ID` exists only to keep this neutral example runnable. A production host must
remove that setting and derive `external_user_id` from its authenticated server-side user session.
Never accept an arbitrary browser-supplied user ID and never expose the application API key.

The production image also exposes the standalone browser bundle at
`https://<platform-host>/widget/ai-support-widget.js`. Add the customer website origin to the
application's `allowed_origins`, then load the bundle and obtain a short-lived token from the
customer application's own backend:

```html
<ai-support-widget
  id="support-widget"
  base-url="https://support.example.com"
  application-id="storefront-web"
  session-key="current-user-id"
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

The inline example is intentionally small. Production sites with a strict Content Security Policy
should move the initialization into an allowed external JavaScript file. The platform API key must
remain in `/api/support-token` on the integrating server.
