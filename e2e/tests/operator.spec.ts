import { execFileSync } from "node:child_process";
import { expect, test } from "../support/fixtures.ts";
import { signUpAndVerify } from "../support/flows.ts";

/** The operator CLI, exactly as `make admin email=…` runs it. */
function grantAdmin(email: string) {
  execFileSync("pnpm", ["--filter", "@orrery/worker", "--silent", "role", "grant", email], {
    stdio: "pipe",
  });
}

test.describe("operator page", () => {
  test("is invisible to ordinary users", async ({ page }) => {
    await signUpAndVerify(page, "not-admin");
    await page.goto("/cabinet");
    await expect(page.getByRole("link", { name: "Operator" })).toHaveCount(0);
    await page.goto("/admin");
    await expect(page.getByRole("alert")).toContainText("does not exist");
    await expect(page.getByRole("table")).toHaveCount(0);
  });

  test("shows an admin every queue, what is running, and recent failures", async ({ page }) => {
    const { email } = await signUpAndVerify(page, "operator");
    grantAdmin(email);
    await page.goto("/cabinet");
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Operator" })
      .click();
    await expect(page.getByRole("heading", { name: "Operator", level: 1 })).toBeVisible();
    const queues = page.getByRole("region", { name: "Queues" }).getByRole("table");
    for (const name of ["email.send", "footage.probe", "objects.delete", "uploads.reap"]) {
      await expect(queues.getByRole("rowheader", { name })).toBeVisible();
    }
    const status = page.getByRole("region", { name: "Status" });
    await expect(status).toContainText("Object store");
    // The running stack's worker finishes its sweep every minute.
    await expect(status).toContainText("Last scheduled sweep finished");
    await expect(page.getByRole("heading", { name: "Running" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recent failures" })).toBeVisible();
  });
});
