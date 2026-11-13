import { expect, test } from "../support/fixtures.ts";
import { signUpAndVerify } from "../support/flows.ts";

test.describe("cabinet of specimens", () => {
  test("accession, edit, and dispose of a specimen", async ({ page }) => {
    await signUpAndVerify(page, "cabinet");
    await page.goto("/cabinet");
    await expect(page.getByRole("heading", { name: "The cabinet is empty" })).toBeVisible();

    await page.getByRole("button", { name: "Accession your first specimen" }).click();
    const accession = page.getByRole("dialog", { name: "Accession a specimen" });
    await accession.getByRole("button", { name: "Enter in the register" }).click();
    await expect(
      accession
        .getByText("Give the specimen a name.")
        .or(accession.getByText(/fill out this field/i)),
    ).toBeVisible();
    await accession.getByLabel("Name").fill("Singer 66 treadle");
    await accession.getByLabel("Notes").fill("Bobbin winder seized; hand wheel turns.");
    await accession.getByRole("button", { name: "Enter in the register" }).click();
    await expect(accession).toBeHidden();

    const specimens = page.getByRole("list", { name: "Specimens" });
    const drawer = specimens.getByRole("listitem", { name: "Singer 66 treadle" });
    await expect(drawer).toContainText("Bobbin winder seized");
    await expect(drawer).toContainText("No. I");

    await drawer.getByRole("button", { name: "Edit Singer 66 treadle" }).click();
    const edit = page.getByRole("dialog", { name: "Edit specimen" });
    await edit.getByLabel("Name").fill("Singer 66, 1923");
    await edit.getByRole("button", { name: "Save changes" }).click();
    await expect(edit).toBeHidden();
    await expect(specimens.getByRole("listitem", { name: "Singer 66, 1923" })).toBeVisible();

    await page.reload();
    const renamed = page.getByRole("listitem", { name: "Singer 66, 1923" });
    await renamed.getByRole("button", { name: "Delete Singer 66, 1923" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Dispose of this specimen?" });
    await confirm.getByRole("button", { name: "Keep it" }).click();
    await expect(renamed).toBeVisible();
    await renamed.getByRole("button", { name: "Delete Singer 66, 1923" }).click();
    await confirm.getByRole("button", { name: "Destroy specimen" }).click();
    await expect(page.getByRole("heading", { name: "The cabinet is empty" })).toBeVisible();
  });

  test("one user's specimens never appear in another's cabinet", async ({ page, browser }) => {
    await signUpAndVerify(page, "owner-a", "Ada");
    await page.goto("/cabinet");
    await page.getByRole("button", { name: "Accession your first specimen" }).click();
    await page.getByLabel("Name").fill("Ada's private orrery");
    await page.getByRole("button", { name: "Enter in the register" }).click();
    await expect(page.getByRole("listitem", { name: "Ada's private orrery" })).toBeVisible();

    const other = await browser.newContext();
    const otherPage = await other.newPage();
    await signUpAndVerify(otherPage, "owner-b", "Babbage");
    await otherPage.goto("/cabinet");
    await expect(otherPage.getByRole("heading", { name: "The cabinet is empty" })).toBeVisible();
    await expect(otherPage.getByText("Ada's private orrery")).toHaveCount(0);
    await other.close();
  });

  test("the cabinet requires signing in", async ({ page }) => {
    await page.goto("/cabinet");
    await expect(page).toHaveURL(/\/sign-in\?redirect=%2Fcabinet/);
  });
});
