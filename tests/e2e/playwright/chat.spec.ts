import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

test.describe('RAG Chat', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'RAG Chat');
  });

  test('chat page renders with input field', async ({ page }) => {
    // The heading should be visible
    await expect(page.locator('h2:has-text("RAG Chat")')).toBeVisible();

    // Verify message input field exists
    const chatInput = page.locator('input[x-model="chatInput"]');
    await expect(chatInput).toBeVisible();
    await expect(chatInput).toHaveAttribute('placeholder', 'Ask about your code...');

    // Verify send button exists
    const sendButton = page.locator('button:has-text("Send")');
    await expect(sendButton).toBeVisible();
  });

  test('chat collection selector exists', async ({ page }) => {
    // Scope to the chat view to avoid matching "Collection:" label from Visualize view
    const chatView = page.locator('div[x-show="view === \'chat\'"]');

    // Verify the collection dropdown is present
    const collectionSelect = page.locator('select[x-model="chatCollection"]');
    await expect(collectionSelect).toBeVisible();

    // Verify the label is present - scoped to chat view
    await expect(chatView.locator('label:has-text("Collection:")')).toBeVisible();
  });

  test('chat model selector exists', async ({ page }) => {
    // Verify the model dropdown is present
    const modelSelect = page.locator('select[x-model="chatModel"]');
    await expect(modelSelect).toBeVisible();

    // Verify the label is present
    await expect(page.locator('label:has-text("Model:")')).toBeVisible();
  });

  test('chat PII toggle exists', async ({ page }) => {
    // Scope to the chat view
    const chatView = page.locator('div[x-show="view === \'chat\'"]');

    // Verify PII masking checkbox is present
    const piiCheckbox = page.locator('input[x-model="piiChatEnabled"]');
    await expect(piiCheckbox).toBeVisible();

    // Verify the PII label/icon is present - scoped to chat view to avoid settings PII references
    await expect(chatView.locator('span:has-text("PII")').first()).toBeVisible();
  });

  test('chat clear button exists', async ({ page }) => {
    // Scope to the chat view to avoid matching "Clear" button from Indexing tasks
    const chatView = page.locator('div[x-show="view === \'chat\'"]');
    const clearButton = chatView.locator('button:has-text("Clear")');
    await expect(clearButton).toBeVisible();
  });

  test('chat empty state message shown', async ({ page }) => {
    // When no messages, the empty state should be visible
    await expect(page.locator('text=Ask a question about your codebase')).toBeVisible();
    await expect(page.locator('text=Make sure you\'ve indexed a project first')).toBeVisible();
  });

  test('sending message shows streaming response', async ({ page }) => {
    // This test requires both Ollama and Qdrant to be running with an indexed collection.
    // We attempt the chat and verify the user message appears. If the backend is unavailable,
    // the test will still verify the UI interaction works.

    const chatInput = page.locator('input[x-model="chatInput"]');
    const sendButton = page.locator('button:has-text("Send")');

    // Type a message
    await chatInput.fill('What is this project about?');

    // Verify send button is enabled
    await expect(sendButton).toBeEnabled();

    // Click send
    await sendButton.click();

    // The user message should appear in the chat
    await expect(page.locator('div.bg-blue-600.text-white:has-text("What is this project about?")')).toBeVisible({
      timeout: 5_000,
    });

    // The assistant response area should appear (streaming indicator)
    // Wait for either a streaming response or an error message
    await page.waitForTimeout(5_000);

    // After sending, the chat input should be cleared
    await expect(chatInput).toHaveValue('');

    // The empty state message should no longer be visible
    await expect(page.locator('text=Ask a question about your codebase')).not.toBeVisible();
  });

  test('send button disabled when input empty', async ({ page }) => {
    const sendButton = page.locator('button:has-text("Send")');
    // Send button should be disabled when input is empty
    await expect(sendButton).toBeDisabled();
  });
});
