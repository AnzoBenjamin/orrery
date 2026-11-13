import { expect, PASSWORD, test, uniqueEmail } from "../support/fixtures.ts";
import { signIn, signUpAndVerify } from "../support/flows.ts";
import { linkIn, waitForEmail } from "../support/mailpit.ts";

test.describe("email and password accounts", () => {
  test("sign-up sends a confirmation email whose link activates the account", async ({ page }) => {
    const { email, name } = await signUpAndVerify(page, "signup");
    await page.getByRole("link", { name: "Continue to your cabinet" }).click();
    await expect(page.getByRole("heading", { name: "Cabinet of specimens" })).toBeVisible();
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Account" })
      .click();
    await expect(page.getByText(email)).toBeVisible();
    await expect(page.getByText("Email confirmed")).toBeVisible();
    await expect(page.getByRole("region", { name: "Account" })).toContainText(name);
  });

  test("an unconfirmed account cannot sign in", async ({ page }) => {
    const email = uniqueEmail("unverified");
    await page.goto("/sign-up");
    await page.getByLabel("Name").fill("Charles Babbage");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByRole("heading", { name: "Confirm your email" })).toBeVisible();

    await signIn(page, email, PASSWORD);
    await expect(page.getByRole("alert")).toContainText("Confirm your email address first");
    await expect(page).toHaveURL(/\/sign-in/);
  });

  test("a wrong password is refused with guidance", async ({ page }) => {
    const { email } = await signUpAndVerify(page, "wrongpw");
    await page.getByRole("link", { name: "Continue to your cabinet" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/sign-in/);

    await signIn(page, email, "not the password at all");
    await expect(page.getByRole("alert")).toContainText("do not match an account");
  });

  test("signing out ends the session and protects the account page", async ({ page }) => {
    await signUpAndVerify(page, "signout");
    await page.goto("/account");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/sign-in/);
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?redirect=/);
  });

  test("a password reset link sets a new password and the old one stops working", async ({
    page,
  }) => {
    const { email } = await signUpAndVerify(page, "reset");
    await page.goto("/account");
    await page.getByRole("button", { name: "Sign out" }).click();

    const requested = new Date(Date.now() - 1000);
    await page.goto("/forgot-password");
    await page.getByLabel("Email").fill(email);
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("status")).toContainText("Check your email");

    const mail = await waitForEmail(email, {
      subject: "Reset your Orrery password",
      after: requested,
    });
    await page.goto(linkIn(mail.text, "/reset-password"));
    await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
    const newPassword = "governor flyball 1788";
    await page.getByLabel("New password", { exact: true }).fill(newPassword);
    await page.getByLabel("Repeat the new password").fill(newPassword);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByRole("status")).toContainText("Password changed");

    await signIn(page, email, PASSWORD);
    await expect(page.getByRole("alert")).toContainText("do not match an account");
    await signIn(page, email, newPassword);
    await expect(page.getByRole("heading", { name: "Cabinet of specimens" })).toBeVisible();
  });

  test("password reset reveals nothing about unknown addresses", async ({ page }) => {
    await page.goto("/forgot-password");
    await page.getByLabel("Email").fill(uniqueEmail("nobody"));
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("status")).toContainText("If an account uses that address");
  });

  test("an invalid reset link explains what to do", async ({ page }) => {
    await page.goto("/reset-password?error=INVALID_TOKEN");
    await expect(page.getByRole("alert")).toContainText("invalid, already used, or expired");
    await page.getByRole("link", { name: "Request a new link" }).click();
    await expect(page).toHaveURL(/\/forgot-password/);
  });
});
