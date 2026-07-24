import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Transport, type ConnectionState } from './transport'

/** Minimal scriptable WebSocket double. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }
  send(data: string): void {
    this.sent.push(data)
  }
  close(): void {
    this.readyState = 3
    this.onclose?.({ code: 1000 })
  }
  // Test helpers
  open(): void {
    this.readyState = 1
    this.onopen?.()
  }
  receive(frame: object): void {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
  get lastSent(): Record<string, unknown> {
    return JSON.parse(this.sent[this.sent.length - 1]!)
  }
}

function connectAndAuth(transport: Transport) {
  const promise = transport.connect({ port: 5000, token: 'tok' })
  const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]!
  ws.open()
  const authFrame = ws.lastSent
  ws.receive({ id: authFrame.id, type: 'response', method: 'auth', params: { ok: true } })
  return { promise, ws }
}

describe('Transport', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  it('connects to the loopback address on the given port', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    expect(ws.url).toBe('ws://127.0.0.1:5000/ws')
  })

  it('sends the auth token as its very first frame', async () => {
    const t = new Transport()
    const promise = t.connect({ port: 5000, token: 'sekrit' })
    const ws = FakeWebSocket.instances[0]!
    ws.open()
    const first = JSON.parse(ws.sent[0]!)
    expect(first.method).toBe('auth')
    expect(first.params.token).toBe('sekrit')
    ws.receive({ id: first.id, type: 'response', method: 'auth', params: { ok: true } })
    await promise
  })

  it('resolves connect only after authentication succeeds', async () => {
    const t = new Transport()
    const states: ConnectionState[] = []
    t.onStateChange((s) => states.push(s))
    const { promise } = connectAndAuth(t)
    await promise
    expect(states).toContain('authenticating')
    expect(states.at(-1)).toBe('open')
  })

  it('rejects connect when the socket closes with 4401', async () => {
    const t = new Transport()
    const promise = t.connect({ port: 5000, token: 'bad' })
    const ws = FakeWebSocket.instances[0]!
    ws.open()
    ws.onclose?.({ code: 4401 })
    await expect(promise).rejects.toThrow(/authentication/i)
  })

  it('correlates a response to its request', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const pending = t.request<{ text: string }>('echo', { text: 'hi' })
    const sent = ws.lastSent
    ws.receive({ id: sent.id, type: 'response', method: 'echo', params: { text: 'hi' } })
    expect(await pending).toEqual({ text: 'hi' })
  })

  it('rejects a request when an error frame arrives for it', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const pending = t.request('echo', { text: 'hi' })
    const sent = ws.lastSent
    ws.receive({
      id: sent.id, type: 'error', method: 'echo',
      params: { code: 'server', message: 'boom', correlation_id: 'abc123' },
    })
    await expect(pending).rejects.toThrow(/boom/)
  })

  it('ignores a response whose id matches nothing', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    expect(() =>
      ws.receive({ id: 'nobody', type: 'response', method: 'echo', params: {} }),
    ).not.toThrow()
  })

  it('routes stream events to the matching handler by id', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const deltas: string[] = []
    let finished = false
    t.stream('chat.send', { text: 'x' }, {
      onDelta: (d) => deltas.push(d.content as string),
      onDone: () => { finished = true },
      onError: () => {},
    })
    const sent = ws.lastSent
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'He' } })
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'llo' } })
    ws.receive({ id: sent.id, type: 'event', method: 'chat.done', params: {} })
    expect(deltas).toEqual(['He', 'llo'])
    expect(finished).toBe(true)
  })

  it('stops delivering events after the stream is cancelled', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const deltas: string[] = []
    const cancel = t.stream('chat.send', {}, {
      onDelta: (d) => deltas.push(d.content as string),
      onDone: () => {},
      onError: () => {},
    })
    const sent = ws.lastSent
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'a' } })
    cancel()
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'b' } })
    expect(deltas).toEqual(['a'])
  })

  it('sends a cancel frame carrying the original request id', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const cancel = t.stream('chat.send', {}, { onDelta: () => {}, onDone: () => {}, onError: () => {} })
    const streamId = ws.lastSent.id
    cancel()
    expect(ws.lastSent.method).toBe('chat.cancel')
    expect(ws.lastSent.params).toMatchObject({ target_id: streamId })
  })

  it('fails queued requests fast when the socket is not open', async () => {
    const t = new Transport()
    await expect(t.request('echo', {})).rejects.toThrow(/not connected/i)
  })

  it('reports reconnecting when the socket drops unexpectedly', async () => {
    const t = new Transport()
    const states: ConnectionState[] = []
    const { promise, ws } = connectAndAuth(t)
    await promise
    t.onStateChange((s) => states.push(s))
    ws.onclose?.({ code: 1006 })
    expect(states).toContain('reconnecting')
  })

  it('rejects in-flight requests when the socket drops', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const pending = t.request('echo', {})
    ws.onclose?.({ code: 1006 })
    await expect(pending).rejects.toThrow(/connection lost/i)
  })
})
