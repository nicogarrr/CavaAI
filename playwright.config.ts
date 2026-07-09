import { defineConfig } from "@playwright/test";

const runE2E = process.env.E2E_RUN === "1";
const apiBaseURL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: apiBaseURL,
    trace: "retain-on-failure",
  },
  webServer: runE2E
    ? {
        command: "python -m uvicorn main:app --host 127.0.0.1 --port 8000",
        cwd: "data-engine",
        env: {
          APP_ENV: process.env.APP_ENV ?? "test",
          DATABASE_URL: process.env.DATABASE_URL ?? "sqlite:///./cavaai_e2e.db",
          CAVAAI_ENABLE_VECTOR_INGEST: "0",
          CAVAAI_ENABLE_VECTOR_CHAT: "0",
        },
        url: `${apiBaseURL}/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      }
    : undefined,
});
