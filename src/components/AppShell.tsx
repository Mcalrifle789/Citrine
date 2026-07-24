import { useEffect, useRef } from 'react'
import { Frame } from './terminal/Frame'
import { Panel } from './terminal/Panel'
import { Prompt } from './terminal/Prompt'
import { StatusBar, type Segment } from './terminal/StatusBar'
import { EmptyState } from './EmptyState'
import { Transport } from '../lib/transport'
import { useAppStore } from '../lib/store'

const COMMANDS: Array<[string, string]> = [
  ['init', 'Initialize a new project'],
  ['chat', 'Start a new chat session'],
  ['code', 'Generate or refactor code'],
  ['explain', 'Explain code or concepts'],
  ['test', 'Generate unit tests'],
  ['docs', 'Generate documentation'],
  ['config', 'Manage configuration'],
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
      } catch (error) {
        addLine('error', error instanceof Error ? error.message : String(error))
      }
    })()

    return () => t.close()
  }, [addLine, setConnection])

  async function handleSubmit(value: string): Promise<void> {
    addLine('input', value)
    try {
      const result = await transport.current!.request<{ text: string }>('echo', {
        text: value,
      })
      addLine('output', result.text)
    } catch (error) {
      addLine('error', error instanceof Error ? error.message : String(error))
    }
  }

  const [label, tone] = CONNECTION_LABEL[connection] ?? ['unknown', 'dim']

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
                  <span className="ct-cmdlist__name">{name}</span>
                  <span className="ct-cmdlist__desc">{description}</span>
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
      <Prompt onSubmit={(v) => void handleSubmit(v)} disabled={connection !== 'open'} />
    </div>
  )
}
