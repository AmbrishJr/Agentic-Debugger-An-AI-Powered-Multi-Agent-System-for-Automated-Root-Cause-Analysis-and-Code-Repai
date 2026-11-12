import { test, expect } from "./fixtures";

test("immutable contract requires another account before investigation and can be selected for validation", async ({ page }) => {
  const session = await (await page.request.get("/api/auth/me")).json();
  const username = `contract-reviewer-${Date.now()}`;
  const response = await page.request.post("/api/users", { headers: { "X-CSRF-Token": session.csrf_token },
    data: { username, password: "contract-browser-password", role: "editor" } });
  expect(response.status()).toBe(201);
  await page.goto("/investigations/new?sample=1");
  await expect(page.getByLabel("Incident title")).not.toHaveValue("");
  await page.getByLabel("Save incident first to register a JSON contract for separate-account review").check();
  await page.getByRole("button", { name: "Save incident for contract review" }).click();
  await expect(page.getByRole("heading", { name: "Contract provenance before investigation" })).toBeVisible();
  const incidentId = page.url().split("/").at(-1)!;
  await page.getByText("Register an immutable JSON contract", { exact: true }).click();
  await page.getByLabel("Registered source files").fill("checkout.py");
  await page.getByLabel("Contract to register").fill(JSON.stringify({ entrypoint: "checkout.py", rationale: "Reviewed percentage and zero behavior for a provenance workflow test.",
    cases: [{ id: "percentage", role: "reproduction", input: 2, baseline: 1, expected: 3 },
            { id: "zero", role: "regression", input: 0, baseline: 0, expected: 0 }] }));
  await page.getByLabel("I reviewed the contract and understand it will be immutable.").check();
  await page.getByRole("button", { name: "Register contract", exact: true }).click();
  await expect(page.getByText(/Registered by browser-admin/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Record separate-account review" })).toHaveCount(0);
  await page.getByRole("button", { name: "Run investigation", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: /separate account must review/ })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill("contract-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.goto(`/investigations/${incidentId}`);
  await page.getByLabel("Independent review rationale").fill("Compared the declared behavior and input coverage against the incident before patch generation.");
  await page.getByLabel("I reviewed these answers and their relevance to the incident.").check();
  await page.getByRole("button", { name: "Record separate-account review" }).click();
  await expect(page.getByText(`Reviewed by ${username}:`, { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "Run investigation", exact: true }).click();
  await expect(page.getByText("7 of 7 completed")).toBeVisible();
  await page.getByRole("link", { name: /Review fix/ }).click();
  if (process.env.AUTORCA_E2E_SANDBOX === "1") {
    await page.getByLabel("Test framework").selectOption("python-json-stdio");
    await page.getByLabel("Use the immutable contract reviewed before investigation").check();
    await expect(page.getByLabel("checkout.py", { exact: true })).toBeChecked();
    await expect(page.getByLabel("checkout.py", { exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Prepare isolated test plan" }).click();
    await expect(page.getByText(/Registered before investigation with separate-account review/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Run isolated tests" })).toBeDisabled();
  }
});
