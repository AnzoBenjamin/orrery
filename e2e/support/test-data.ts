/**
 * Test data creation helpers.
 *
 * These create test data through the product's own flows (UI or server functions),
 * never through direct database manipulation. This ensures tests exercise real
 * user paths while being more maintainable than inline test code.
 */
import type { Page } from "@playwright/test";
import { expect, PASSWORD, uniqueEmail } from "./fixtures.ts";
import { linkIn, waitForEmail } from "./mailpit.ts";

export interface TestUser {
  email: string;
  password: string;
  name: string;
}

export interface TestSpecimen {
  id: string;
  title: string;
  description: string;
}

/**
 * Create and verify a user through the UI flow.
 *
 * This is the most reliable approach as it exercises the real sign-up path
 * that users experience.
 */
export async function createTestUserViaUI(
  page: Page,
  label: string,
  name = "Test User",
): Promise<TestUser> {
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

/**
 * Sign in an existing user via the UI.
 */
export async function signInViaUI(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  // Wait for redirect away from sign-in page
  await expect(page).not.toHaveURL(/\/sign-in/);
}

/**
 * Create and sign in a test user, ready to use the app.
 *
 * This combines user creation and sign-in, leaving the page authenticated
 * and ready to create specimens or perform other actions.
 */
export async function setupTestUser(
  page: Page,
  label: string,
  name = "Test User",
): Promise<TestUser> {
  const user = await createTestUserViaUI(page, label, name);

  // The verification flow signs the user in, but let's navigate to cabinet to confirm
  await page.goto("/cabinet");
  await expect(page.getByRole("heading", { name: "Cabinet of specimens" })).toBeVisible();

  return user;
}

/**
 * Create a specimen via the UI flow.
 *
 * The page must already be authenticated (call setupTestUser first).
 */
export async function createTestSpecimenViaUI(
  page: Page,
  data: { title: string; description?: string },
): Promise<TestSpecimen> {
  await page.goto("/cabinet");

  // Open accession dialog
  const hasSpecimens = await page.getByRole("list", { name: "Specimens" }).isVisible();
  if (hasSpecimens) {
    await page.getByRole("button", { name: "Accession a specimen" }).click();
  } else {
    await page.getByRole("button", { name: "Accession your first specimen" }).click();
  }

  // Fill form
  const dialog = page.getByRole("dialog", { name: "Accession a specimen" });
  await dialog.getByLabel("Name").fill(data.title);
  if (data.description) {
    await dialog.getByLabel("Notes").fill(data.description);
  }
  await dialog.getByRole("button", { name: "Enter in the register" }).click();

  // Wait for dialog to close and specimen to appear
  await expect(dialog).toBeHidden();
  const specimenItem = page.getByRole("listitem", { name: data.title });
  await expect(specimenItem).toBeVisible();

  // Extract specimen ID from the link
  const specimenLink = specimenItem.getByRole("link", { name: data.title });
  const href = await specimenLink.getAttribute("href");
  if (!href) {
    throw new Error("Specimen link has no href");
  }

  const match = href.match(/\/specimens\/([a-f0-9-]+)/);
  if (!match?.[1]) {
    throw new Error(`Could not extract specimen ID from href: ${href}`);
  }

  return {
    id: match[1],
    title: data.title,
    description: data.description ?? "",
  };
}

/**
 * Create multiple specimens for a test user.
 *
 * Useful for testing lists, pagination, and bulk operations.
 */
export async function createMultipleSpecimens(
  page: Page,
  count: number,
  titlePrefix = "Test Specimen",
): Promise<TestSpecimen[]> {
  const specimens: TestSpecimen[] = [];

  for (let i = 0; i < count; i++) {
    const specimen = await createTestSpecimenViaUI(page, {
      title: `${titlePrefix} ${i + 1}`,
      description: `Description for specimen ${i + 1}`,
    });
    specimens.push(specimen);
  }

  return specimens;
}

/**
 * Navigate to a specimen page.
 */
export async function goToSpecimen(page: Page, specimenId: string): Promise<void> {
  await page.goto(`/specimens/${specimenId}`);
}

/**
 * Delete a specimen via the UI.
 */
export async function deleteSpecimenViaUI(page: Page, title: string): Promise<void> {
  await page.goto("/cabinet");
  const specimenItem = page.getByRole("listitem", { name: title });
  await specimenItem.getByRole("button", { name: `Delete ${title}` }).click();

  const confirm = page.getByRole("alertdialog", { name: "Dispose of this specimen?" });
  await confirm.getByRole("button", { name: "Destroy specimen" }).click();

  await expect(specimenItem).toBeHidden();
}
