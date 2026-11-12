import type { Page } from "@playwright/test";
import { expect, PASSWORD, uniqueEmail } from "./fixtures.ts";
import { linkIn, waitForEmail } from "./mailpit.ts";

/** Signs up through the UI and confirms the address through the real verification email. */
export async function signUpAndVerify(page: Page, label: string, name = "Ada Lovelace") {
  const email = uniqueEmail(label);
  await page.goto("/sign-up");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Confirm your email" })).toBeVisible();

  const mail = await waitForEmail(email, { subject: "Confirm your email address" });
  await page.goto(linkIn(mail.text, "/api/auth/verify-email"));
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
  return { email, password: PASSWORD, name };
}

export async function signIn(page: Page, email: string, password: string) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}
