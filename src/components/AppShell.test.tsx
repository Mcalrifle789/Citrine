import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The shell: the command rail is gone, files can be dropped, and a turn in
 * flight is visible.
 *
 * The transport is faked rather than stood up, so these exercise the shell's
 * own behaviour. The real socket round trip is covered end to end in
 * tests/e2e/shell.spec.ts.
 */

const requests: Array<{ method: string; params: Record<string, unknown> }> = []
let resolveChat: ((value: { text: string }) => void) | null = null

const CATALOG = [
  { name: 'theme', description: 'Switch visual themes' },
  { name: 'status', description: 'Show current system status' },
  { name: 'github', description: 'Create a GitHub repository' },
]

const STATUS = {
  provider: 'OpenRouter',
  provider_id: 'custom',
  model: 'openai/gpt-4o-mini',
  tokens: '0/128k',
  token_used: 0,
  token_total: 128000,
  session: 'main',
  sessions: ['main'],
  transcript_key: 'Default::main#0',
  agent: 'Default',
  agents: ['Default'],
  providers: [{ id: 'custom', label: 'OpenRouter', model: 'openai/gpt-4o-mini' }],
  models: ['openai/gpt-4o-mini'],
}

vi.mock('../lib/transport', () => {
  class Transport {
    private listeners: Array<(s: string) => void> = []
    onStateChange(cb: (s: string) => void) {
      this.listeners.push(cb)
    }
    getState() {
      return 'open'
    }
    async connect() {
      for (const cb of this.listeners) cb('open')
    }
    request(method: string, params: Record<string, unknown> = {}) {
      requests.push({ method, params })
      if (method === 'app.status') return Promise.resolve(STATUS)
      if (method === 'app.commands') return Promise.resolve({ commands: CATALOG })
      if (method === 'chat.send') {
        return new Promise((resolve) => {
          resolveChat = resolve as (value: { text: string }) => void
        })
      }
      return Promise.resolve({ text: 'ok' })
    }
    close() {}
  }
  return { Transport }
})

const { AppShell } = await import('./AppShell')
const { useAppStore } = await import('../lib/store')

function textFile(name: string, body: string): File {
  return new File([body], name, { type: 'text/plain' })
}

function drop(files: File[]): void {
  const app = document.querySelector('.ct-app') as HTMLElement
  const dataTransfer = { files, items: [], types: ['Files'] }
  fireEvent.dragEnter(app, { dataTransfer })
  fireEvent.drop(app, { dataTransfer })
}

async function ready(): Promise<void> {
  await waitFor(() => expect(requests.some((r) => r.method === 'app.commands')).toBe(true))
}

beforeEach(() => {
  requests.length = 0
  resolveChat = null
  useAppStore.getState().reset()
  Object.defineProperty(window, 'citrine', {
    value: { getBackendInfo: () => Promise.resolve({ port: 1234, token: 't' }) },
    configurable: true,
  })
})

describe('the command rail is gone', () => {
  it('does not render a command list', async () => {
    render(<AppShell />)
    await ready()
    expect(document.querySelector('.ct-cmdlist')).toBeNull()
  })

  it('does not render the rail at all', async () => {
    render(<AppShell />)
    await ready()
    expect(document.querySelector('.ct-app__rail')).toBeNull()
  })

  it('tells the user where the commands went', async () => {
    // The rail was the only place they were advertised, so the empty state
    // has to carry that now.
    render(<AppShell />)
    await ready()
    expect(screen.getByTestId('scrollback').textContent).toContain(
      'for the full command list',
    )
  })

  it('fetches the catalog from the backend rather than duplicating it', async () => {
    // A second copy in the renderer drifts, and then the menu offers commands
    // the backend does not implement.
    render(<AppShell />)
    await ready()
    expect(requests.some((r) => r.method === 'app.commands')).toBe(true)
  })

  it('offers the fetched catalog behind "/"', async () => {
    render(<AppShell />)
    await ready()
    await userEvent.type(screen.getByRole('textbox', { name: 'Citrine prompt' }), '/')
    expect(screen.getAllByRole('option')).toHaveLength(CATALOG.length)
  })
})

