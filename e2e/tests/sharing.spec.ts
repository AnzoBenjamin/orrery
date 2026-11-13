import { expect, test } from "../support/fixtures.ts";
import { signUpAndVerify } from "../support/flows.ts";
import { media } from "../support/media.ts";

test.describe("share links", () => {
  test("a link opens the specimen read-only without signing in, until revoked", async ({
    page,
    browser,
  }) => {
    test.slow();
    await signUpAndVerify(page, "share");
    await page.goto("/cabinet");
    await page.getByRole("button", { name: "Accession your first specimen" }).click();
    await page.getByLabel("Name").fill("Vaucanson's duck");
    await page.getByRole("button", { name: "Enter in the register" }).click();
    await page.getByRole("link", { name: "Vaucanson's duck" }).click();

    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Choose files" }).click();
    await (await chooser).setFiles(media.shortClip());
    await expect(
      page.getByRole("list", { name: "Footage" }).getByRole("listitem", { name: "short.mp4" }),
    ).toContainText("Ready", { timeout: 60_000 });

    await page.getByRole("button", { name: "Share" }).click();
    const dialog = page.getByRole("dialog", { name: "Share this specimen" });
    await expect(dialog.getByText("No links yet.")).toBeVisible();
    await dialog.getByRole("radio", { name: "For 7 days" }).check({ force: true });
    await dialog.getByRole("button", { name: "Create link" }).click();
    const url = await dialog.getByLabel("New link").inputValue();
    expect(url).toMatch(/\/s\/[A-Za-z0-9_-]{43}$/);
    await expect(dialog.getByRole("list", { name: "Share links" })).toContainText("works until");

    const visitor = await browser.newContext();
    const guest = await visitor.newPage();
    await guest.goto(url);
    await expect(guest.getByRole("heading", { name: "Vaucanson's duck", level: 1 })).toBeVisible();
    await expect(guest.getByRole("button", { name: "Share" })).toHaveCount(0);
    await expect(guest.getByRole("button", { name: "Choose files" })).toHaveCount(0);
    await guest.getByRole("button", { name: "Play" }).click();
    await expect(guest.getByLabel("Playback of working footage")).toBeVisible();

    await dialog.getByRole("button", { name: /^Revoke link created/ }).click();
    await expect(dialog.getByText("Inactive")).toBeVisible();
    await guest.reload();
    await expect(guest.getByRole("heading", { name: "Link unavailable" })).toBeVisible();
    await visitor.close();
  });

  test("a made-up link reveals nothing", async ({ page }) => {
    await page.goto(`/s/${"x".repeat(43)}`);
    await expect(page.getByRole("heading", { name: "Link unavailable" })).toBeVisible();
  });
});
