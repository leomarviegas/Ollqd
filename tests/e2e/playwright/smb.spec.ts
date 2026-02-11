import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

// SMB tests can be skipped if SMB is not configured in the environment.
const SMB_ENABLED = process.env.SMB_ENABLED === '1' || process.env.SMB_ENABLED === 'true';

test.describe('SMB Shares', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'SMB Shares');
  });

  test('SMB page renders form', async ({ page }) => {
    // The heading should be visible
    await expect(page.locator('h2:has-text("SMB/CIFS Network Shares")')).toBeVisible();

    // Verify the "Add Network Share" section
    await expect(page.locator('h3:has-text("Add Network Share")')).toBeVisible();

    // Verify form fields
    const serverInput = page.locator('input[x-model="smbForm.server"]');
    await expect(serverInput).toBeVisible();
    await expect(serverInput).toHaveAttribute('placeholder', '192.168.1.100 or hostname');

    const shareInput = page.locator('input[x-model="smbForm.share"]');
    await expect(shareInput).toBeVisible();
    await expect(shareInput).toHaveAttribute('placeholder', 'documents');

    const usernameInput = page.locator('input[x-model="smbForm.username"]');
    await expect(usernameInput).toBeVisible();

    const passwordInput = page.locator('input[x-model="smbForm.password"]');
    await expect(passwordInput).toBeVisible();

    // Domain, Port, Label fields
    const domainInput = page.locator('input[x-model="smbForm.domain"]');
    await expect(domainInput).toBeVisible();

    const portInput = page.locator('input[x-model\\.number="smbForm.port"]');
    await expect(portInput).toBeVisible();

    const labelInput = page.locator('input[x-model="smbForm.label"]');
    await expect(labelInput).toBeVisible();
  });

  test('SMB test connection button exists', async ({ page }) => {
    const testButton = page.locator('button:has-text("Test Connection")');
    await expect(testButton).toBeVisible();
  });

  test('SMB add share button exists', async ({ page }) => {
    const addButton = page.locator('button:has-text("Add Share")');
    await expect(addButton).toBeVisible();
    // Should be disabled when server and share are empty
    await expect(addButton).toBeDisabled();
  });

  test('SMB configured shares section renders', async ({ page }) => {
    // The "Configured Shares" section should be visible
    await expect(page.locator('h3:has-text("Configured Shares")')).toBeVisible();

    // Either shows existing shares or the empty state message
    const emptyMessage = page.locator('text=No shares configured yet');
    const shareCards = page.locator(
      'div:has(h3:text("Configured Shares")) >> div.border.border-gray-200.rounded-lg.p-3',
    );

    const hasShares = (await shareCards.count()) > 0;
    const hasEmptyMessage = await emptyMessage.isVisible().catch(() => false);

    // One of these should be true
    expect(hasShares || hasEmptyMessage).toBeTruthy();
  });

  test('SMB add share enables button when fields filled', async ({ page }) => {
    const addButton = page.locator('button:has-text("Add Share")');

    // Initially disabled
    await expect(addButton).toBeDisabled();

    // Fill required fields
    await page.fill('input[x-model="smbForm.server"]', '192.168.1.100');
    await page.fill('input[x-model="smbForm.share"]', 'testshare');

    // Button should now be enabled
    await expect(addButton).toBeEnabled();
  });

  test('SMB test connection attempt', async ({ page }) => {
    test.skip(!SMB_ENABLED, 'SMB test connection requires SMB_ENABLED=1');

    // Fill connection details
    await page.fill('input[x-model="smbForm.server"]', process.env.SMB_SERVER || '192.168.1.1');
    await page.fill('input[x-model="smbForm.share"]', process.env.SMB_SHARE || 'public');

    // Click Test Connection
    await page.click('button:has-text("Test Connection")');

    // Wait for result
    await page.waitForTimeout(5_000);

    // Result should be visible (either success or failure)
    const resultArea = page.locator('[x-show="smbTestResult"]');
    await expect(resultArea).toBeVisible({ timeout: 10_000 });
  });
});
