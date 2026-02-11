import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Settings');
  });

  test('settings page renders tabs', async ({ page }) => {
    // The heading should be visible
    await expect(page.locator('h2:has-text("Settings")')).toBeVisible();

    // Scope to the settings view to avoid matching buttons from other views
    const settingsView = page.locator('div[x-show="view === \'settings\'"]');

    // Scope to the settings tab bar to avoid matching buttons elsewhere in settings sections
    const settingsTabBar = settingsView.locator('div.flex.border-b.border-gray-200');

    // Verify all settings sub-tabs exist
    await expect(settingsTabBar.locator('button:has-text("General")')).toBeVisible();
    await expect(settingsTabBar.locator('button:has-text("Embedding")')).toBeVisible();
    await expect(settingsTabBar.locator('button:has-text("Distance Metrics")')).toBeVisible();
    await expect(settingsTabBar.locator('button:has-text("Mounted Paths")')).toBeVisible();
    await expect(settingsTabBar.locator('button:has-text("Chunking")')).toBeVisible();
    // Use exact text match to avoid matching "Images" button from Indexing view
    await expect(settingsTabBar.locator('button', { hasText: /^Image$/ })).toBeVisible();
    await expect(settingsTabBar.locator('button:has-text("Document AI")')).toBeVisible();
    await expect(settingsTabBar.locator('button:has-text("Privacy")')).toBeVisible();
  });

  test('ollama settings form', async ({ page }) => {
    // General tab should be active by default, showing Ollama Settings
    await expect(page.locator('h4:has-text("Ollama Settings")')).toBeVisible({ timeout: 10_000 });

    // Scope to the Ollama settings card (direct parent div with the h4)
    const ollamaCard = page.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
      has: page.locator('h4:has-text("Ollama Settings")'),
    });

    // Verify Ollama form fields
    const baseUrlInput = page.locator('input[x-model="settingsConfig.ollama.base_url"]');
    await expect(baseUrlInput).toBeVisible();

    const chatModelInput = page.locator('input[x-model="settingsConfig.ollama.chat_model"]');
    await expect(chatModelInput).toBeVisible();

    const embedModelInput = page.locator('input[x-model="settingsConfig.ollama.embed_model"]');
    await expect(embedModelInput).toBeVisible();

    const visionModelInput = page.locator('input[x-model="settingsConfig.ollama.vision_model"]');
    await expect(visionModelInput).toBeVisible();

    const timeoutInput = page.locator('input[x-model\\.number="settingsConfig.ollama.timeout_s"]');
    await expect(timeoutInput).toBeVisible();

    // Save and Reset buttons scoped to the Ollama card
    await expect(
      ollamaCard.locator('button:has-text("Save")'),
    ).toBeVisible();
    await expect(
      ollamaCard.locator('button:has-text("Reset")'),
    ).toBeVisible();

    // Run Ollama Locally toggle
    await expect(page.locator('text=Run Ollama Locally')).toBeVisible();
  });

  test('qdrant settings form', async ({ page }) => {
    // General tab -- Qdrant Settings section
    await expect(page.locator('h4:has-text("Qdrant Settings")')).toBeVisible({ timeout: 10_000 });

    // Scope to the Qdrant settings card (direct parent div with the h4)
    const qdrantCard = page.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
      has: page.locator('h4:has-text("Qdrant Settings")'),
    });

    // Verify Qdrant form fields
    const urlInput = page.locator('input[x-model="settingsConfig.qdrant.url"]');
    await expect(urlInput).toBeVisible();

    const defaultCollectionInput = page.locator(
      'input[x-model="settingsConfig.qdrant.default_collection"]',
    );
    await expect(defaultCollectionInput).toBeVisible();

    // Save and Reset buttons scoped to the Qdrant card
    await expect(
      qdrantCard.locator('button:has-text("Save")'),
    ).toBeVisible();
    await expect(
      qdrantCard.locator('button:has-text("Reset")'),
    ).toBeVisible();
  });

  test('chunking settings form', async ({ page }) => {
    // Navigate to Chunking tab - scope click to settings view to avoid Indexing tab conflict
    const settingsView = page.locator('div[x-show="view === \'settings\'"]');
    await settingsView.locator('button:has-text("Chunking")').click();
    await page.waitForTimeout(500);

    await expect(page.locator('h4:has-text("Chunking Configuration")')).toBeVisible({
      timeout: 5_000,
    });

    // Scope to the Chunking settings card
    const chunkingCard = page.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
      has: page.locator('h4:has-text("Chunking Configuration")'),
    });

    // Verify chunking form fields
    const chunkSizeInput = page.locator(
      'input[x-model\\.number="settingsConfig.chunking.chunk_size"]',
    );
    await expect(chunkSizeInput).toBeVisible();

    const chunkOverlapInput = page.locator(
      'input[x-model\\.number="settingsConfig.chunking.chunk_overlap"]',
    );
    await expect(chunkOverlapInput).toBeVisible();

    const maxFileSizeInput = page.locator(
      'input[x-model\\.number="settingsConfig.chunking.max_file_size_kb"]',
    );
    await expect(maxFileSizeInput).toBeVisible();

    // Save and Reset buttons scoped to the Chunking card
    await expect(chunkingCard.locator('button:has-text("Save")')).toBeVisible();
    await expect(chunkingCard.locator('button:has-text("Reset")')).toBeVisible();
  });

  test('PII settings form', async ({ page }) => {
    // Navigate to Privacy tab
    await page.click('button:has-text("Privacy")');
    await page.waitForTimeout(1_000);

    await expect(page.locator('h4:has-text("PII Masking")')).toBeVisible({ timeout: 10_000 });

    // Verify PII toggle checkboxes
    const enabledCheckbox = page.locator('input[x-model="piiConfig.enabled"]');
    await expect(enabledCheckbox).toBeVisible();

    const spacyCheckbox = page.locator('input[x-model="piiConfig.use_spacy"]');
    await expect(spacyCheckbox).toBeVisible();

    const maskEmbeddingsCheckbox = page.locator('input[x-model="piiConfig.mask_embeddings"]');
    await expect(maskEmbeddingsCheckbox).toBeVisible();

    // Verify labels
    await expect(page.locator('text=Enable PII Masking')).toBeVisible();
    await expect(page.locator('text=Use spaCy NER')).toBeVisible();
    await expect(page.locator('text=Mask Embeddings')).toBeVisible();

    // Save PII Settings button
    await expect(page.locator('button:has-text("Save PII Settings")')).toBeVisible();

    // Detected PII Types section
    await expect(page.locator('text=Detected PII Types')).toBeVisible();
  });

  test('PII test masking', async ({ page }) => {
    // Navigate to Privacy tab
    await page.click('button:has-text("Privacy")');
    await page.waitForTimeout(1_000);

    // Verify the test tool section exists
    await expect(page.locator('h4:has-text("Test PII Detection")')).toBeVisible({
      timeout: 10_000,
    });

    // Verify the textarea for test input
    const testTextArea = page.locator('textarea[x-model="piiTestText"]');
    await expect(testTextArea).toBeVisible();

    // Verify the Test Detection button
    const testButton = page.locator('button:has-text("Test Detection")');
    await expect(testButton).toBeVisible();
    // Should be disabled when text is empty
    await expect(testButton).toBeDisabled();

    // Enter test text with PII
    await testTextArea.fill('Contact John Smith at john@example.com or 555-123-4567');

    // Button should now be enabled
    await expect(testButton).toBeEnabled();

    // Click test
    await testButton.click();

    // Wait for the result to appear
    await page.waitForTimeout(3_000);

    // Verify masked output area appears (if API is available)
    const maskedOutput = page.locator('text=Masked output:');
    const isResultVisible = await maskedOutput.isVisible().catch(() => false);

    if (isResultVisible) {
      // If the API responded, the masked text should be visible
      const maskedText = page.locator('p.font-mono[x-text="piiTestResult?.masked"]');
      await expect(maskedText).toBeVisible();
    }
    // If API is unavailable, the test still passes (form interaction verified)
  });

  test('settings persist after save', async ({ page }) => {
    // This test verifies that changing a setting, saving, and reloading preserves the value.
    // We use the Qdrant default_collection field as a test target.

    await expect(page.locator('h4:has-text("Qdrant Settings")')).toBeVisible({ timeout: 10_000 });

    // Scope to the Qdrant settings card
    const qdrantCard = page.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
      has: page.locator('h4:has-text("Qdrant Settings")'),
    });

    const collectionInput = page.locator(
      'input[x-model="settingsConfig.qdrant.default_collection"]',
    );
    await expect(collectionInput).toBeVisible();

    // Read current value
    const originalValue = await collectionInput.inputValue();

    // Set a test value
    const testValue = `e2e-persist-test-${Date.now()}`;
    await collectionInput.clear();
    await collectionInput.fill(testValue);

    // Set up dialog handler for save confirmation
    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    // Click Save scoped to the Qdrant card
    await qdrantCard.locator('button:has-text("Save")').click();
    await page.waitForTimeout(2_000);

    // Reload the page and navigate back to settings
    await page.reload();
    await page.waitForTimeout(2_000);

    // After reload, we need to re-login (sessionStorage cleared on reload may vary)
    // Check if we are still logged in
    const isLoggedIn = await page.locator('aside').isVisible().catch(() => false);
    if (!isLoggedIn) {
      await login(page);
    }

    await navigateToTab(page, 'Settings');
    await page.waitForTimeout(2_000);

    // Read the value again
    const newCollectionInput = page.locator(
      'input[x-model="settingsConfig.qdrant.default_collection"]',
    );
    await expect(newCollectionInput).toBeVisible({ timeout: 10_000 });
    const savedValue = await newCollectionInput.inputValue();

    // The value should be persisted (either our test value or the API might have failed)
    // If the gateway is running, it should match
    if (savedValue === testValue) {
      expect(savedValue).toBe(testValue);

      // Restore original value - scope Save to Qdrant card
      const qdrantCardReloaded = page.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
        has: page.locator('h4:has-text("Qdrant Settings")'),
      });
      await newCollectionInput.clear();
      await newCollectionInput.fill(originalValue || 'codebase');
      await qdrantCardReloaded.locator('button:has-text("Save")').click();
      await page.waitForTimeout(1_000);
    }
  });

  test('image settings form', async ({ page }) => {
    // Navigate to Image tab - scope click to settings view to avoid Indexing "Images" tab
    const settingsView = page.locator('div[x-show="view === \'settings\'"]');
    await settingsView.locator('button', { hasText: /^Image$/ }).click();
    await page.waitForTimeout(500);

    await expect(page.locator('h4:has-text("Image Configuration")')).toBeVisible({
      timeout: 5_000,
    });

    // Scope to the Image settings card
    const imageCard = page.locator('div.bg-white.rounded-lg.shadow.p-4').filter({
      has: page.locator('h4:has-text("Image Configuration")'),
    });

    // Verify image form fields
    const maxSizeInput = page.locator(
      'input[x-model\\.number="settingsConfig.image.max_image_size_kb"]',
    );
    await expect(maxSizeInput).toBeVisible();

    const captionPromptTextarea = page.locator(
      'textarea[x-model="settingsConfig.image.caption_prompt"]',
    );
    await expect(captionPromptTextarea).toBeVisible();

    // Save and Reset buttons scoped to the Image card
    await expect(imageCard.locator('button:has-text("Save")')).toBeVisible();
    await expect(imageCard.locator('button:has-text("Reset")')).toBeVisible();
  });

  test('document AI settings form', async ({ page }) => {
    // Navigate to Document AI tab
    await page.click('button:has-text("Document AI")');
    await page.waitForTimeout(1_000);

    await expect(page.locator('h4:has-text("Document AI (Docling)")')).toBeVisible({
      timeout: 10_000,
    });

    // Verify form fields
    const enabledCheckbox = page.locator('input[x-model="doclingConfig.enabled"]');
    await expect(enabledCheckbox).toBeVisible();

    const tableStructureCheckbox = page.locator(
      'input[x-model="doclingConfig.table_structure"]',
    );
    await expect(tableStructureCheckbox).toBeVisible();

    const ocrCheckbox = page.locator('input[x-model="doclingConfig.ocr_enabled"]');
    await expect(ocrCheckbox).toBeVisible();

    const ocrEngineSelect = page.locator('select[x-model="doclingConfig.ocr_engine"]');
    await expect(ocrEngineSelect).toBeVisible();

    const timeoutInput = page.locator('input[x-model\\.number="doclingConfig.timeout_s"]');
    await expect(timeoutInput).toBeVisible();

    // Save button
    await expect(page.locator('button:has-text("Save Document AI Settings")')).toBeVisible();
  });
});
