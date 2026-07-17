import { afterEach, describe, expect, it } from 'vitest';

import { ApiError, errorMessage } from '@/api/client';

describe('errorMessage', () => {
  afterEach(() => {
    document.documentElement.lang = 'en';
  });

  it('uses a stable error code instead of the server detail', () => {
    const error = new ApiError(401, 'invalid_credentials', 'Server detail must not leak');

    expect(errorMessage(error, 'Fallback')).toBe('The email or password is incorrect.');
  });

  it('uses the active Simplified Chinese dictionary', () => {
    document.documentElement.lang = 'zh-CN';
    const error = new ApiError(401, 'invalid_credentials', 'Invalid email or password');

    expect(errorMessage(error, '请求未能完成。')).toBe('邮箱或密码不正确。');
  });

  it('uses the localized fallback for unknown codes and network errors', () => {
    document.documentElement.lang = 'zh-CN';

    expect(errorMessage(new ApiError(500, 'future_error', 'Future detail'), '请求未能完成。'))
      .toBe('请求未能完成。');
    expect(errorMessage(new TypeError('Failed to fetch'), '请求未能完成。'))
      .toBe('请求未能完成。');
  });
});
