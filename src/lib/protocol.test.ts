import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, parseEnvelope } from './protocol'

const FIXTURES = resolve(__dirname, '../../tests/fixtures/protocol')
const files = readdirSync(FIXTURES).filter((f) => f.endsWith('.json'))

describe('protocol contract', () => {
  it('finds the shared fixtures', () => {
    expect(files).toHaveLength(7)
  })

  it.each(files)('parses %s', (file) => {
    const raw = readFileSync(resolve(FIXTURES, file), 'utf-8')
    const envelope = parseEnvelope(raw)
    expect(envelope.id).toBeTruthy()
    expect(envelope.method).toBeTruthy()
  })

  it.each(files)('round-trips %s without loss', (file) => {
    const raw = readFileSync(resolve(FIXTURES, file), 'utf-8')
    expect(JSON.parse(JSON.stringify(parseEnvelope(raw)))).toEqual(JSON.parse(raw))
  })

  it('exposes the same error taxonomy as the backend', () => {
    expect([...ERROR_CODES].sort()).toEqual(
      ['auth', 'context_length', 'model_not_found', 'network', 'quota', 'rate_limit', 'server'],
    )
  })

  it('rejects an unknown message type', () => {
    expect(() => parseEnvelope('{"id":"x","type":"telepathy","method":"echo","params":{}}')).toThrow()
  })

  it('rejects a frame with no id', () => {
    expect(() => parseEnvelope('{"type":"request","method":"echo","params":{}}')).toThrow()
  })

  it('rejects malformed JSON', () => {
    expect(() => parseEnvelope('{not json')).toThrow()
  })
})
