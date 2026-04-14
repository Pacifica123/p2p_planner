import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: ['smoke/**/*.smoke.spec.ts'],
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    headless: true,
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
    env: {
      VITE_API_BASE_URL: 'http://127.0.0.1:18080/api/v1',
      VITE_ENABLE_PROJECT_ROADMAP_SEED: 'false',
    },
  },
});
