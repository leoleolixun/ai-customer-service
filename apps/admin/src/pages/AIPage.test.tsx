import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AIPage from './AIPage';
import { I18nProvider } from '@/i18n/I18nProvider';

const provider = {
  id: 'provider-1',
  tenant_id: 'tenant-1',
  scope: 'tenant' as const,
  name: 'GLM',
  kind: 'openai_compatible' as const,
  base_url: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
  has_api_key: true,
  can_manage: true,
  status: 'draft' as const,
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
};

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  invalidateQueries: vi.fn(),
}));

vi.mock('@/api/client', () => ({
  api: mocks.api,
  errorMessage: (error: unknown) => error instanceof Error ? error.message : 'Request failed',
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
  useSuspenseQuery: ({ queryKey }: { queryKey: string[] }) => {
    if (queryKey[0] === 'provider-accounts') return { data: [provider] };
    return { data: [] };
  },
}));

describe('AIPage provider management', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.api.mockReset();
    mocks.invalidateQueries.mockReset();
    mocks.api.mockResolvedValue(undefined);
    mocks.invalidateQueries.mockResolvedValue(undefined);
  });

  afterEach(cleanup);

  it('updates the Base URL while keeping the stored API key', async () => {
    const user = userEvent.setup();
    render(<I18nProvider><AIPage /></I18nProvider>);

    await user.click(screen.getByRole('button', { name: 'Edit GLM' }));
    const baseUrl = screen.getByRole('textbox', { name: 'Base URL' });
    await user.clear(baseUrl);
    await user.type(baseUrl, 'https://open.bigmodel.cn/api/paas/v4');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(mocks.api).toHaveBeenCalledWith('/v1/admin/ai/provider-accounts/provider-1', {
      method: 'PATCH',
      body: JSON.stringify({
        name: 'GLM',
        base_url: 'https://open.bigmodel.cn/api/paas/v4',
      }),
    });
  });

  it('requires confirmation before deleting a provider', async () => {
    const user = userEvent.setup();
    render(<I18nProvider><AIPage /></I18nProvider>);

    await user.click(screen.getByRole('button', { name: 'Delete GLM' }));
    expect(screen.getByRole('heading', { name: 'Delete provider account?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Delete provider' }));

    expect(mocks.api).toHaveBeenCalledWith('/v1/admin/ai/provider-accounts/provider-1', {
      method: 'DELETE',
    });
  });
});
