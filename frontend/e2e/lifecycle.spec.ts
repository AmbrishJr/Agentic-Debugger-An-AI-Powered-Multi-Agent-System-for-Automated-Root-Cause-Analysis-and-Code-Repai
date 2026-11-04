import { test, expect } from "./fixtures";

test("resolution evidence and reopen history persist across reload", async ({
  page,
}) => {
  await page.goto("/investigations/new?sample=1");
  await expect(page.getByLabel("Incident title")).not.toHaveValue("");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.getByText("7 of 7 completed")).toBeVisible();
  await page.getByRole("link", { name: /Review fix/ }).click();
  await page.getByRole("button", { name: "Approve fix", exact: true }).click();
  await page
    .getByLabel("Resolution summary")
    .fill("Synthetic release restored checkout availability.");
  await page
    .getByLabel("Verification evidence")
    .fill("Synthetic CI run 123 and confirmed checkout monitoring.");
  await page.getByRole("button", { name: "Confirm resolved" }).click();
  await expect(page.getByLabel("Reason for reopening")).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Synthetic CI run 123", { exact: false }),
  ).toBeVisible();
  await page
    .getByLabel("Reason for reopening")
    .fill("Synthetic monitoring detected another failure.");
  await page.getByRole("button", { name: "Reopen incident" }).click();
  await expect(page.getByLabel("Resolution summary")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  const response = await page.request.get("/api/incidents");
  expect(response.status()).toBe(401);
});
