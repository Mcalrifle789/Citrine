import { useEffect, useRef, useState } from 'react'
import { Frame } from './terminal/Frame'
import { Panel } from './terminal/Panel'
import { Prompt } from './terminal/Prompt'
import { StatusBar, type Segment } from './terminal/StatusBar'
import { EmptyState } from './EmptyState'
import { Transport } from '../lib/transport'
import { METHODS } from '../lib/protocol'
import { useAppStore } from '../lib/store'
import { applyTheme, THEMES, type ThemeName } from '../lib/theme'

interface AppStatus {
  provider: string
  provider_id: string | null
  model: string
  tokens: string
  token_total: number
  session: string
  sessions: string[]
  agent: string
  agents: string[]
  providers: Array<{ id: string; label: string; model?: string | null }>
  models: string[]
}

const COMMANDS: Array<[string, string]> = [
  ['provider', 'Add or switch model providers'],
  ['model', 'Browse models from the selected provider'],
  ['keys', 'Manage stored API keys'],
  ['mcp', 'Connect ElevenLabs, Deepgram, SUNO, or custom MCP'],
  ['searchsetup', 'Configure DuckDuckGo, Perplexity, Gemini, Parallel, or custom search'],
  ['theme', 'Switch visual themes'],
  ['settings', 'Open Citrine settings'],
  ['new', 'Start a new session'],
  ['plan', 'Enter planning mode'],
  ['build', 'Enter execution mode'],
  ['memory', 'View or edit saved memory'],
  ['context', 'Inspect active context'],
  ['summarize', 'Summarize the session'],
  ['fork', 'Branch this conversation'],
  ['session', 'Switch between agent sessions'],
  ['agent', 'Switch agents or create a new one'],
  ['tasks', 'View active agent tasks'],
  ['tools', 'Inspect enabled tools'],
  ['approvals', 'Review pending confirmations'],
  ['schedule', 'Create a scheduled task'],
  ['code', 'Generate or refactor code'],
  ['explain', 'Explain code or concepts'],
  ['refactor', 'Improve existing code'],
  ['test', 'Generate or run tests'],
  ['docs', 'Generate documentation'],
  ['review', 'Review code for bugs'],
  ['debug', 'Diagnose errors'],
  ['diff', 'Inspect current changes'],
  ['patch', 'Apply a focused patch'],
  ['commit', 'Create a git commit'],
  ['git', 'Inspect branches and history'],
  ['init', 'Initialize a project'],
  ['open', 'Open a project'],
  ['files', 'Browse project files'],
  ['workspace', 'Manage workspace roots'],
  ['run', 'Run a project command'],
  ['terminal', 'Open a shell pane'],
  ['deploy', 'Deploy the project'],
  ['env', 'Manage environment variables'],
  ['package', 'Build or package the app'],
  ['update', 'Check for updates'],
  ['desktop', 'Request desktop control'],
  ['screenshot', 'Capture the screen'],
  ['browse', 'Open a browser task'],
  ['search', 'Search through the configured search provider'],
  ['web', 'Fetch or inspect web pages'],
  ['research', 'Run a research pass'],
  ['notes', 'Open local notes'],
  ['speak', 'Generate speech with ElevenLabs'],
  ['listen', 'Start voice input'],
  ['transcribe', 'Transcribe audio with Deepgram'],
  ['voice', 'Manage voices'],
  ['music', 'Generate music with SUNO'],
  ['clone', 'Duplicate or transform audio'],
  ['media', 'View generated media assets'],
  ['spotify', 'Browse or play Spotify'],
  ['calendar', 'Inspect calendar context'],
  ['inbox', 'Triage messages or email'],
  ['commands', 'Open the full command catalog'],
  ['history', 'Browse previous sessions'],
  ['export', 'Export chats or artifacts'],
  ['reset', 'Reset session state'],
  ['logs', 'Open app and backend logs'],
  ['health', 'Run Citrine diagnostics'],
  ['status', 'Show current system status'],
  ['help', 'Show help information'],
]

const CONNECTION_LABEL: Record<string, [string, Segment['tone']]> = {
  idle: ['connecting…', 'dim'],
  connecting: ['connecting…', 'dim'],
  authenticating: ['authenticating…', 'dim'],
  open: ['connected', 'ok'],
  reconnecting: ['reconnecting…', 'err'],
  closed: ['disconnected', 'err'],
}

