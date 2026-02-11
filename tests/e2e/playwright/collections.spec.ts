import { test, expect } from '@playwright/test';
import { login, navigateToTab, uniqueCollectionName, GATEWAY_URL } from './helpers';

test.describe('Collections', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Collections');
  });

  test('collections page loads', async ({ page }) => {
    // The heading should be visible
    await expect(page.locator('h2:has-text("Collections")')).toBeVisible();
    // The "Create Collection" button should be present
    await expect(page.locator('button:has-text("Create Collection")')).toBeVisible();
  });

  test('create collection via UI', async ({ page }) => {
    const collectionName = uniqueCollectionName();

    // Click "Create Collection" button
    await page.click('button:has-text("Create Collection")');

    // Wait for the modal to appear
    await expect(page.locator('h3:has-text("Create Collection")')).toBeVisible({ timeout: 5_000 });

    // Fill the form
    await page.fill('input[x-model="newCollection.name"]', collectionName);
    // Vector size and distance should have defaults, but verify they exist
    await expect(page.locator('input[x-model\\.number="newCollection.vector_size"]')).toBeVisible();
    await expect(page.locator('select[x-model="newCollection.distance"]')).toBeVisible();

    // Submit the form - use the modal's submit button (type="submit" inside the modal form)
    const modal = page.locator('div[x-show="showModal === \'create-collection\'"]');
    await modal.locator('button[type="submit"]').click();

    // Wait for the collection to appear in the Collections list (not the Dashboard table)
    await page.waitForTimeout(2_000);
    const collectionsView = page.locator('div[x-show="view === \'collections\'"]');
    await expect(collectionsView.locator(`text=${collectionName}`).first()).toBeVisible({ timeout: 10_000 });

    // Cleanup: delete the collection via API
    try {
      await fetch(`${GATEWAY_URL}/api/qdrant/collections/${encodeURIComponent(collectionName)}`, {
        method: 'DELETE',
      });
    } catch {
      // Best-effort cleanup
    }
  });

  test('delete collection via UI', async ({ page }) => {
    const collectionName = uniqueCollectionName('e2e-del');

    // Create a collection via API first
    const createResponse = await fetch(`${GATEWAY_URL}/api/qdrant/collections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: collectionName, vector_size: 1024, distance: 'Cosine' }),
    });

    // If API is not reachable, skip the test
    if (!createResponse.ok) {
      test.skip(true, 'Gateway API not reachable for collection setup');
      return;
    }

    // Reload collections
    await navigateToTab(page, 'Dashboard');
    await page.waitForTimeout(1_000);
    await navigateToTab(page, 'Collections');
    await page.waitForTimeout(1_000);

    // Verify collection appears in the Collections view (not the Dashboard table)
    const collectionsView = page.locator('div[x-show="view === \'collections\'"]');
    await expect(collectionsView.locator(`text=${collectionName}`).first()).toBeVisible({ timeout: 10_000 });

    // Set up dialog handler for the confirmation prompt
    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });
    const collectionRow = collectionsView.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
      has: page.locator(`text=${collectionName}`),
    });
    await collectionRow.locator('button:has-text("Delete")').click();

    // Wait for deletion to complete
    await page.waitForTimeout(2_000);

    // Verify collection is removed
    await expect(page.locator(`p.font-medium:has-text("${collectionName}")`)).not.toBeVisible({
      timeout: 10_000,
    });
  });

  test('collection shows point count', async ({ page }) => {
    // Wait for collection list to load
    await page.waitForTimeout(2_000);

    // Each collection card shows "X points" text
    const collectionCards = page.locator('div.bg-white.rounded-lg.shadow.p-4');
    const count = await collectionCards.count();

    if (count > 0) {
      // Verify the first collection card has a points display
      const firstCard = collectionCards.first();
      const pointsText = firstCard.locator('p.text-sm.text-gray-500');
      await expect(pointsText).toBeVisible();
      const text = await pointsText.textContent();
      // Should contain "points" text
      expect(text).toContain('points');
    }
    // If no collections exist, the test is still valid (nothing to verify)
  });

  test('collection has browse and search buttons', async ({ page }) => {
    await page.waitForTimeout(2_000);

    const collectionCards = page.locator('div.bg-white.rounded-lg.shadow.p-4');
    const count = await collectionCards.count();

    if (count > 0) {
      const firstCard = collectionCards.first();
      await expect(firstCard.locator('button:has-text("Browse")')).toBeVisible();
      await expect(firstCard.locator('button:has-text("Search")')).toBeVisible();
      await expect(firstCard.locator('button:has-text("Delete")')).toBeVisible();
    }
  });
});
