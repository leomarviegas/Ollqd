import { Page, expect } from '@playwright/test';

/** Gateway API base URL (Go service) */
export const GATEWAY_URL = process.env.GATEWAY_URL || 'http://localhost:8000';

/**
 * Log in to the Ollqd WebUI.
 * Fills the username field with "testuser", submits the login form,
 * and waits until the dashboard heading is visible.
 */
export async function login(page: Page): Promise<void> {
  await page.goto('/');
  // Wait for the login form to render (Alpine.js hydration)
  await page.waitForSelector('input[type="text"][x-model="loginForm.username"]', {
    state: 'visible',
    timeout: 15_000,
  });
  await page.fill('input[x-model="loginForm.username"]', 'testuser');
  // Fill password field if present
  const passwordField = page.locator('input[x-model="loginForm.password"]');
  if (await passwordField.isVisible()) {
    await passwordField.fill('testpass');
  }
  await page.click('button[type="submit"]');
  // Wait for the dashboard to appear — the sidebar should be visible
  await page.waitForSelector('aside', { state: 'visible', timeout: 15_000 });
  // Verify we see the Dashboard heading
  await expect(page.locator('h2:has-text("Dashboard")')).toBeVisible({ timeout: 10_000 });
}

/**
 * Navigate to a specific tab/view by clicking the sidebar nav button.
 * @param tabName - The visible text label of the tab (e.g. "Collections", "Models", "RAG Chat")
 */
export async function navigateToTab(page: Page, tabName: string): Promise<void> {
  // Click the sidebar nav button whose text matches the tab name
  const navButton = page.locator(`aside nav button:has(span:text("${tabName}"))`);
  await navButton.click();
  // Wait a short time for Alpine.js transitions
  await page.waitForTimeout(500);
}

/**
 * Wait for the health status indicators in the sidebar to be visible.
 * These show Ollama and Qdrant connection status (up/down).
 */
export async function waitForHealth(page: Page): Promise<void> {
  // The health indicators are in the sidebar footer
  await page.waitForSelector('aside >> text=Ollama', { state: 'visible', timeout: 10_000 });
  await page.waitForSelector('aside >> text=Qdrant', { state: 'visible', timeout: 10_000 });
}

/**
 * Collect console errors during a page operation.
 * Returns an array of unexpected error messages.
 * Ignores known/expected errors (e.g. network requests failing when services are down).
 */
export async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Ignore expected errors from services that may not be running
      const ignoredPatterns = [
        'net::ERR_',
        'Failed to fetch',
        'NetworkError',
        'WebSocket',
        'favicon.ico',
        'ERR_CONNECTION_REFUSED',
        'Load failed',
        'Failed to load viz libs',
      ];
      if (!ignoredPatterns.some((pattern) => text.includes(pattern))) {
        errors.push(text);
      }
    }
  });
  return errors;
}

/**
 * Wait for no unexpected console errors on the current page.
 * Collects console errors for a brief period and asserts none were found.
 */
export async function waitForNoConsoleErrors(page: Page): Promise<void> {
  const errors = await collectConsoleErrors(page);
  // Give the page a moment to settle
  await page.waitForTimeout(2_000);
  expect(errors).toEqual([]);
}

/**
 * Generate a unique collection name for test isolation.
 */
export function uniqueCollectionName(prefix = 'e2e-test'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}
