import { expect, test } from '@playwright/test';

test('widget uses full-screen mobile dialog semantics without horizontal overflow', async ({ page }) => {
  await page.route('**/api/support-token', (route) =>
    route.fulfill({ json: { access_token: 'e2e-customer-token' } }),
  );
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/chat/sessions' && request.method() === 'POST') {
      await route.fulfill({
        json: {
          id: 'conversation-mobile',
          application_id: 'demo',
          mode: 'ai',
          status: 'open',
          created_at: '2026-07-17T00:00:00Z',
          updated_at: '2026-07-17T00:00:00Z',
        },
        status: 201,
      });
      return;
    }
    if (path.endsWith('/messages')) {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ json: { code: 'handoff_not_found', detail: 'Not found' }, status: 404 });
  });

  await page.goto('http://127.0.0.1:5174');
  await page.locator('#language-select').selectOption('zh-CN');
  await page.getByRole('button', { name: '打开客服' }).click();
  const dialog = page.getByRole('dialog', { name: 'Northstar 客户支持' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-modal', 'false');

  const measurements = await dialog.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      borderRadius: style.borderRadius,
      height: Math.round(rect.height),
      width: Math.round(rect.width),
      viewportHeight: window.innerHeight,
      viewportWidth: window.innerWidth,
      horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
    };
  });

  expect(measurements.borderRadius).toBe('0px');
  expect(Math.abs(measurements.width - measurements.viewportWidth)).toBeLessThanOrEqual(1);
  expect(Math.abs(measurements.height - measurements.viewportHeight)).toBeLessThanOrEqual(1);
  expect(measurements.horizontalOverflow).toBeLessThanOrEqual(0);
  await expect(page.getByRole('textbox', { name: '消息' })).toBeVisible();
  await expect(page.getByRole('button', { name: '关闭客服' })).toBeVisible();
  await expect(dialog.getByRole('combobox', { name: '语言' })).toHaveValue('zh-CN');
});
