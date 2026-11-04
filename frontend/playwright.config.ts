import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  use: { baseURL: "http://127.0.0.1:13000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "PYTHONPATH=../backend ../backend/.venv/bin/python ../scripts/seed_e2e.py && ../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 18000",
      url: "http://127.0.0.1:18000/api/health",
      reuseExistingServer: false,
      env: {
        DATABASE_URL: "sqlite:///./test-results/e2e.db",
        OPENAI_API_KEY: "",
        GEMINI_API_KEY: "",
        LLM_PROVIDER: "openai",
        GITHUB_TOKEN: "",
        AUTORCA_API_TOKEN: "",
        AUTH_ENABLED: "true",
        AUTORCA_E2E: "1",
        SANDBOX_ENABLED:
          process.env.AUTORCA_E2E_SANDBOX === "1" ? "true" : "false",
      },
    },
    {
      command: "npm run start -- --port 13000",
      url: "http://127.0.0.1:13000",
      reuseExistingServer: false,
      env: { BACKEND_URL: "http://127.0.0.1:18000", AUTORCA_API_TOKEN: "" },
      timeout: 120000,
    },
  ],
});
