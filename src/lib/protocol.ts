import { z } from 'zod'

/**
 * Mirror of backend/citrine/protocol.py. The two are hand-maintained, and
 * tests/fixtures/protocol is validated from both sides to catch drift.
 */

export const MESSAGE_TYPES = ['request', 'response', 'event', 'error'] as const
export type MessageType = (typeof MESSAGE_TYPES)[number]

export const ERROR_CODES = [
  'auth',
  'rate_limit',
  'quota',
  'network',
  'model_not_found',
  'context_length',
  'server',
] as const
export type ErrorCode = (typeof ERROR_CODES)[number]

export const METHODS = {
  auth: 'auth',
  appStatus: 'app.status',
  echo: 'echo',
  commandRun: 'command.run',
  chatSend: 'chat.send',
  chatCancel: 'chat.cancel',
  chatDelta: 'chat.delta',
  chatDone: 'chat.done',
  chatError: 'chat.error',
  /** Declared for slice 4; not implemented in this slice. */
  toolConfirm: 'tool.confirm',
} as const

export const envelopeSchema = z.object({
  id: z.string().min(1),
  type: z.enum(MESSAGE_TYPES),
  method: z.string().min(1),
  params: z.record(z.string(), z.unknown()).default({}),
})

export type Envelope = z.infer<typeof envelopeSchema>

export interface ErrorPayload {
  code: ErrorCode
  message: string
  correlation_id: string
}

export interface ChatDelta {
  content: string
}

export interface ChatDone {
  prompt_tokens: number
  completion_tokens: number
  finish_reason: string
}

export function parseEnvelope(raw: string): Envelope {
  const parsed: unknown = JSON.parse(raw)
  return envelopeSchema.parse(parsed)
}

export function serialiseEnvelope(envelope: Envelope): string {
  return JSON.stringify(envelope)
}

let counter = 0
/** Monotonic, collision-free within a session; ids need not be UUIDs. */
export function nextId(prefix = 'req'): string {
  counter += 1
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}`
}
