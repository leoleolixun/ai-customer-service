import { expect, test } from '@playwright/test';

const now = '2026-07-17T08:00:00Z';

test('knowledge version lifecycle prevents conflicting restores', async ({ page }) => {
  const documents = [
    {
      id: 'document-v1',
      knowledge_base_id: 'base-1',
      supersedes_document_id: null,
      version: 1,
      title: 'Old policy',
      source_filename: 'policy-v1.md',
      source_url: null,
      mime_type: 'text/markdown',
      byte_size: 100,
      content_hash: 'a'.repeat(64),
      status: 'disabled',
      error_message: null,
      can_restore: false,
      restore_block_reason: 'document_restore_version_conflict',
      created_at: now,
      updated_at: now,
    },
    {
      id: 'document-v3',
      knowledge_base_id: 'base-1',
      supersedes_document_id: 'document-v2',
      version: 3,
      title: 'New policy',
      source_filename: 'policy-v2.md',
      source_url: null,
      mime_type: 'text/markdown',
      byte_size: 120,
      content_hash: 'b'.repeat(64),
      status: 'ready',
      error_message: null,
      can_restore: false,
      restore_block_reason: null,
      created_at: now,
      updated_at: now,
    },
  ];

  await page.addInitScript(() => {
    localStorage.setItem('support-admin-token', 'knowledge-admin-token');
    localStorage.setItem('ai-support.language', 'en');
  });
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: 'knowledge-admin',
          email: 'knowledge-admin@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-1',
          role: 'tenant_admin',
        },
      });
      return;
    }
    if (path === '/v1/admin/knowledge-bases') {
      await route.fulfill({
        json: [{
          id: 'base-1',
          name: 'Policies',
          description: 'Customer policies',
          embedding_model_config_id: 'model-1',
          embedding_model_name: 'fake-embedding',
          embedding_dimension: 32,
          embedding_version: 'v1',
          chunking_version: 'v1',
          keyword_score_threshold: 0.15,
          vector_similarity_threshold: 0.72,
          status: 'active',
          created_at: now,
          updated_at: now,
        }],
      });
      return;
    }
    if (path === '/v1/admin/ai/model-configs') {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === '/v1/admin/applications' || path.endsWith('/applications')) {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === '/v1/admin/knowledge-bases/base-1/documents') {
      await route.fulfill({ json: documents });
      return;
    }
    const statusMatch = path.match(/\/documents\/(document-v[13])\/status$/);
    if (request.method() === 'PATCH' && statusMatch) {
      const body = request.postDataJSON() as { status: 'ready' | 'disabled' };
      const document = documents.find((item) => item.id === statusMatch[1]);
      if (document) {
        document.status = body.status;
        document.can_restore = body.status === 'disabled';
        document.restore_block_reason = null;
      }
      const oldVersion = documents.find((item) => item.id === 'document-v1');
      if (oldVersion && statusMatch[1] === 'document-v3' && body.status === 'disabled') {
        oldVersion.can_restore = true;
        oldVersion.restore_block_reason = null;
      }
      await route.fulfill({ json: document });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/knowledge');
  await expect(page.getByRole('heading', { name: 'Knowledge' })).toBeVisible();

  const restoreOld = page.getByRole('button', { name: 'Restore Old policy' });
  await expect(restoreOld).toBeDisabled();
  await page.getByRole('button', { name: 'Disable New policy' }).click();
  await expect(restoreOld).toBeEnabled();
  await restoreOld.click();

  await expect(page.getByRole('row', { name: /Old policy/ }).getByText('Ready')).toBeVisible();
});

test('knowledge load failures do not appear as empty writable state', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('support-admin-token', 'knowledge-admin-token');
    localStorage.setItem('ai-support.language', 'en');
  });
  await page.route('**/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: 'knowledge-admin',
          email: 'knowledge-admin@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-1',
          role: 'tenant_admin',
        },
      });
      return;
    }
    if (path === '/v1/admin/knowledge-bases') {
      await route.fulfill({
        json: [{
          id: 'base-1',
          name: 'Policies',
          description: 'Customer policies',
          embedding_model_config_id: 'model-1',
          embedding_model_name: 'fake-embedding',
          embedding_dimension: 32,
          embedding_version: 'v1',
          chunking_version: 'v1',
          keyword_score_threshold: 0.15,
          vector_similarity_threshold: 0.72,
          status: 'active',
          created_at: now,
          updated_at: now,
        }],
      });
      return;
    }
    if (path === '/v1/admin/ai/model-configs') {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === '/v1/admin/applications') {
      await route.fulfill({
        json: [{
          id: 'application-1',
          tenant_id: 'tenant-1',
          name: 'Storefront',
          public_key: 'pk_storefront',
          allowed_origins: [],
          rate_limit_per_minute: 60,
          status: 'active',
          created_at: now,
          updated_at: now,
        }],
      });
      return;
    }
    if (
      path === '/v1/admin/knowledge-bases/base-1/documents'
      || path === '/v1/admin/knowledge-bases/base-1/applications'
    ) {
      await route.fulfill({
        status: 400,
        json: { code: 'future_error', detail: 'Internal detail must not be shown.' },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/knowledge');

  await expect(page.getByText('Documents could not be loaded.')).toBeVisible();
  await expect(page.getByText('Application bindings could not be loaded.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Bind app' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Upload' })).toBeDisabled();
  await expect(page.getByText('None', { exact: true })).toHaveCount(0);
});
