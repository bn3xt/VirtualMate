import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("chat and administration use GET plus WebSocket without local POST", async ({ page }) => {
  const localMethods: string[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith("http://127.0.0.1:8135")) localMethods.push(request.method());
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "How can VirtualMate help you today?" })).toBeVisible();
  await expect(page.getByText("No knowledge index is ready", { exact: true })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByPlaceholder("Message VirtualMate")).toBeVisible();
  await page.screenshot({ path: "standalone/virtual_mate/artifacts/ui-modern-chat.png", fullPage: true });

  await page.getByRole("button", { name: "Administration", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("main").getByText("personal_legacy_v1")).toBeVisible();
  await expect(page.getByText(/workspace[\\/]knowledge/)).toBeVisible();
  await page.screenshot({ path: "standalone/virtual_mate/artifacts/ui-modern-admin.png", fullPage: true });

  const id = `ui-server-${Date.now()}`;
  const alias = `UI Test Server ${id}`;
  const baseUrl = `https://${id}.example.test/v1`;
  await page.getByLabel("Identifier").fill(id);
  await page.getByLabel("Alias").fill(alias);
  await page.getByLabel("Base URL").fill(baseUrl);
  await page.getByRole("button", { name: "Save server" }).click();
  await expect(page.getByText(alias)).toBeVisible();
  await expect(page.getByText(baseUrl)).toBeVisible();

  expect(localMethods.length).toBeGreaterThan(0);
  expect(localMethods).not.toContain("POST");
  expect(new Set(localMethods)).toEqual(new Set(["GET"]));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  await expect(page.getByPlaceholder("Message VirtualMate")).toBeVisible();
  await expect(page.getByRole("heading", { name: "How can VirtualMate help you today?" })).toBeVisible();
  await page.screenshot({ path: "standalone/virtual_mate/artifacts/ui-modern-mobile.png", fullPage: true });
});

test("chat reports a setup error without breaking the interface", async ({ page }) => {
  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: "standalone/virtual_mate/artifacts/ui-modern-dark.png", fullPage: true });
  await page.getByPlaceholder("Message VirtualMate").fill("What is the current project status?");
  await page.getByPlaceholder("Message VirtualMate").press("Enter");

  await expect(page.getByText(/I could not generate an answer: The chat role must be configured/)).toBeVisible();
  await expect(page.getByText(/End-to-end response time:/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "VirtualMate" })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export conversation" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^virtualmate-conversation-.*\.html$/);
  const downloadedPath = await download.path();
  expect(downloadedPath).not.toBeNull();
  const exported = await readFile(downloadedPath!, "utf8");
  expect(exported).toContain("Conversation with VirtualMate");
  expect(exported).toContain("What is the current project status?");
  expect(exported).toContain("End-to-end response time:");
  expect(exported).toContain("color-scheme:dark");
  expect(exported).not.toContain("mermaid-toolbar");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Switch to light mode" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

