import { test, expect } from '@playwright/test';
import { login, navigateToTab, uniqueCollectionName, GATEWAY_URL } from './helpers';

test.describe('Security', () => {
  test('no sensitive headers in responses', async ({ page }) => {
    const sensitiveHeaders: { url: string; header: string; value: string }[] = [];

    // Intercept all network responses and check for sensitive headers
    page.on('response', (response) => {
      const headers = response.headers();
      const url = response.url();

      // Check for gRPC headers that should not leak to the frontend
      const sensitivePatterns = [
        'x-grpc-',
        'grpc-status',
        'grpc-message',
        'grpc-encoding',
        'x-envoy-',
        'x-debug',
      ];

      for (const [headerName, headerValue] of Object.entries(headers)) {
        for (const pattern of sensitivePatterns) {
          if (headerName.toLowerCase().startsWith(pattern)) {
            sensitiveHeaders.push({ url, header: headerName, value: headerValue });
          }
        }
      }
    });

    await login(page);

    // Navigate through several pages to generate network requests
    await navigateToTab(page, 'Collections');
    await page.waitForTimeout(1_000);

    await navigateToTab(page, 'Models');
    await page.waitForTimeout(1_000);

    await navigateToTab(page, 'Settings');
    await page.waitForTimeout(1_000);

    await navigateToTab(page, 'Dashboard');
    await page.waitForTimeout(1_000);

    // Assert no sensitive headers were found
    expect(sensitiveHeaders).toEqual([]);
  });

  test('XSS in collection name sanitized', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Collections');

    // Attempt to create a collection with a script-tag name
    const xssPayload = '<script>alert("xss")</script>';

    // Open create collection modal
    await page.click('button:has-text("Create Collection")');
    await expect(page.locator('h3:has-text("Create Collection")')).toBeVisible({ timeout: 5_000 });

    // Fill with XSS payload
    await page.fill('input[x-model="newCollection.name"]', xssPayload);

    // Submit the form
    await page.click('div:has(h3:text("Create Collection")) button[type="submit"]');
    await page.waitForTimeout(2_000);

    // Check that no alert dialog was triggered by the XSS payload
    // If the script executed, there would be an unhandled dialog.
    // Also check the page content does not contain unescaped script tags in the DOM
    const pageContent = await page.content();

    // The raw <script> tag should NOT appear in rendered content as executable HTML.
    // Alpine.js uses x-text which auto-escapes, so the content should be text-only.
    // We check that there is no <script>alert("xss")</script> in the page body
    // (outside of x-text attributes which are safe).
    const scriptTagInBody = pageContent.includes('<script>alert("xss")</script>');

    // The collection name may appear in the page but should be escaped (as text, not HTML)
    // If it appears, it should be inside text nodes, not as executable script
    expect(scriptTagInBody).toBeFalsy();

    // Cleanup: try to delete the collection if it was created
    try {
      await fetch(
        `${GATEWAY_URL}/api/qdrant/collections/${encodeURIComponent(xssPayload)}`,
        { method: 'DELETE' },
      );
    } catch {
      // Best-effort cleanup
    }
  });

  test('session storage used for authentication', async ({ page }) => {
    await login(page);

    // Verify session storage has the login flag
    const isLoggedIn = await page.evaluate(() => {
      return sessionStorage.getItem('ollqd_logged_in');
    });
    expect(isLoggedIn).toBe('1');

    // Verify username is stored
    const username = await page.evaluate(() => {
      return sessionStorage.getItem('ollqd_user');
    });
    expect(username).toBe('testuser');
  });

  test('logout clears session', async ({ page }) => {
    await login(page);

    // Click Sign Out
    await page.click('button:has-text("Sign Out")');
    await page.waitForTimeout(1_000);

    // Verify we are back to the login screen
    await expect(page.locator('input[x-model="loginForm.username"]')).toBeVisible({
      timeout: 5_000,
    });

    // Verify session storage is cleared
    const isLoggedIn = await page.evaluate(() => {
      return sessionStorage.getItem('ollqd_logged_in');
    });
    expect(isLoggedIn).toBeNull();
  });

  test('empty username shows error', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('input[x-model="loginForm.username"]', {
      state: 'visible',
      timeout: 15_000,
    });

    // Submit without entering username
    await page.click('button[type="submit"]');

    // Error message should appear
    await expect(page.locator('text=Please enter a username')).toBeVisible({ timeout: 5_000 });
  });
});