export function AppShell() {
  const transport = useRef<Transport | null>(null)
  const [promptValue, setPromptValue] = useState('')
  const [promptFocusToken, setPromptFocusToken] = useState(0)
  const [appStatus, setAppStatus] = useState<AppStatus | null>(null)
  const { connection, lines, addLine, setConnection } = useAppStore()

  useEffect(() => {
    const t = new Transport()
    transport.current = t
    t.onStateChange(setConnection)

    void (async () => {
      const info = await window.citrine.getBackendInfo()
      if (!info) {
        addLine('error', 'Backend is unavailable.')
        return
      }
      try {
        await t.connect(info)
        await refreshStatus(t)
      } catch (error) {
        addLine('error', error instanceof Error ? error.message : String(error))
      }
    })()

    return () => t.close()
  }, [addLine, setConnection])

  async function handleSubmit(value: string): Promise<void> {
    addLine('input', value)
    try {
      const method = value.startsWith('/') ? METHODS.commandRun : METHODS.chatSend
      const result = await transport.current!.request<{ text: string }>(method, {
        text: value,
      })
      addLine('output', result.text)
      maybeApplyCommandSideEffect(value)
      if (value.startsWith('/')) {
        await refreshStatus()
      }
    } catch (error) {
      addLine('error', error instanceof Error ? error.message : String(error))
    }
  }

  function handleCommandSelect(name: string): void {
    setPromptValue(`/${name} `)
    setPromptFocusToken((token) => token + 1)
  }

  function maybeApplyCommandSideEffect(value: string): void {
    const [command, arg] = value.trim().split(/\s+/, 2)
    if (command !== '/theme' || !arg) return
    if ((THEMES as readonly string[]).includes(arg)) {
      applyTheme(arg as ThemeName)
    }
  }

  async function refreshStatus(client = transport.current): Promise<void> {
    if (!client || client.getState() !== 'open') return
    const result = await client.request<AppStatus>(METHODS.appStatus)
    setAppStatus(result)
  }

  function commandSuggestions(): Array<{ label: string; value: string }> {
    if (!promptValue.startsWith('/')) return []
    const [command, ...rest] = promptValue.trimStart().split(/\s+/)
    const query = rest.join(' ').toLowerCase()
    const filter = (items: Array<{ label: string; value: string }>) =>
      items.filter((item) => item.label.toLowerCase().includes(query)).slice(0, 8)

    if (command === '/provider') {
      return filter(
        (appStatus?.providers ?? []).map((provider) => ({
          label: `${provider.label}${provider.model ? ` · ${provider.model}` : ''}`,
          value: `/provider ${provider.id}`,
        })),
      )
    }
    if (command === '/model') {
      return filter(
        (appStatus?.models ?? []).map((model) => ({
          label: model,
          value: `/model ${model}`,
        })),
      )
    }
    if (command === '/session') {
      return filter(
        (appStatus?.sessions ?? []).map((session) => ({
          label: session,
          value: `/session ${session}`,
        })),
      )
    }
    if (command === '/agent') {
      return filter(
        (appStatus?.agents ?? []).map((agent) => ({
          label: agent,
          value: `/agent ${agent}`,
        })),
      )
    }
    return []
  }

  const [label, tone] = CONNECTION_LABEL[connection] ?? ['unknown', 'dim']
  const promptMeta = appStatus
    ? `${appStatus.provider} · ${appStatus.model} · ${tokenMeter(appStatus.token_total, lines)}`
    : 'provider: -- · model: -- · tokens: --'

  return (
    <div className="ct-app">
      <header className="ct-app__header">
        <span className="ct-app__logo">Citrine</span>
        <span className="ct-app__sub">AI Project</span>
      </header>

      <div className="ct-app__body">
        <aside className="ct-app__rail">
          <Panel title="Available Commands">
            <ul className="ct-cmdlist">
              {COMMANDS.map(([name, description]) => (
                <li key={name}>
                  <button
                    type="button"
                    className="ct-cmdlist__button"
                    onClick={() => handleCommandSelect(name)}
                    aria-label={`Insert /${name} command`}
                  >
                    <span className="ct-cmdlist__name">/{name}</span>
                    <span className="ct-cmdlist__desc">{description}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Status">
            <div className="ct-status">
              <div>
                Connection: <span className="ct-accent">{label}</span>
              </div>
              <div>Session: local</div>
              <div>Commands: {COMMANDS.length}</div>
            </div>
          </Panel>
        </aside>

        <main className="ct-app__main">
          <Frame title={`Citrine v0.1.0 · shell & spine`}>
            <div className="ct-scrollback" data-testid="scrollback">
              {lines.length === 0 ? (
                <EmptyState />
              ) : (
                lines.map((line) => (
                  <div key={line.id} className="ct-line" data-kind={line.kind}>
                    {line.kind === 'input' ? `> ${line.text}` : line.text}
                  </div>
                ))
              )}
            </div>
          </Frame>
        </main>
      </div>

      <StatusBar
        segments={[
          { id: 'app', label: 'citrine', tone: 'accent' },
          { id: 'branch', label: ' main', tone: 'gold' },
        ]}
        right={[{ id: 'conn', label, tone }]}
      />
      <Prompt
        value={promptValue}
        onValueChange={setPromptValue}
        focusToken={promptFocusToken}
        meta={promptMeta}
        suggestions={commandSuggestions()}
        onSubmit={(v) => void handleSubmit(v)}
        disabled={connection !== 'open'}
      />
    </div>
  )
}

function tokenMeter(total: number, lines: Array<{ text: string }>): string {
  if (total <= 0) return '--'
  const used = lines.reduce((sum, line) => sum + Math.ceil(line.text.length / 4), 0)
  return `${compactTokens(Math.max(total - used, 0))}/${compactTokens(total)}`
}

function compactTokens(value: number): string {
  if (value >= 1_000_000) return `${Math.floor(value / 1_000_000)}m`
  if (value >= 1_000) return `${Math.floor(value / 1_000)}k`
  return String(value)
}
