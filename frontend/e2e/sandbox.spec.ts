import { test, expect } from "./fixtures";

test("reviewed snapshot authorization runs real isolated before and after tests", async ({
  page,
}) => {
  test.skip(
    process.env.AUTORCA_E2E_SANDBOX !== "1",
    "Opt in to a configured real Docker runtime.",
  );
  await page.goto("/investigations/new?sample=1");
  await expect(page.getByLabel("Incident title")).not.toHaveValue("");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.getByText("7 of 7 completed")).toBeVisible();
  await page.getByRole("link", { name: /Review fix/ }).click();
  await page.getByLabel("checkout.py", { exact: true }).check();
  await page.getByLabel("test_checkout.py", { exact: true }).check();
  await page.getByLabel("Add reviewed reproduction and regression expectations").check();
  await page.getByLabel("Expected reproduction failures").fill([
    "test_checkout.DiscountTests.test_zero_discount | ZeroDivisionError",
    "test_checkout.DiscountTests.test_invalid_inputs | ZeroDivisionError",
    "test_checkout.DiscountTests.test_percentage_discount | AssertionError",
    "test_checkout.DiscountTests.test_full_discount | AssertionError",
  ].join("\n"));
  await page.getByLabel("Required regression tests").fill([
    "test_checkout.DiscountTests.test_zero_discount",
    "test_checkout.DiscountTests.test_percentage_discount",
    "test_checkout.DiscountTests.test_full_discount",
    "test_checkout.DiscountTests.test_invalid_inputs",
  ].join("\n"));
  await page.getByLabel("Why these tests cover the incident").fill("Reviewed zero-discount reproduction, percentage arithmetic, boundaries and invalid inputs.");
  await expect(page.getByRole("button", { name: "Prepare isolated test plan" })).toBeDisabled();
  await page.getByLabel("I reviewed these existing tests and their expected behavior against the incident.").check();
  await page
    .getByRole("button", { name: "Prepare isolated test plan" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review this execution plan" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run isolated tests" }),
  ).toBeDisabled();
  await page
    .getByLabel(
      "I authorize executing these source and test snapshots before and after this patch in the restricted runner.",
    )
    .check();
  await page.getByRole("button", { name: "Run isolated tests" }).click();
  await expect(page.getByText(/Isolated run /)).toBeVisible();
  const run = page
    .locator("details")
    .filter({ hasText: /Isolated run / })
    .first();
  await expect(run.getByText("Completed", { exact: true })).toBeVisible();
  if (!((await run.getAttribute("open")) !== null))
    await run.locator("summary").click();
  await expect(
    page.getByRole("heading", { name: "After patch · passed · exit 0" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Verified repair" })).toBeVisible();
  await expect(run.getByRole("heading", { name: "Specification observations: matched" })).toBeVisible();
  const incidentId = page.url().split("/").at(-2);
  const report = await page.request.get(`/api/incidents/${incidentId}/report`);
  const exported = await report.json();
  expect(exported.repair_outcome.status).toBe("VERIFIED");
  expect(exported.validation.isolated.specification_assessment.status).toBe("matched");
  expect(exported.validation.isolated.specification_assessment.independent_proof).toBe(false);
  await page.getByRole("button", { name: "Approve fix", exact: true }).click();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await expect(page.getByText(/Isolated run /)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Verified repair" })).toBeVisible();
});

test("wrong reviewed failure expectation blocks a positive repair outcome", async ({ page }) => {
  test.skip(process.env.AUTORCA_E2E_SANDBOX !== "1", "Requires the configured restricted runner.");
  const session = await (await page.request.get("/api/auth/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const sample = (await (await page.request.get("/api/samples")).json()).items[0];
  const created = await page.request.post("/api/incidents", { headers, data: { title: "Expected failure mismatch", error_log: sample.error_log } });
  expect(created.status()).toBe(201);
  const incident = await created.json();
  await page.request.post(`/api/incidents/${incident.id}/investigate`, { headers, data: {} });
  await expect.poll(async () => (await (await page.request.get(`/api/incidents/${incident.id}`)).json()).status).toBe("awaiting_review");
  const tests = [
    ["test_zero_discount", "ValueError"], // Deliberately wrong; the source raises ZeroDivisionError.
    ["test_invalid_inputs", "ZeroDivisionError"],
    ["test_percentage_discount", "AssertionError"],
    ["test_full_discount", "AssertionError"],
  ];
  const response = await page.request.post(`/api/incidents/${incident.id}/validation-plans`, { headers, data: {
    files: ["checkout.py", "test_checkout.py"], verification_spec: {
      version: 1, reviewed: true, rationale: "Negative fixture: the expected exception deliberately does not match the incident.",
      reproduction: tests.map(([method, exception]) => ({ test_id: `test_checkout.DiscountTests.${method}`, expected_exception: exception })),
      regressions: tests.map(([method]) => `test_checkout.DiscountTests.${method}`),
    },
  } });
  expect(response.status()).toBe(201);
  const planned = await response.json();
  expect((await page.request.post(`/api/incidents/${incident.id}/validation-runs/${planned.id}/authorize`, { headers,
    data: { authorized: true, plan_hash: planned.plan_hash } })).status()).toBe(202);
  await page.goto(`/investigations/${incident.id}/review`);
  await expect(page.getByRole("heading", { name: "Validation failed" })).toBeVisible();
  expect((await (await page.request.get(`/api/incidents/${incident.id}/report`)).json()).validation.isolated.specification_assessment.status).toBe("mismatch");
  await expect(page.getByRole("heading", { name: "Verified repair" })).toHaveCount(0);
});
