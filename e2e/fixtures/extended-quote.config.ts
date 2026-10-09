import { defineConfig } from '@playwright/test';
export default defineConfig({
    testDir: '..', testMatch: 'extended-quote.spec.ts', workers: 1, timeout: 60000,
    use: { baseURL: 'http://127.0.0.1:3101', launchOptions: { executablePath: process.env.E2E_CHROME_PATH || '/usr/bin/google-chrome', args: ['--no-sandbox'] } },
    webServer: { command: 'npm run dev -- --hostname 127.0.0.1 --port 3101', cwd: '../..', env: { APP_ENV: 'test', E2E_AUTH_BYPASS: '1', NEXT_DIST_DIR: '.next-extended' }, url: 'http://127.0.0.1:3101/extended-quote-preview', reuseExistingServer: false, timeout: 120000 },
});
