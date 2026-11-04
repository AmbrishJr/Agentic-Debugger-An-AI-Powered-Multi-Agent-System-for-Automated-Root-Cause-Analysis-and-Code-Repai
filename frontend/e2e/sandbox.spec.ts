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
  await page.getByRole("button", { name: "Approve fix", exact: true }).click();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await expect(page.getByText(/Isolated run /)).toBeVisible();
});
