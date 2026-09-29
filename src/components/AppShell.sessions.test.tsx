import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Starting a new session clears the window.
 *
 * The reported bug: after `/new` the previous session's lines were still on
 * screen, so a "new session" read as a continuation of the old conversation.
 * The backend decides which conversation is active and reports it as
 * `app.status.transcript_key`; the shell follows it.
 *
 * The transport is faked, but the fake mirrors the backend's real behaviour:
 * `/new` moves the session, `/agent` moves the agent, `/reset` moves the epoch,
 * and each of those produces a different key and its own token count.
 */

interface FakeStatus {
  provider: string
  provider_id: string | null
  model: string
  tokens: string
  token_used: number
  token_total: number
  session: string
  sessions: string[]
  transcript_key: string
  agent: string
  agents: string[]
  providers: Array<{ id: string; label: string; model?: string | null }>
  models: string[]
}

/** The backend's own state, reduced to what /new, /agent and /reset touch. */
const backend = {
  session: 'main',
  agent: 'Default',
  epoch: 0,
  models: { Default: 'openai/gpt-4o-mini', Scout: 'openai/gpt-4o' } as Record<
    string,
    string
  >,
  usage: {} as Record<string, number>,
}

function key(): string {
  return `${backend.agent}::${backend.session}#${backend.epoch}`
}

function status(): FakeStatus {
  const used = backend.usage[`${backend.agent}::${backend.session}`] ?? 0
  return {
    provider: 'OpenRouter',
    provider_id: 'custom',
    model: backend.models[backend.agent]!,
    tokens: `${used}/128k`,
    token_used: used,
    token_total: 128000,
    session: backend.session,
    sessions: ['main'],
    transcript_key: key(),
    agent: backend.agent,
    agents: ['Default', 'Scout'],
    providers: [{ id: 'custom', label: 'OpenRouter', model: 'openai/gpt-4o-mini' }],
    models: ['openai/gpt-4o-mini'],
  }
}

function runCommand(text: string): string {
  if (text === '/new') {
    backend.session = 'session-1'
    return 'New session created: session-1.'
  }
  if (text === '/reset') {
    backend.epoch += 1
    return 'Session main reset.'
  }
  if (text.startsWith('/agent ')) {
    backend.agent = text.slice('/agent '.length)
    return `Agent switched to ${backend.agent}.`
  }
  if (text === '/session main') {
    backend.session = 'main'
    return 'Session switched to main.'
  }
  return 'ok'
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
      if (method === 'app.status') return Promise.resolve(status())
      if (method === 'app.commands') {
        return Promise.resolve({
          commands: [
            { name: 'new', description: 'Start a new session' },
            { name: 'reset', description: 'Reset session state' },
            { name: 'agent', description: 'Switch agents' },
            { name: 'session', description: 'Switch sessions' },
          ],
        })
      }
      if (method === 'command.run') {
        return Promise.resolve({ text: runCommand(String(params.text)) })
      }
      if (method === 'chat.send') {
        backend.usage[`${backend.agent}::${backend.session}`] = 4200
        return Promise.resolve({ text: 'a reply' })
      }
      return Promise.resolve({ text: 'ok' })
    }
    close() {}
  }
  return { Transport }
})

const { AppShell } = await import('./AppShell')
const { useAppStore } = await import('../lib/store')

const prompt = () => screen.getByRole('textbox', { name: 'Citrine prompt' })
const scrollback = () => screen.getByTestId('scrollback')

/** The header chip for `key`. "main" also appears as the branch in the status
 *  bar, so the chips have to be read by name rather than by their text. */
function chip(name: string): string {
  const label = [...document.querySelectorAll('.ct-chip__key')].find(
    (node) => node.textContent === name,
  )
  return label?.parentElement?.textContent?.slice(name.length) ?? ''
}

async function ready(): Promise<void> {
  render(<AppShell />)
  await waitFor(() =>
    expect(useAppStore.getState().transcriptKey).toBe('Default::main#0'),
  )
}

