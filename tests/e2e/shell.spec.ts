import { _electron as electron, expect, test } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// package.json sets "type": "module", so Playwright loads this file as ESM
// where __dirname does not exist.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

test('shell launches, connects, and echoes through the Python backend', async () => {
  const app = await electron.launch({ args: [resolve(root, 'out/main/main.js')], cwd: root })
  const window = await app.firstWindow()

  // The status bar reports a live backend connection. Scoped to the status
  // role because the rail's Status panel shows the same word.
  await expect(
    window.getByRole('status').getByText('connected'),
  ).toBeVisible({ timeout: 30_000 })

  // The empty state shows before any input.
  await expect(window.getByTestId('scrollback')).toContainText('How can I help you')

  await expect(window.getByText('Commands: 66')).toBeVisible()

  await window.getByRole('button', { name: 'Insert /sessions command' }).click()
  await expect(window.getByRole('textbox', { name: 'Citrine prompt' })).toHaveValue('/sessions ')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')
  await expect(window.locator('[data-kind="output"]').last()).toContainText('Agent sessions')

  await window.getByRole('button', { name: 'Insert /searchsetup command' }).click()
  await expect(window.getByRole('textbox', { name: 'Citrine prompt' })).toHaveValue('/searchsetup ')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')
  await expect(window.locator('[data-kind="output"]').last()).toContainText('DuckDuckGo')

  // A full round trip: renderer -> WebSocket -> Python -> back.
  await window.getByRole('textbox', { name: 'Citrine prompt' }).fill('spine check')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')

  await expect(window.getByTestId('scrollback')).toContainText('> spine check')
  await expect(window.locator('[data-kind="output"]').last()).toHaveText('spine check')

  await app.close()
})
