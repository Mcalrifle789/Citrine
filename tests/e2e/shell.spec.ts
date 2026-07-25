import { _electron as electron, expect, test } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'

// package.json sets "type": "module", so Playwright loads this file as ESM
// where __dirname does not exist.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

test('shell launches, connects, and routes through the Python backend', async () => {
  const citrineHome = mkdtempSync(resolve(tmpdir(), 'citrine-e2e-'))
  mkdirSync(citrineHome, { recursive: true })
  writeFileSync(
    resolve(citrineHome, 'config.json'),
    JSON.stringify({
      username: 'e2e',
      password_hash: '',
      password_salt: '',
      providers: [
        {
          id: 'custom',
          label: 'OpenRouter',
          base_url: null,
          model: 'openai/gpt-4o-mini',
        },
      ],
      active_provider_id: 'custom',
      search_provider: null,
      music_plugins: [],
      theme: 'citrine',
      active_session: 'main',
      sessions: ['main'],
      token_usage: {},
      active_agent: 'Default',
      agents: [{ name: 'Default', provider_id: 'custom', model: 'openai/gpt-4o-mini' }],
    }),
  )
  const app = await electron.launch({
    args: [resolve(root, 'out/main/main.js')],
    cwd: root,
    env: { ...process.env, CITRINE_HOME: citrineHome },
  })
  const window = await app.firstWindow()

  // The status bar reports a live backend connection. Scoped to the status
  // role because the rail's Status panel shows the same word.
  await expect(
    window.getByRole('status').getByText('connected'),
  ).toBeVisible({ timeout: 30_000 })

  // The empty state shows before any input.
  await expect(window.getByTestId('scrollback')).toContainText('How can I help you')

  await expect(window.getByText('Commands: 66')).toBeVisible()
  await expect(window.getByText('OpenRouter · openai/gpt-4o-mini · 0/128k')).toBeVisible()

  await window.getByRole('textbox', { name: 'Citrine prompt' }).fill('/model ')
  await expect(window.getByRole('listbox', { name: 'Command suggestions' })).toBeVisible()
  await window.getByRole('button', { name: 'openai/gpt-4o-mini', exact: true }).click()
  await expect(window.getByRole('textbox', { name: 'Citrine prompt' })).toHaveValue('/model openai/gpt-4o-mini')

  await window.getByRole('button', { name: 'Insert /session command' }).click()
  await expect(window.getByRole('textbox', { name: 'Citrine prompt' })).toHaveValue('/session ')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')
  await expect(window.locator('[data-kind="output"]').last()).toContainText('Sessions')

  await window.getByRole('button', { name: 'Insert /searchsetup command' }).click()
  await expect(window.getByRole('textbox', { name: 'Citrine prompt' })).toHaveValue('/searchsetup ')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')
  await expect(window.locator('[data-kind="output"]').last()).toContainText('DuckDuckGo')

  await window.getByRole('button', { name: 'Insert /theme command' }).click()
  await expect(window.getByRole('textbox', { name: 'Citrine prompt' })).toHaveValue('/theme ')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).fill('/theme matrix')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')
  await expect(window.locator('[data-kind="output"]').last()).toContainText('Theme switched')

  // A full round trip: renderer -> WebSocket -> Python -> chat router.
  await window.getByRole('textbox', { name: 'Citrine prompt' }).fill('spine check')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')

  await expect(window.getByTestId('scrollback')).toContainText('> spine check')
  await expect(window.locator('[data-kind="output"]').last()).toContainText('needs a base URL')
  await expect(window.locator('.ct-prompt__meta')).toContainText(/OpenRouter · openai\/gpt-4o-mini · [1-9][0-9]*\/128k/)

  await app.close()
})
