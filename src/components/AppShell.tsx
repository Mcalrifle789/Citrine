import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import { Frame } from './terminal/Frame'
import { Prompt, type PromptCommand, type PromptOption } from './terminal/Prompt'
import { StatusBar, type Segment } from './terminal/StatusBar'
import { EmptyState } from './EmptyState'
import { ThinkingIndicator } from './ThinkingIndicator'
import { Transport } from '../lib/transport'
import { METHODS } from '../lib/protocol'
import { useAppStore } from '../lib/store'
import { applyTheme, THEMES, type ThemeName } from '../lib/theme'
import {
  formatBytes,
  readAttachments,
  toWire,
  type Attachment,
} from '../lib/attachments'

interface AppStatus {
  provider: string
  provider_id: string | null
  model: string
  tokens: string
  token_used: number
  token_total: number
  session: string
  sessions: string[]
  agent: string
  agents: string[]
  providers: Array<{ id: string; label: string; model?: string | null }>
  models: string[]
}

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
  const [commands, setCommands] = useState<PromptCommand[]>([])
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [pendingFiles, setPendingFiles] = useState<string[] | null>(null)
  const scrollbackRef = useRef<HTMLDivElement>(null)
  const { connection, lines, addLine, setConnection } = useAppStore()

  // dragenter and dragleave both fire when the pointer crosses a *child*
  // boundary, so a boolean flickers the overlay off mid-drag. Counting the
  // enters and leaves is the standard fix.
  const dragDepth = useRef(0)
  const [dragging, setDragging] = useState(false)

  const refreshStatus = useCallback(
    async (client: Transport | null = transport.current): Promise<void> => {
      if (!client || client.getState() !== 'open') return
      setAppStatus(await client.request<AppStatus>(METHODS.appStatus))
    },
    [],
  )

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
        // The catalog is owned by the backend registry. Fetching it means the
        // menu cannot list a command the backend does not implement, which a
        // second hand-maintained copy in the renderer guarantees eventually.
        const catalog = await t.request<{ commands: PromptCommand[] }>(
          METHODS.appCommands,
        )
        setCommands(catalog.commands ?? [])
      } catch (error) {
        addLine('error', error instanceof Error ? error.message : String(error))
      }
    })()

    return () => t.close()
  }, [addLine, setConnection, refreshStatus])

  // Pin the transcript to the newest line as it grows.
  useEffect(() => {
    const element = scrollbackRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [lines, pendingFiles])

  async function handleSubmit(value: string): Promise<void> {
    const sent = attachments
    const names = sent.map((attachment) => attachment.name)

    addLine('input', value, names.length > 0 ? names : undefined)
    setAttachments([])
    setPendingFiles(names)

    try {
      const isCommand = value.startsWith('/')
      const method = isCommand ? METHODS.commandRun : METHODS.chatSend
      const params: Record<string, unknown> = { text: value }
      // Commands run locally against config and take no files; only a chat
      // turn has anything to do with them.
      if (!isCommand && sent.length > 0) params.attachments = toWire(sent)

      const result = await transport.current!.request<{ text: string }>(method, params)
      addLine('output', result.text)
      maybeApplyCommandSideEffect(value)
      await refreshStatus()
    } catch (error) {
      addLine('error', error instanceof Error ? error.message : String(error))
    } finally {
      setPendingFiles(null)
    }
  }

  function maybeApplyCommandSideEffect(value: string): void {
    const [command, arg] = value.trim().split(/\s+/, 2)
    if (command !== '/theme' || !arg) return
    if ((THEMES as readonly string[]).includes(arg)) {
      applyTheme(arg as ThemeName)
    }
  }

  async function ingest(files: FileList | File[]): Promise<void> {
    const read = await readAttachments(files)
    if (read.length === 0) return
    setAttachments((current) => [...current, ...read])
    setPromptFocusToken((token) => token + 1)
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>): void {
    if (!event.dataTransfer.types.includes('Files')) return
    event.preventDefault()
    dragDepth.current += 1
    setDragging(true)
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>): void {
    if (!event.dataTransfer.types.includes('Files')) return
    // Without this the browser navigates to the dropped file and the whole
    // renderer is replaced by it.
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }

  function handleDragLeave(): void {
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setDragging(false)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    if (event.dataTransfer.files.length > 0) void ingest(event.dataTransfer.files)
  }

  function removeAttachment(name: string): void {
    setAttachments((current) => current.filter((item) => item.name !== name))
  }

  function argumentSuggestions(): PromptOption[] {
    if (!promptValue.startsWith('/')) return []
    const [command, ...rest] = promptValue.trimStart().split(/\s+/)
    const query = rest.join(' ').toLowerCase()
    const filter = (items: PromptOption[]) =>
      items.filter((item) => item.label.toLowerCase().includes(query)).slice(0, 8)

    if (command === '/provider') {
      return filter(
        (appStatus?.providers ?? []).map((provider) => ({
          label: provider.label,
          hint: provider.model ?? undefined,
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
    ? `${appStatus.provider} · ${appStatus.model} · ${appStatus.tokens}`
    : 'provider: -- · model: -- · tokens: --'
  const busy = pendingFiles !== null

  return (
    <div
      className="ct-app"
      data-dragging={dragging || undefined}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <header className="ct-app__header">
        <span className="ct-app__logo">Citrine</span>
        <span className="ct-app__sub">AI Project</span>
        <div className="ct-app__meta">
          <span className="ct-chip">
            <span className="ct-chip__key">agent</span>
            {appStatus?.agent ?? '--'}
          </span>
          <span className="ct-chip">
            <span className="ct-chip__key">session</span>
            {appStatus?.session ?? '--'}
          </span>
          <span className="ct-chip">
            <span className="ct-chip__key">model</span>
            {appStatus?.model ?? '--'}
          </span>
        </div>
      </header>

      <main className="ct-app__main">
        <Frame title="Citrine v0.1.0 · shell &amp; spine">
          <div className="ct-scrollback" data-testid="scrollback" ref={scrollbackRef}>
            {lines.length === 0 && !busy ? (
              <EmptyState />
            ) : (
              lines.map((line) => (
                <div key={line.id} className="ct-line" data-kind={line.kind}>
                  {line.kind === 'input' ? `> ${line.text}` : line.text}
                  {line.files && (
                    <span className="ct-line__files"> [{line.files.join(', ')}]</span>
                  )}
                </div>
              ))
            )}
            {busy && <ThinkingIndicator files={pendingFiles ?? []} />}
          </div>
        </Frame>
      </main>

      <StatusBar
        segments={[
          { id: 'app', label: 'citrine', tone: 'accent' },
          { id: 'branch', label: ' main', tone: 'gold' },
          { id: 'commands', label: `${commands.length} commands`, tone: 'dim' },
        ]}
        right={[
          { id: 'tokens', label: appStatus?.tokens ?? '--', tone: 'dim' },
          { id: 'conn', label, tone },
        ]}
      />

      <Prompt
        value={promptValue}
        onValueChange={setPromptValue}
        focusToken={promptFocusToken}
        meta={promptMeta}
        commands={commands}
        suggestions={argumentSuggestions()}
        onSubmit={(v) => void handleSubmit(v)}
        disabled={connection !== 'open' || busy}
      >
        {attachments.length > 0 && (
          <div className="ct-attachments" data-testid="attachments">
            {attachments.map((attachment) => (
              <span
                key={attachment.name}
                className="ct-attachment"
                data-unreadable={attachment.text === null || undefined}
              >
                <span className="ct-attachment__name">{attachment.name}</span>
                <span className="ct-attachment__size">
                  {formatBytes(attachment.size)}
                  {attachment.truncated && ' · truncated'}
                  {attachment.text === null && ' · binary'}
                </span>
                <button
                  type="button"
                  className="ct-attachment__remove"
                  aria-label={`Remove ${attachment.name}`}
                  onClick={() => removeAttachment(attachment.name)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </Prompt>

      {dragging && (
        <div className="ct-dropzone" data-testid="dropzone" role="presentation">
          <div className="ct-dropzone__inner">
            <span className="ct-dropzone__title">Drop files for Citrine</span>
            <span className="ct-dropzone__hint">
              Text files are read in full; anything else is described by name and size.
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
