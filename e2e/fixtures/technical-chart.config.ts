import { defineConfig } from '@playwright/test';
export default defineConfig({
    testDir: '..', testMatch: 'technical-chart.spec.ts', workers: 1, timeout: 60000,
    use: { baseURL: 'http://127.0.0.1:3100', launchOptions: { executablePath: process.env.E2E_CHROME_PATH || undefined, args: ['--no-sandbox'] } },
    webServer: { command: 'npm run dev -- --hostname 127.0.0.1 --port 3100', cwd: '../..', url: 'http://127.0.0.1:3100/chart-preview', reuseExistingServer: !process.env.CI, timeout: 120000 },
});
