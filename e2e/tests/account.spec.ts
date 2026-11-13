import type { Page } from "@playwright/test";
import { expect, test } from "../support/fixtures.ts";
import { signIn, signUpAndVerify } from "../support/flows.ts";

async function openAccount(page: Page) {
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Account", level: 1 })).toBeVisible();
}

test.describe("account settings", () => {
  test("lists sessions and signs out another device", async ({ page, browser }) => {
    // Several sign-ins, browser contexts, and page audits: allow three times the usual time.
    test.slow();
    const { email, password } = await signUpAndVerify(page, "sessions");

    const laptop = await browser.newContext();
    const laptopPage = await laptop.newPage();
    await signIn(laptopPage, email, password);
    await expect(laptopPage).toHaveURL(/\/cabinet/);

    await openAccount(page);
    const sessions = page.getByRole("list", { name: "Sessions" });
    await expect(sessions.getByRole("listitem")).toHaveCount(2);
    await expect(sessions.getByRole("listitem", { name: /this device/ })).toContainText(
      "This device",
    );

    await sessions.getByRole("button", { name: /^Sign out / }).click();
    await expect(sessions.getByRole("listitem")).toHaveCount(1);
    await expect(page.getByText("This is the only place you are signed in.")).toBeVisible();

    await laptopPage.goto("/account");
    await expect(laptopPage).toHaveURL(/\/sign-in\?redirect=/);
    await laptop.close();

    // The remaining session is still signed in.
    await page.reload();
    await expect(page.getByRole("heading", { name: "Account", level: 1 })).toBeVisible();
  });

  test("signs out everywhere else at once", async ({ page, browser }) => {
    // Several sign-ins, browser contexts, and page audits: allow three times the usual time.
    test.slow();
    const { email, password } = await signUpAndVerify(page, "everywhere");
    const others = await Promise.all([browser.newContext(), browser.newContext()]);
    for (const context of others) {
      const p = await context.newPage();
      await signIn(p, email, password);
      await expect(p).toHaveURL(/\/cabinet/);
    }

    await openAccount(page);
    const sessions = page.getByRole("list", { name: "Sessions" });
    await expect(sessions.getByRole("listitem")).toHaveCount(3);
    await page.getByRole("button", { name: "Sign out everywhere else" }).click();
    await expect(sessions.getByRole("listitem")).toHaveCount(1);

    for (const context of others) {
      const p = context.pages()[0];
      if (!p) throw new Error("context lost its page");
      await p.goto("/cabinet");
      await expect(p).toHaveURL(/\/sign-in\?redirect=/);
      await context.close();
    }
  });

  test("turning off analysis emails is remembered", async ({ page }) => {
    await signUpAndVerify(page, "prefs");
    await openAccount(page);
    const toggle = page.getByRole("switch", { name: "Email me when an analysis finishes" });
    await expect(toggle).toBeChecked();
    await page.locator("label").filter({ hasText: "Email me when an analysis finishes" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("switch", { name: "Email me when an analysis finishes" }),
    ).not.toBeChecked();
  });

  test("adds a passkey, signs in with it, and removes it", async ({ page }) => {
    // Several sign-ins, browser contexts, and page audits: allow three times the usual time.
    test.slow();
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("WebAuthn.enable");
    await cdp.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    });

    await signUpAndVerify(page, "passkey");
    await openAccount(page);
    await expect(page.getByText("No passkeys yet.")).toBeVisible();
    await page.getByRole("button", { name: "Add a passkey" }).click();
    const dialog = page.getByRole("dialog", { name: "Add a passkey" });
    await dialog.getByLabel("Name").fill("Workshop laptop");
    await dialog.getByRole("button", { name: "Create passkey" }).click();
    await expect(dialog).toBeHidden();
    const passkeys = page.getByRole("list", { name: "Passkeys" });
    await expect(passkeys.getByRole("listitem", { name: "Workshop laptop" })).toBeVisible();

    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page).toHaveURL(/\/sign-in/);
    await page.getByRole("button", { name: "Sign in with a passkey" }).click();
    await expect(page).toHaveURL(/\/cabinet/);

    await openAccount(page);
    await passkeys.getByRole("button", { name: "Remove Workshop laptop" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Remove this passkey?" });
    await confirm.getByRole("button", { name: "Remove passkey" }).click();
    await expect(confirm).toBeHidden();
    await expect(page.getByText("No passkeys yet.")).toBeVisible();
  });

  test("deleting the account destroys its specimens and its sign-in", async ({ page }) => {
    // Several sign-ins, browser contexts, and page audits: allow three times the usual time.
    test.slow();
    const { email, password } = await signUpAndVerify(page, "delete");
    await page.goto("/cabinet");
    await page.getByRole("button", { name: "Accession your first specimen" }).click();
    await page.getByLabel("Name").fill("Doomed music box");
    await page.getByRole("button", { name: "Enter in the register" }).click();
    await expect(page.getByRole("listitem", { name: "Doomed music box" })).toBeVisible();

    await openAccount(page);
    await page.getByRole("button", { name: "Delete account" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Delete your account?" });
    await confirm.getByRole("button", { name: "Keep my account" }).click();
    await expect(confirm).toBeHidden();

    await page.getByRole("button", { name: "Delete account" }).click();
    await confirm.getByLabel("Password").fill("not my password at all");
    await confirm.getByRole("button", { name: "Delete everything" }).click();
    await expect(confirm.getByRole("alert")).toContainText("That password is not correct");

    await confirm.getByLabel("Password").fill(password);
    await confirm.getByRole("button", { name: "Delete everything" }).click();
    await expect(page).toHaveURL(/\/sign-in\?deleted=/);
    await expect(page.getByRole("status")).toContainText("have been deleted");

    await page.goto("/cabinet");
    await expect(page).toHaveURL(/\/sign-in\?redirect=/);
    await signIn(page, email, password);
    await expect(page.getByRole("alert")).toContainText("do not match an account");
  });
});
