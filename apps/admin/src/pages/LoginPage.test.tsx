import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import LoginPage from './LoginPage';
import { I18nProvider, LANGUAGE_STORAGE_KEY } from '@/i18n/I18nProvider';

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@/auth/AuthProvider', () => ({
  useAuth: () => ({ checking: false, login: mocks.login, user: null }),
}));

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mocks.navigate,
}));

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.login.mockReset();
    mocks.navigate.mockReset();
    mocks.login.mockResolvedValue(undefined);
    mocks.navigate.mockResolvedValue(undefined);
  });

  afterEach(cleanup);

  it('submits staff credentials and tenant context', async () => {
    const user = userEvent.setup();
    render(<I18nProvider><LoginPage /></I18nProvider>);

    expect(screen.getByRole('heading', { name: 'Support Console' })).toBeVisible();
    await user.type(screen.getByRole('textbox', { name: 'Email' }), 'agent@example.test');
    await user.type(screen.getByLabelText(/^Password/), 'correct-password');
    await user.type(screen.getByRole('textbox', { name: 'Tenant ID' }), 'tenant-1');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(mocks.login).toHaveBeenCalledWith({
      email: 'agent@example.test',
      password: 'correct-password',
      tenantId: 'tenant-1',
    });
    expect(mocks.navigate).toHaveBeenCalledWith({ to: '/' });
  });

  it('renders an accessible error and re-enables submission after login fails', async () => {
    mocks.login.mockRejectedValue(new Error('Invalid credentials'));
    const user = userEvent.setup();
    render(<I18nProvider><LoginPage /></I18nProvider>);

    await user.type(screen.getByRole('textbox', { name: 'Email' }), 'agent@example.test');
    await user.type(screen.getByLabelText(/^Password/), 'wrong-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it('switches to Simplified Chinese and persists the language', async () => {
    const user = userEvent.setup();
    render(<I18nProvider><LoginPage /></I18nProvider>);

    await user.click(screen.getByRole('button', { name: 'Change language' }));
    await user.click(screen.getByRole('menuitem', { name: '简体中文' }));

    expect(screen.getByRole('heading', { name: '客服管理后台' })).toBeVisible();
    expect(screen.getByRole('button', { name: '登录' })).toBeVisible();
    expect(screen.getByRole('textbox', { name: '租户 ID' })).toBeVisible();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('zh-CN');
    expect(document.documentElement.lang).toBe('zh-CN');
  });
});
