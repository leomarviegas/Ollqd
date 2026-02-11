import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

test.describe('Visualize', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Visualize');
  });

  test('visualize page renders tabs', async ({ page }) => {
    // The heading should be visible
    await expect(page.locator('h2:has-text("Visualize")')).toBeVisible();

    // Verify all three visualization sub-tabs
    await expect(page.locator('button:has-text("Collection Overview")')).toBeVisible();
    await expect(page.locator('button:has-text("Vector Space 3D")')).toBeVisible();
    await expect(page.locator('button:has-text("File Tree")')).toBeVisible();
  });

  test('visualization collection selector', async ({ page }) => {
    // Scope to the visualize view to avoid matching "Collection:" label from Chat view
    const vizView = page.locator('div[x-show="view === \'visualize\'"]');

    // Verify the collection dropdown exists
    const collectionSelect = page.locator('select[x-model="vizCollection"]');
    await expect(collectionSelect).toBeVisible();

    // Verify the label - scoped to visualize view
    await expect(vizView.locator('label:has-text("Collection:")')).toBeVisible();
  });

  test('visualization renders overview container', async ({ page }) => {
    // The overview tab should be active by default
    // Verify the overview container element exists
    const overviewContainer = page.locator('#viz-overview-container');
    await expect(overviewContainer).toBeAttached();

    // Scope to the overview sub-tab section
    const overviewSection = page.locator('div[x-show="vizTab === \'overview\'"]');

    // Verify the limit input and Load button exist - scoped to overview tab
    const limitInput = overviewSection.locator('input[x-model\\.number="vizLimit"]');
    await expect(limitInput).toBeVisible();

    const loadButton = overviewSection.locator('button').filter({ hasText: 'Load' }).first();
    await expect(loadButton).toBeVisible();
  });

  test('vector space 3D tab renders', async ({ page }) => {
    // Click Vector Space 3D tab - scope to visualize view
    const vizView = page.locator('div[x-show="view === \'visualize\'"]');
    await vizView.locator('button:has-text("Vector Space 3D")').click();
    await page.waitForTimeout(500);

    // Verify the vectors container element exists
    const vectorsContainer = page.locator('#viz-vectors-container');
    await expect(vectorsContainer).toBeAttached();

    // Scope to the vectors sub-tab section
    const vectorsSection = page.locator('div[x-show="vizTab === \'vectors\'"]');

    // Verify the method selector
    const methodSelect = page.locator('select[x-model="vizMethod"]');
    await expect(methodSelect).toBeVisible();

    // Verify PCA and t-SNE options
    await expect(methodSelect.locator('option[value="pca"]')).toBeAttached();
    await expect(methodSelect.locator('option[value="tsne"]')).toBeAttached();

    // Verify the Load button - scoped to vectors section
    const loadButton = vectorsSection.locator('button').filter({ hasText: 'Load' }).first();
    await expect(loadButton).toBeVisible();
  });

  test('file tree tab renders', async ({ page }) => {
    // Click File Tree tab
    await page.click('button:has-text("File Tree")');
    await page.waitForTimeout(500);

    // Verify the filetree container element exists
    const filetreeContainer = page.locator('#viz-filetree-container');
    await expect(filetreeContainer).toBeAttached();

    // Verify the file selector dropdown
    const fileSelect = page.locator('select[x-model="vizSelectedFile"]');
    await expect(fileSelect).toBeVisible();

    // The Load button should exist but be disabled (no file selected by default)
    const loadButton = page
      .locator('div:has(#viz-filetree-container)')
      .locator('button:has-text("Load")')
      .first();
    if (await loadButton.isVisible()) {
      await expect(loadButton).toBeDisabled();
    }
  });
});
