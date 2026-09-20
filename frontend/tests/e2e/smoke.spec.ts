/**
 * Playwright smoke for unified workspace + Excel-capable results.
 */
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const demoImage = path.resolve(__dirname, "../../../test-data/demo/old-tom-demo.jpg");
const batchDir = path.resolve(__dirname, "../../../test-data/batch-sample");

test.describe("Workspace smoke", () => {
  test("Single Label modal → Analyze → results", async ({ page, request }) => {
    const health = await request.get("http://127.0.0.1:8000/health/live");
    test.skip(!health.ok(), "Backend not running on :8000");

    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Review Setup/i })).toBeVisible();
    await expect(page.getByText(/Ready for review/i)).toBeVisible();
    await expect(page.getByText(/Select Single Label or Batch Review to begin/i)).toBeVisible();
    await page.getByRole("button", { name: /Single Label/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator('input[type="file"]').setInputFiles(demoImage);
    await page.getByRole("button", { name: /^Analyze Label$/i }).click();
    await expect(page.getByText(/Overall finding|Extracted label information/i).first()).toBeVisible({
      timeout: 120_000,
    });
    await expect(page.getByRole("button", { name: /Download Excel Report/i })).toBeVisible();
  });

  test("Batch modal → process → results", async ({ page, request }) => {
    const health = await request.get("http://127.0.0.1:8000/health/live");
    test.skip(!health.ok(), "Backend not running on :8000");

    await page.goto("/");
    await page.getByRole("button", { name: /Batch Review/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#batch-manifest").setInputFiles(path.join(batchDir, "sample-manifest.csv"));
    await page.locator("#batch-images").setInputFiles([
      path.join(batchDir, "old-tom-001.jpg"),
      path.join(batchDir, "stones-throw-002.jpg"),
      path.join(batchDir, "demo-review-003.jpg"),
    ]);
    await page.getByRole("button", { name: /^Validate$/i }).click();
    await expect(page.getByRole("button", { name: /Process Batch/i })).toBeEnabled({
      timeout: 60_000,
    });
    await page.getByRole("button", { name: /Process Batch/i }).click();
    await expect(page.getByText(/Batch results|Processed|COMPLETED/i).first()).toBeVisible({
      timeout: 180_000,
    });
  });
});
