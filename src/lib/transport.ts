import { METHODS, nextId, parseEnvelope, type Envelope } from './protocol'

export interface BackendInfo {
  port: number
  token: string
}

export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'authenticating'
  | 'open'
  | 'reconnecting'
  | 'closed'

export interface StreamHandlers {
  onDelta: (params: Record<string, unknown>) => void
  onDone: (params: Record<string, unknown>) => void
  onError: (params: Record<string, unknown>) => void
}

interface Pending {
  resolve: (value: never) => void
  reject: (reason: Error) => void
}

const RECONNECT_BASE_MS = 300
const RECONNECT_MAX_MS = 5000

/**
 * WebSocket client for the Citrine backend.
 *
 * Every frame carries an id, so responses and stream events demultiplex
 * through the same map without special cases. Requests fail fast when the
 * socket is not open rather than queueing forever — a hung promise is far
 * harder to diagnose than an immediate rejection.
 */
export class Transport {
  private socket: WebSocket | null = null
  private info: BackendInfo | null = null
  private state: ConnectionState = 'idle'
  private pending = new Map<string, Pending>()
  private streams = new Map<string, StreamHandlers>()
  private listeners: Array<(s: ConnectionState) => void> = []
  private reconnectAttempt = 0
  private intentionalClose = false

  onStateChange(cb: (s: ConnectionState) => void): void {
    this.listeners.push(cb)
  }

  getState(): ConnectionState {
    return this.state
  }

  private setState(state: ConnectionState): void {
    this.state = state
    for (const cb of this.listeners) cb(state)
  }

  connect(info: BackendInfo): Promise<void> {
    this.info = info
    this.intentionalClose = false
    return new Promise<void>((resolve, reject) => {
      this.setState('connecting')
      const socket = new WebSocket(`ws://127.0.0.1:${info.port}/ws`)
      this.socket = socket

      let authSettled = false

      socket.onopen = () => {
        this.setState('authenticating')
        const id = nextId('auth')
        this.pending.set(id, {
          resolve: () => {
            authSettled = true
            this.reconnectAttempt = 0
            this.setState('open')
            resolve()
          },
          reject: (err) => {
            authSettled = true
            reject(err)
          },
        } as Pending)
        socket.send(
          JSON.stringify({
            id,
            type: 'request',
            method: METHODS.auth,
            params: { token: info.token },
          }),
        )
      }

      socket.onmessage = (event: { data: string }) => {
        this.handleFrame(String(event.data))
      }

      socket.onclose = (event: { code: number }) => {
        if (!authSettled) {
          authSettled = true
          reject(
            new Error(
              event.code === 4401
                ? 'Backend rejected authentication (4401).'
                : event.code === 4403
                  ? 'Backend rejected the connection origin (4403).'
                  : `Connection closed before authentication (${event.code}).`,
            ),
          )
          return
        }
        this.handleUnexpectedClose()
      }

      socket.onerror = () => {
        /* onclose always follows; handled there. */
      }
    })
  }

  private handleFrame(raw: string): void {
    let envelope: Envelope
    try {
      envelope = parseEnvelope(raw)
    } catch {
      return // A frame we cannot parse is not worth tearing the socket down.
    }

    if (envelope.type === 'event') {
      const handlers = this.streams.get(envelope.id)
      if (!handlers) return
      if (envelope.method === METHODS.chatDelta) handlers.onDelta(envelope.params)
      else if (envelope.method === METHODS.chatDone) {
        this.streams.delete(envelope.id)
        handlers.onDone(envelope.params)
      } else if (envelope.method === METHODS.chatError) {
        this.streams.delete(envelope.id)
        handlers.onError(envelope.params)
      }
      return
    }

    const pending = this.pending.get(envelope.id)
    if (!pending) {
      // Could also be a terminal error for a stream.
      const handlers = this.streams.get(envelope.id)
      if (handlers && envelope.type === 'error') {
        this.streams.delete(envelope.id)
        handlers.onError(envelope.params)
      }
      return
    }

    this.pending.delete(envelope.id)
    if (envelope.type === 'error') {
      const message = String(envelope.params.message ?? 'Backend error')
      const correlation = envelope.params.correlation_id
      pending.reject(
        new Error(correlation ? `${message} (ref ${String(correlation)})` : message),
      )
      return
    }
    ;(pending.resolve as (v: unknown) => void)(envelope.params)
  }

  private handleUnexpectedClose(): void {
    const error = new Error('Connection lost.')
    for (const [, pending] of this.pending) pending.reject(error)
    this.pending.clear()
    for (const [, handlers] of this.streams) {
      handlers.onError({ code: 'network', message: 'Connection lost.', correlation_id: '' })
    }
    this.streams.clear()

    if (this.intentionalClose) {
      this.setState('closed')
      return
    }

    this.setState('reconnecting')
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this.reconnectAttempt,
      RECONNECT_MAX_MS,
    )
    this.reconnectAttempt += 1
    setTimeout(() => {
      if (this.intentionalClose || !this.info) return
      void this.connect(this.info).catch(() => {
        /* onclose schedules the next attempt. */
      })
    }, delay)
  }

  request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (!this.socket || this.state !== 'open') {
      return Promise.reject(new Error('Not connected to the Citrine backend.'))
    }
    const id = nextId('req')
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject } as unknown as Pending)
      this.socket!.send(JSON.stringify({ id, type: 'request', method, params }))
    })
  }

  /** Start a streaming request. Returns a cancel function. */
  stream(
    method: string,
    params: Record<string, unknown>,
    handlers: StreamHandlers,
  ): () => void {
    const id = nextId('stream')
    this.streams.set(id, handlers)
    this.socket?.send(JSON.stringify({ id, type: 'request', method, params }))

    return () => {
      if (!this.streams.has(id)) return
      this.streams.delete(id)
      this.socket?.send(
        JSON.stringify({
          id: nextId('cancel'),
          type: 'request',
          method: METHODS.chatCancel,
          params: { target_id: id },
        }),
      )
    }
  }

  close(): void {
    this.intentionalClose = true
    this.socket?.close()
    this.socket = null
    this.setState('closed')
  }
}
