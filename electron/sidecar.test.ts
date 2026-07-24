import { describe, expect, it } from 'vitest'
import { MAX_RESTART_ATTEMPTS, nextBackoffMs, parseReadyLine } from './sidecar'

describe('parseReadyLine', () => {
  it('extracts the port from a ready handshake', () => {
    expect(parseReadyLine('{"event": "ready", "port": 54873}')).toBe(54873)
  })

  it('tolerates surrounding whitespace', () => {
    expect(parseReadyLine('  {"event":"ready","port":1234}  \r')).toBe(1234)
  })

  it('ignores unrelated JSON lines', () => {
    expect(parseReadyLine('{"event": "something-else", "port": 1}')).toBeNull()
  })

  it('ignores non-JSON noise', () => {
    expect(parseReadyLine('INFO starting up')).toBeNull()
  })

  it('rejects a ready line with a missing port', () => {
    expect(parseReadyLine('{"event": "ready"}')).toBeNull()
  })

  it('rejects a non-numeric port', () => {
    expect(parseReadyLine('{"event": "ready", "port": "54873"}')).toBeNull()
  })

  it('rejects port zero, which means the socket never bound', () => {
    expect(parseReadyLine('{"event": "ready", "port": 0}')).toBeNull()
  })
})

describe('nextBackoffMs', () => {
  it('starts small', () => {
    expect(nextBackoffMs(0)).toBe(250)
  })

  it('doubles with each attempt', () => {
    expect(nextBackoffMs(1)).toBe(500)
    expect(nextBackoffMs(2)).toBe(1000)
  })

  it('caps so a persistent failure does not back off forever', () => {
    expect(nextBackoffMs(99)).toBeLessThanOrEqual(8000)
  })

  it('gives up after five attempts, per spec', () => {
    expect(MAX_RESTART_ATTEMPTS).toBe(5)
  })
})
