import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : 'list',
  outputDir: process.env.CI
    ? 'test-results'
    : '/tmp/ai-customer-service-playwright-results',
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop-chromium',
      testIgnore: /\.mobile\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chromium',
      testMatch: /.*\.mobile\.spec\.ts/,
      use: { ...devices['iPhone 13'] },
    },
  ],
  webServer: [
    {
      command:
        'npm run dev --workspace @ai-support/admin -- --host 127.0.0.1 --strictPort',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      url: 'http://127.0.0.1:5173/login',
    },
    {
      command:
        'npm run dev --workspace @ai-support/demo -- --host 127.0.0.1 --strictPort',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      url: 'http://127.0.0.1:5174',
    },
  ],
});
