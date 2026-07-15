import { defineConfig } from "@playwright/test";
import { createHmac } from "node:crypto";

const runE2E = process.env.E2E_RUN === "1";
const runUiE2E = process.env.E2E_UI_RUN === "1";
const apiBaseURL = process.env.E2E_API_URL ?? "http://127.0.0.1:8101";
const uiBaseURL = process.env.E2E_UI_URL ?? "http://127.0.0.1:3100";
const uiPort = new URL(uiBaseURL).port || "3100";
const apiPort = new URL(apiBaseURL).port || "8101";
const uiBackendURL = process.env.E2E_UI_BACKEND_URL ?? "http://127.0.0.1:8100";
const e2eResearchSecret = process.env.RESEARCH_AUTH_SECRET ?? "cavaai-e2e-research-secret-at-least-32-characters";
const apiTimestamp = Math.floor(Date.now() / 1000).toString();
const apiTenant = "e2e-api-tenant";
const apiUser = "e2e-api-user";
const apiSignature = createHmac("sha256", e2eResearchSecret)
  .update(`${apiTenant}:${apiUser}:${apiTimestamp}`)
  .digest("hex");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  timeout: 90_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: runUiE2E ? uiBaseURL : apiBaseURL,
    trace: "retain-on-failure",
    extraHTTPHeaders: runE2E
      ? {
          "X-CavaAI-Tenant": apiTenant,
          "X-CavaAI-User": apiUser,
          "X-CavaAI-Timestamp": apiTimestamp,
          "X-CavaAI-Signature": apiSignature,
        }
      : undefined,
  },
  webServer: runUiE2E
    ? [
      {
        command: "python -m uvicorn main:app --host 127.0.0.1 --port 8100",
        cwd: "data-engine",
        env: {
          APP_ENV: "test",
          DATABASE_URL: "sqlite:///./cavaai_ui_e2e.db",
          RESEARCH_AUTH_REQUIRED: "true",
          RESEARCH_AUTH_SECRET: e2eResearchSecret,
          RESEARCH_AUTH_MAX_AGE_SECONDS: "3600",
          CAVAAI_ENABLE_VECTOR_INGEST: "0",
          CAVAAI_ENABLE_VECTOR_CHAT: "0",
        },
        url: `${uiBackendURL}/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
      {
        command: `npm run dev -- --hostname 127.0.0.1 --port ${uiPort}`,
        env: {
          BETTER_AUTH_SECRET: process.env.BETTER_AUTH_SECRET ?? "cavaai-e2e-secret-at-least-32-characters",
          BETTER_AUTH_URL: uiBaseURL,
          E2E_AUTH_BYPASS: "1",
          FMP_BACKEND_URL: uiBackendURL,
          RESEARCH_AUTH_SECRET: e2eResearchSecret,
          NEXT_DIST_DIR: ".next-e2e",
        },
        url: `${uiBaseURL}/sign-in`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
    ]
    : runE2E
    ? {
        command: `python -m uvicorn main:app --host 127.0.0.1 --port ${apiPort}`,
        cwd: "data-engine",
        env: {
          APP_ENV: process.env.APP_ENV ?? "test",
          DATABASE_URL: process.env.DATABASE_URL ?? "sqlite:///./cavaai_e2e.db",
          RESEARCH_AUTH_REQUIRED: "true",
          RESEARCH_AUTH_SECRET: e2eResearchSecret,
          RESEARCH_AUTH_MAX_AGE_SECONDS: "3600",
          CAVAAI_ENABLE_VECTOR_INGEST: "0",
          CAVAAI_ENABLE_VECTOR_CHAT: "0",
        },
        url: `${apiBaseURL}/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      }
    : undefined,
});
