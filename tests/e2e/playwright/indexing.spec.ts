import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

test.describe('Indexing', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Indexing');
  });

  test('indexing page renders tabs', async ({ page }) => {
    // The heading should be visible
    await expect(page.locator('h2:has-text("Indexing")')).toBeVisible();

    // Scope to the indexing view to avoid matching buttons from other views
    const indexingView = page.locator('div[x-show="view === \'indexing\'"]');

    // Verify the indexing sub-tabs exist: Codebase, Images, Upload
    // Scope to the tab bar to avoid matching buttons with similar text elsewhere in the view
    const indexTabBar = indexingView.locator('div.flex.border-b.border-gray-200');
    await expect(indexTabBar.locator('button:has-text("Codebase")')).toBeVisible();
    await expect(indexTabBar.locator('button:has-text("Images")')).toBeVisible();
    await expect(indexTabBar.locator('button:has-text("Upload")')).toBeVisible();
  });

  test('codebase indexing form', async ({ page }) => {
    // Codebase tab should be active by default
    // Verify form fields exist
    const rootPathInput = page.locator('input[x-model="indexForm.root_path"]');
    await expect(rootPathInput).toBeVisible();
    await expect(rootPathInput).toHaveAttribute('placeholder', '/path/to/project');

    const collectionInput = page.locator('input[x-model="indexForm.collection"]');
    await expect(collectionInput).toBeVisible();

    // Chunk size and overlap fields
    const chunkSizeInput = page.locator('input[x-model\\.number="indexForm.chunk_size"]');
    await expect(chunkSizeInput).toBeVisible();

    const chunkOverlapInput = page.locator('input[x-model\\.number="indexForm.chunk_overlap"]');
    await expect(chunkOverlapInput).toBeVisible();

    // Incremental checkbox
    const incrementalCheckbox = page.locator('input[x-model="indexForm.incremental"]');
    await expect(incrementalCheckbox).toBeVisible();

    // Start Indexing button
    await expect(page.locator('button:has-text("Start Indexing")')).toBeVisible();
  });

  test('images indexing form', async ({ page }) => {
    // Click Images tab
    await page.click('button:has-text("Images")');
    await page.waitForTimeout(500);

    // Verify form fields for image indexing
    const rootPathInput = page.locator('input[x-model="imageIndexForm.root_path"]');
    await expect(rootPathInput).toBeVisible();

    const collectionInput = page.locator('input[x-model="imageIndexForm.collection"]');
    await expect(collectionInput).toBeVisible();

    // Vision model selector
    const visionModelSelect = page.locator('select[x-model="imageIndexForm.vision_model"]');
    await expect(visionModelSelect).toBeVisible();

    // Incremental checkbox
    const incrementalCheckbox = page.locator('input[x-model="imageIndexForm.incremental"]');
    await expect(incrementalCheckbox).toBeVisible();

    // Start Image Indexing button
    await expect(page.locator('button:has-text("Start Image Indexing")')).toBeVisible();
  });

  test('upload area exists', async ({ page }) => {
    // Click Upload tab
    await page.click('button:has-text("Upload")');
    await page.waitForTimeout(500);

    // Verify the drag-and-drop zone exists
    const dropZone = page.locator('text=Drag & drop files here or click to browse');
    await expect(dropZone).toBeVisible();

    // Verify supported file types text
    await expect(page.locator('text=Supports:')).toBeVisible();

    // Verify the hidden file input exists
    const fileInput = page.locator('input[type="file"][x-ref="uploadInput"]');
    await expect(fileInput).toBeAttached();

    // Verify upload options (collection, chunk size, chunk overlap)
    const uploadCollection = page.locator('input[x-model="uploadCollection"]');
    await expect(uploadCollection).toBeVisible();

    const uploadChunkSize = page.locator('input[x-model\\.number="uploadChunkSize"]');
    await expect(uploadChunkSize).toBeVisible();

    const uploadChunkOverlap = page.locator('input[x-model\\.number="uploadChunkOverlap"]');
    await expect(uploadChunkOverlap).toBeVisible();

    // Upload & Index button (disabled when no files)
    const uploadButton = page.locator('button:has-text("Upload & Index")');
    await expect(uploadButton).toBeVisible();
    await expect(uploadButton).toBeDisabled();
  });

  test('task list renders', async ({ page }) => {
    // Scope to the indexing view
    const indexingView = page.locator('div[x-show="view === \'indexing\'"]');

    // The Tasks section should be visible on the indexing page
    await expect(indexingView.locator('h3:has-text("Tasks")')).toBeVisible();

    // Verify task filter dropdown exists
    const taskFilter = page.locator('select[x-model="taskFilter"]');
    await expect(taskFilter).toBeVisible();

    // Verify task control buttons exist - scope to the Tasks section within indexing
    const tasksSection = indexingView.locator('div.bg-white.rounded-lg.shadow.p-6').filter({
      has: page.locator('h3:has-text("Tasks")'),
    });
    await expect(tasksSection.locator('button:has-text("Refresh")')).toBeVisible();
    await expect(tasksSection.locator('button:has-text("Clear")')).toBeVisible();

    // Verify auto-refresh checkbox exists
    const autoRefreshCheckbox = tasksSection.locator('input[type="checkbox"]').first();
    await expect(autoRefreshCheckbox).toBeAttached();
  });

  test('mounted paths section exists', async ({ page }) => {
    // Scope to the indexing view
    const indexingView = page.locator('div[x-show="view === \'indexing\'"]');

    // The "Available Paths" section should be visible at the top of the indexing page
    await expect(indexingView.locator('text=Available Paths')).toBeVisible();

    // Verify the path input and Add button - scope to the mounted paths section
    const mountedPathsSection = indexingView.locator('div.bg-blue-50');
    const pathInput = mountedPathsSection.locator('input[x-model="newMountedPath"]');
    await expect(pathInput).toBeVisible();
    await expect(mountedPathsSection.locator('button:has-text("Add")')).toBeVisible();
  });
});