/** Type a command, dismissing the "/" menu so Enter submits the raw text. */
async function send(text: string): Promise<void> {
  await userEvent.type(prompt(), `${text}{Escape}{Enter}`)
}

beforeEach(() => {
  backend.session = 'main'
  backend.agent = 'Default'
  backend.epoch = 0
  backend.usage = {}
  useAppStore.getState().reset()
  Object.defineProperty(window, 'citrine', {
    value: { getBackendInfo: () => Promise.resolve({ port: 1234, token: 't' }) },
    configurable: true,
  })
})

describe('starting a new session', () => {
  it('takes the previous conversation off the window', async () => {
    await ready()
    await send('tell me something')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))

    await send('/new')
    await waitFor(() => expect(scrollback().textContent).not.toContain('a reply'))
  })

  it('does not leave the previous prompt on the window either', async () => {
    await ready()
    await send('tell me something')
    await waitFor(() => expect(scrollback().textContent).toContain('tell me something'))

    await send('/new')
    await waitFor(() =>
      expect(scrollback().textContent).not.toContain('tell me something'),
    )
  })

  it('shows the confirmation in the new session, not the old one', async () => {
    // Filing it under the session the user just left means they never see it.
    await ready()
    await send('/new')
    await waitFor(() =>
      expect(scrollback().textContent).toContain('New session created: session-1.'),
    )
  })

  it('leaves the window otherwise empty', async () => {
    await ready()
    await send('hello')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))

    await send('/new')
    await waitFor(() => expect(useAppStore.getState().lines).toHaveLength(1))
  })

  it('shows the new session name in the header', async () => {
    await ready()
    await send('/new')
    await waitFor(() => expect(chip('session')).toBe('session-1'))
  })

  it('puts the token count back to zero', async () => {
    await ready()
    await send('hello')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))
    expect(screen.getByText('4200/128k')).toBeTruthy()

    await send('/new')
    await waitFor(() => expect(screen.getByText('0/128k')).toBeTruthy())
  })

  it('brings the old conversation back if the user switches to it', async () => {
    await ready()
    await send('hello')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))
    await send('/new')
    await waitFor(() => expect(scrollback().textContent).not.toContain('a reply'))

    await send('/session main')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))
  })
})

describe('switching agents', () => {
  it('clears the window', async () => {
    await ready()
    await send('hello')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))

    await send('/agent Scout')
    await waitFor(() => expect(scrollback().textContent).not.toContain('a reply'))
  })

  it('shows the new agent model', async () => {
    await ready()
    await send('/agent Scout')
    await waitFor(() => expect(chip('model')).toBe('openai/gpt-4o'))
  })

  it('puts the token count back to zero for the new agent', async () => {
    // The complaint: the previous agent's count carried across, measured
    // against a context window that is no longer the one in use.
    await ready()
    await send('hello')
    await waitFor(() => expect(screen.getByText('4200/128k')).toBeTruthy())

    await send('/agent Scout')
    await waitFor(() => expect(screen.getByText('0/128k')).toBeTruthy())
  })

  it('restores that agent count on the way back', async () => {
    await ready()
    await send('hello')
    await waitFor(() => expect(screen.getByText('4200/128k')).toBeTruthy())
    await send('/agent Scout')
    await waitFor(() => expect(screen.getByText('0/128k')).toBeTruthy())

    await send('/agent Default')
    await waitFor(() => expect(screen.getByText('4200/128k')).toBeTruthy())
  })
})

describe('resetting a session', () => {
  it('clears the window without renaming the session', async () => {
    await ready()
    await send('hello')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))

    await send('/reset')
    await waitFor(() => expect(scrollback().textContent).not.toContain('a reply'))
    expect(chip('session')).toBe('main')
  })
})

describe('an ordinary turn', () => {
  it('does not clear the window', async () => {
    // The status refresh runs after every turn, so a key that is merely equal
    // must not be treated as a change.
    await ready()
    await send('first')
    await waitFor(() => expect(scrollback().textContent).toContain('a reply'))

    await send('second')
    await waitFor(() =>
      expect(scrollback().textContent).toContain('first'),
    )
    expect(scrollback().textContent).toContain('second')
  })
})
