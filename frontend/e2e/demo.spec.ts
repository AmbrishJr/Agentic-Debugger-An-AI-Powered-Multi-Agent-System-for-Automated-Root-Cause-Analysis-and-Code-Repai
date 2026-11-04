import { test, expect } from "./fixtures";

test("complete demo, inspect evidence and tests, approve, and find it in history", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/investigations/new");
  await page.getByRole("button", { name: "Load sample incident" }).click();
  const title = `E2E checkout ${Date.now()}`;
  await page.getByLabel("Incident title").fill(title);
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page).toHaveURL(/\/investigations\/[a-f0-9-]+/);
  await expect(page.getByText("7 of 7 completed")).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "1. Percentage discount is implemented as division",
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Review fix/ }).click();
  await expect(page.getByLabel("Proposed unified diff")).toContainText(
    "return price * (1 - discount / 100)",
  );
  await expect(page.getByText("Four regression tests after fix")).toBeVisible();
  await page.getByText("View before / after test output").click();
  await expect(
    page.getByText("Ran 4 tests", { exact: false }).last(),
  ).toBeVisible();
  await page
    .getByLabel("Review note")
    .fill("Reviewed through the browser end-to-end test.");
  await page.getByRole("button", { name: "Approve fix", exact: true }).click();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await page
    .getByRole("link", { name: "Incident history", exact: true })
    .click();
  await page.getByRole("textbox", { name: "Search incidents" }).fill(title);
  await expect(
    page.getByRole("cell", { name: "Approved", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Demo", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("rejection persists and mobile layout stays within the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/investigations/new?sample=1");
  await expect(page.getByLabel("Incident title")).not.toHaveValue("");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.getByText("7 of 7 completed")).toBeVisible();
  await page.getByRole("link", { name: /Review fix/ }).click();
  await page.getByRole("button", { name: "Reject fix", exact: true }).click();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Rejected").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/review-mobile.png",
    fullPage: true,
  });
  const overflow = await page.evaluate(() =>
    Array.from(document.querySelectorAll("body *"))
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.right > window.innerWidth + 1;
      })
      .map((element) => ({
        tag: element.tagName,
        cls: element.className,
        width: element.getBoundingClientRect().width,
      }))
      .slice(0, 12),
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    JSON.stringify(overflow),
  ).toBeTruthy();
});

test("settings save and dashboard renders stored analytics", async ({
  page,
}) => {
  await page.goto("/settings");
  await page.getByLabel("AI provider", { exact: true }).selectOption("gemini");
  await expect(page.getByLabel("Model", { exact: true })).toHaveValue("gemini-3.5-flash-lite");
  await page.getByLabel("Maximum historical matches").fill("4");
  await page.getByRole("button", { name: "Save configuration" }).click();
  await expect(page.getByRole("status")).toContainText("Configuration saved");
  await page.reload();
  await expect(page.getByLabel("AI provider", { exact: true })).toHaveValue("gemini");
  await expect(page.getByLabel("Maximum historical matches")).toHaveValue("4");
  await page.getByLabel("AI provider", { exact: true }).selectOption("openai");
  await page.getByRole("button", { name: "Save configuration" }).click();
  await expect(page.getByRole("status")).toContainText("Configuration saved");
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "From incident to insight." }),
  ).toBeVisible();
  await expect(
    page.getByText("Total incidents", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
});