describe('dropping files', () => {
  it('shows nothing until something is dragged in', async () => {
    render(<AppShell />)
    await ready()
    expect(screen.queryByTestId('dropzone')).toBeNull()
  })

  it('invites the drop while a file is over the window', async () => {
    render(<AppShell />)
    await ready()
    const app = document.querySelector('.ct-app') as HTMLElement
    fireEvent.dragEnter(app, { dataTransfer: { files: [], types: ['Files'] } })
    expect(screen.getByTestId('dropzone')).toBeTruthy()
  })

  it('ignores a drag that is not carrying files', async () => {
    // Selecting text and dragging it should not raise a file overlay.
    render(<AppShell />)
    await ready()
    const app = document.querySelector('.ct-app') as HTMLElement
    fireEvent.dragEnter(app, { dataTransfer: { files: [], types: ['text/plain'] } })
    expect(screen.queryByTestId('dropzone')).toBeNull()
  })

  it('lists a dropped file as an attachment', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() =>
      expect(screen.getByTestId('attachments').textContent).toContain('main.py'),
    )
  })

  it('clears the overlay once the file lands', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => expect(screen.queryByTestId('dropzone')).toBeNull())
  })

  it('shows the size so a large paste is not a surprise', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'x'.repeat(2048))])
    await waitFor(() =>
      expect(screen.getByTestId('attachments').textContent).toContain('2.0 KB'),
    )
  })

  it('lets an attachment be taken back off', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => screen.getByTestId('attachments'))

    await userEvent.click(screen.getByRole('button', { name: 'Remove main.py' }))
    expect(screen.queryByTestId('attachments')).toBeNull()
  })

  it('sends the file contents with the turn', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => screen.getByTestId('attachments'))

    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      'explain this{Enter}',
    )

    await waitFor(() => {
      const chat = requests.find((r) => r.method === 'chat.send')
      expect(chat).toBeTruthy()
      expect(chat!.params.attachments).toMatchObject([
        { name: 'main.py', text: 'print(1)' },
      ])
    })
  })

  it('does not attach files to a slash command', async () => {
    // Commands run locally against config; they have nothing to do with files.
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => screen.getByTestId('attachments'))

    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      '/status{Escape}{Enter}',
    )

    await waitFor(() => {
      const command = requests.find((r) => r.method === 'command.run')
      expect(command).toBeTruthy()
      expect(command!.params.attachments).toBeUndefined()
    })
  })
})

describe('a turn in flight', () => {
  it('is not shown before anything is sent', async () => {
    render(<AppShell />)
    await ready()
    expect(screen.queryByTestId('thinking-indicator')).toBeNull()
  })

  it('shows the agent working while the reply is outstanding', async () => {
    // Without it an eight-second request is indistinguishable from one that
    // has failed silently.
    render(<AppShell />)
    await ready()
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      'hello{Enter}',
    )
    await waitFor(() => expect(screen.getByTestId('thinking-indicator')).toBeTruthy())
  })

  it('names the files it is working through', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => screen.getByTestId('attachments'))

    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      'explain{Enter}',
    )

    await waitFor(() =>
      expect(screen.getByTestId('thinking-indicator').textContent).toContain('main.py'),
    )
  })

  it('stops once the reply arrives', async () => {
    render(<AppShell />)
    await ready()
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      'hello{Enter}',
    )
    await waitFor(() => screen.getByTestId('thinking-indicator'))

    resolveChat!({ text: 'a reply' })
    await waitFor(() => expect(screen.queryByTestId('thinking-indicator')).toBeNull())
    expect(screen.getByTestId('scrollback').textContent).toContain('a reply')
  })

  it('clears the attachments once they have been sent', async () => {
    // Leaving them staged would silently re-send them on the next turn.
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => screen.getByTestId('attachments'))

    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      'go{Enter}',
    )
    await waitFor(() => expect(screen.queryByTestId('attachments')).toBeNull())
  })

  it('records the files against the line that carried them', async () => {
    render(<AppShell />)
    await ready()
    drop([textFile('main.py', 'print(1)')])
    await waitFor(() => screen.getByTestId('attachments'))

    await userEvent.type(
      screen.getByRole('textbox', { name: 'Citrine prompt' }),
      'go{Enter}',
    )
    await waitFor(() =>
      expect(document.querySelector('.ct-line__files')?.textContent).toContain('main.py'),
    )
  })
})
