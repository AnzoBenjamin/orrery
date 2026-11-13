import type { Page } from "@playwright/test";
import { expect, test } from "../support/fixtures.ts";
import { signUpAndVerify } from "../support/flows.ts";
import { media } from "../support/media.ts";

async function newSpecimen(page: Page, title: string) {
  await page.goto("/cabinet");
  await page.getByRole("button", { name: "Accession your first specimen" }).click();
  await page.getByLabel("Name").fill(title);
  await page.getByRole("button", { name: "Enter in the register" }).click();
  await page.getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
}

/** Polls a (still validly signed) object URL until the store no longer has the object. */
export async function expectObjectGone(page: Page, url: string) {
  await expect
    .poll(async () => (await page.request.get(url)).status(), {
      timeout: 150_000,
      intervals: [2_000, 5_000],
    })
    .toBe(404);
}

async function choose(page: Page, path: string) {
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles(path);
}

test.describe("footage", () => {
  test("uploads real footage, inspects it, plays it, and removes it", async ({ page }) => {
    test.slow();
    await signUpAndVerify(page, "footage");
    await newSpecimen(page, "Singer 66 treadle");
    await expect(page.getByText("No footage yet")).toBeVisible();

    await page.getByRole("radio", { name: "Broken" }).check({ force: true });
    await choose(page, media.shortClip());

    const item = page.getByRole("list", { name: "Footage" }).getByRole("listitem", {
      name: "short.mp4",
    });
    await expect(item).toContainText("Broken");
    await expect(item).toContainText("Ready", { timeout: 60_000 });
    await expect(item).toContainText("0:02 · 320 × 240 · 30 fps · H264");

    await item.getByRole("button", { name: "Play short.mp4" }).click();
    const video = item.getByLabel("Playback of short.mp4");
    await expect(video).toBeVisible();
    await expect
      .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 20_000 })
      .toBeGreaterThan(0);

    const objectUrl = await video.getAttribute("src");
    if (!objectUrl) throw new Error("the player has no source");

    await item.getByRole("button", { name: "Remove short.mp4" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Remove this footage?" });
    await confirm.getByRole("button", { name: "Remove footage" }).click();
    await expect(page.getByText("No footage yet")).toBeVisible();
    // The objects.delete job runs every minute and removes the stored file.
    await expectObjectGone(page, objectUrl);
  });

  test("rejects a renamed non-video file with guidance", async ({ page }) => {
    test.slow();
    await signUpAndVerify(page, "disguised");
    await newSpecimen(page, "Typewriter");
    await choose(page, media.disguised());
    const item = page.getByRole("list", { name: "Footage" }).getByRole("listitem", {
      name: "notes.mp4",
    });
    await expect(item).toContainText("Rejected", { timeout: 60_000 });
    await expect(item).toContainText("not a video we can read");

    // The owner is told in the notice tray, which links back to the specimen.
    const tray = page.getByRole("button", { name: "Notices, 1 unread" });
    await expect(tray).toBeVisible();
    await tray.click();
    const notices = page.getByRole("dialog", { name: "Notices" });
    const notice = notices.getByRole("link", { name: /notes\.mp4 was rejected/ });
    await expect(notice).toContainText("not a video we can read");
    await notice.click();
    await expect(page.getByRole("button", { name: "Notices", exact: true })).toBeVisible();
  });

  test("an upload survives a dropped connection and finishes", async ({ page }) => {
    test.slow();
    await signUpAndVerify(page, "offline");
    await newSpecimen(page, "Mantel clock");
    // Slow the upload enough to cut the connection part-way through.
    await page.route("http://localhost:53900/**", async (route) => {
      await new Promise((r) => setTimeout(r, 400));
      await route.continue();
    });
    await choose(page, media.largeClip());

    const upload = page.getByRole("list", { name: "Uploads" }).getByRole("listitem", {
      name: "large.mp4",
    });
    await expect(upload).toContainText(/Uploading, [1-9][\d.]* MB of/, { timeout: 60_000 });
    await page.context().setOffline(true);
    await expect(page.getByText("Connection lost.")).toBeVisible();
    await page.waitForTimeout(3000);
    await page.context().setOffline(false);

    const item = page.getByRole("list", { name: "Footage" }).getByRole("listitem", {
      name: "large.mp4",
    });
    await expect(item).toContainText("Ready", { timeout: 120_000 });
    await expect(upload).toHaveCount(0);
  });
});
