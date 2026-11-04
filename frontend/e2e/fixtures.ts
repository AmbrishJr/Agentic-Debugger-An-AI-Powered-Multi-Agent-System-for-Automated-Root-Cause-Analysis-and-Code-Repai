import { test as base, expect } from "@playwright/test";
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.goto("/");
    await page.getByLabel("Username", { exact: true }).fill("browser-admin");
    await page
      .getByLabel("Password", { exact: true })
      .fill("browser-test-password-only");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
    await use(page);
  },
});
export { expect };
