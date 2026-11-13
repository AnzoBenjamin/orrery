import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type Page } from "@playwright/test";

/** Unique addresses per test run, so parallel tests never collide on one account. */
export function uniqueEmail(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@orrery.test`;
}

export const PASSWORD = "brass escapement 1868";

interface Violation {
  url: string;
  id: string;
  impact: string | null | undefined;
  help: string;
  targets: string[];
  html: string[];
}

async function audit(page: Page, url: string, found: Violation[]) {
  try {
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    for (const v of results.violations) {
      if (v.impact === "serious" || v.impact === "critical") {
        found.push({
          url,
          id: v.id,
          impact: v.impact,
          help: v.help,
          targets: v.nodes.map((n) => n.target.join(" ")),
          html: v.nodes.map((n) => n.html.slice(0, 300)),
        });
      }
    }
  } catch (error) {
    // The page navigated away mid-audit (the next load is audited instead), or the test finished
    // while a last load event was still being audited.
    if (!(error instanceof Error && /navigat|closed|destroyed|context|test ended/i.test(error.message))) {
      throw error;
    }
  }
}

/**
 * Every page a test visits is checked with axe once it loads, and the test fails on serious or
 * critical violations (requirement 13.5).
 */
export const test = base.extend<{ accessibility: undefined }>({
  accessibility: [
    async ({ page }, use) => {
      const found: Violation[] = [];
      // Axe allows one run per page at a time, so audits are chained.
      let chain: Promise<void> = Promise.resolve();
      page.on("load", () => {
        const url = page.url();
        chain = chain.then(() => audit(page, url, found));
      });
      await use(undefined);
      await chain;
      expect(found, JSON.stringify(found, null, 2)).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
