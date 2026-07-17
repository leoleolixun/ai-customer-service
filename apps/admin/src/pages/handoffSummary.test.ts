import { describe, expect, it } from 'vitest';

import { localizeHandoffSummary } from '@/pages/handoffSummary';

describe('localizeHandoffSummary', () => {
  it('localizes stable role codes', () => {
    expect(localizeHandoffSummary('user: 需要帮助\nai: 请联系人工客服', {
      customer: '客户',
      ai: 'AI',
    })).toBe('客户: 需要帮助\nAI: 请联系人工客服');
  });

  it('keeps existing summaries compatible and leaves content lines unchanged', () => {
    expect(localizeHandoffSummary('Customer: Need help\nsecond line\nAI: Contact support', {
      customer: 'Customer',
      ai: 'AI',
    })).toBe('Customer: Need help\nsecond line\nAI: Contact support');
  });
});
