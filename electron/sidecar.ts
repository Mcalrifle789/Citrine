import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

export interface BackendInfo {
  port: number
  token: string
}

export type SidecarState = 'starting' | 'ready' | 'restarting' | 'failed'

export const MAX_RESTART_ATTEMPTS = 5
const BASE_BACKOFF_MS = 250
const MAX_BACKOFF_MS = 8000
const READY_TIMEOUT_MS = 20_000

/**
 * Parse the backend's single stdout handshake line.
 * Returns null for anything that is not a well-formed ready announcement,
 * including port 0 — which would mean the socket never actually bound.
 */
export function parseReadyLine(line: string): number | null {
  const trimmed = line.trim()
  if (!trimmed.startsWith('{')) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return null
  }

  if (typeof parsed !== 'object' || parsed === null) return null
  const record = parsed as Record<string, unknown>
  if (record.event !== 'ready') return null
  if (typeof record.port !== 'number' || !Number.isInteger(record.port)) return null
  if (record.port <= 0) return null
  return record.port
}

export function nextBackoffMs(attempt: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS)
}

function pythonExecutable(projectRoot: string): string {
  const venvWin = resolve(projectRoot, 'backend/.venv/Scripts/python.exe')
  const venvPosix = resolve(projectRoot, 'backend/.venv/bin/python')
  if (existsSync(venvWin)) return venvWin
  if (existsSync(venvPosix)) return venvPosix
  return process.platform === 'win32' ? 'python' : 'python3'
}

export class Sidecar {
  private child: ChildProcessWithoutNullStreams | null = null
  private info: BackendInfo | null = null
  private attempt = 0
  private stopping = false
  private listeners: Array<(s: SidecarState) => void> = []

  constructor(
    private readonly projectRoot: string,
    private readonly allowedOrigin: string,
    private readonly token: string = randomBytes(32).toString('hex'),
  ) {}

  onStateChange(cb: (s: SidecarState) => void): void {
    this.listeners.push(cb)
  }

  private emit(state: SidecarState): void {
    for (const cb of this.listeners) cb(state)
  }

  getInfo(): BackendInfo | null {
    return this.info
  }

  async start(): Promise<BackendInfo> {
    this.emit('starting')
    const info = await this.spawnOnce()
    this.info = info
    this.attempt = 0
    this.emit('ready')
    return info
  }

  private spawnOnce(): Promise<BackendInfo> {
    return new Promise<BackendInfo>((resolvePromise, rejectPromise) => {
      const python = pythonExecutable(this.projectRoot)
      const child = spawn(
        python,
        ['-m', 'citrine.server', '--port', '0', '--host', '127.0.0.1',
         '--origin', this.allowedOrigin],
        {
          cwd: resolve(this.projectRoot, 'backend'),
          env: { ...process.env, CITRINE_AUTH_TOKEN: this.token, PYTHONUNBUFFERED: '1' },
        },
      ) as ChildProcessWithoutNullStreams

      this.child = child

      let settled = false
      let stdoutBuffer = ''
      const stderrTail: string[] = []

      const timer = setTimeout(() => {
        if (settled) return
        settled = true
        child.kill()
        rejectPromise(
          new Error(
            `Backend did not announce readiness within ${READY_TIMEOUT_MS}ms.\n` +
              stderrTail.join(''),
          ),
        )
      }, READY_TIMEOUT_MS)

      child.stdout.setEncoding('utf-8')
      child.stdout.on('data', (chunk: string) => {
        stdoutBuffer += chunk
        let newline: number
        while ((newline = stdoutBuffer.indexOf('\n')) !== -1) {
          const line = stdoutBuffer.slice(0, newline)
          stdoutBuffer = stdoutBuffer.slice(newline + 1)
          const port = parseReadyLine(line)
          if (port !== null && !settled) {
            settled = true
            clearTimeout(timer)
            resolvePromise({ port, token: this.token })
          }
        }
      })

      child.stderr.setEncoding('utf-8')
      child.stderr.on('data', (chunk: string) => {
        stderrTail.push(chunk)
        if (stderrTail.length > 50) stderrTail.shift()
        process.stderr.write(`[backend] ${chunk}`)
      })

      child.on('error', (err) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        rejectPromise(
          new Error(`Failed to launch Python at "${python}": ${err.message}`),
        )
      })

      child.on('exit', (code) => {
        clearTimeout(timer)
        if (!settled) {
          settled = true
          rejectPromise(
            new Error(
              `Backend exited with code ${code} before becoming ready.\n` +
                stderrTail.join(''),
            ),
          )
          return
        }
        void this.handleUnexpectedExit()
      })
    })
  }

  private async handleUnexpectedExit(): Promise<void> {
    if (this.stopping) return
    this.info = null

    if (this.attempt >= MAX_RESTART_ATTEMPTS) {
      this.emit('failed')
      return
    }

    const delay = nextBackoffMs(this.attempt)
    this.attempt += 1
    this.emit('restarting')
    await new Promise((r) => setTimeout(r, delay))
    if (this.stopping) return

    try {
      this.info = await this.spawnOnce()
      this.attempt = 0
      this.emit('ready')
    } catch {
      void this.handleUnexpectedExit()
    }
  }

  stop(): void {
    this.stopping = true
    this.child?.kill()
    this.child = null
    this.info = null
  }
}
