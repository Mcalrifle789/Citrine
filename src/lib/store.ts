import { create } from 'zustand'
import type { ConnectionState } from './transport'

export type LineKind = 'input' | 'output' | 'error'

export interface Line {
  id: string
  kind: LineKind
  text: string
  /** Attachment names sent with this line, when it carried files. */
  files?: string[]
}

/**
 * The key a transcript is filed under. The backend composes it from the active
 * agent, the active session, and a reset epoch (`app.status.transcript_key`),
 * so `/new`, `/session`, `/agent` and `/reset` each produce a different one.
 */
export type TranscriptKey = string

/** Where lines go before the backend has told us which session we are in. */
const INITIAL_KEY: TranscriptKey = 'pending'

interface AppState {
  connection: ConnectionState
  /** Lines of the active transcript. The view renders only this. */
  lines: Line[]
  transcriptKey: TranscriptKey
  transcripts: Record<TranscriptKey, Line[]>
  addLine: (kind: LineKind, text: string, files?: string[]) => void
  setConnection: (state: ConnectionState) => void
  /**
   * Point the window at `key`'s transcript.
   *
   * A key we have never seen starts empty, which is what blanks the window on
   * a new session. A key we have seen comes back with its lines, so switching
   * away from a session and back does not destroy it.
   */
  switchTranscript: (key: TranscriptKey) => void
  /** Discard the active transcript's lines, keeping the key. */
  clearTranscript: () => void
  reset: () => void
}

let lineCounter = 0

export const useAppStore = create<AppState>((set) => ({
  connection: 'idle',
  lines: [],
  transcriptKey: INITIAL_KEY,
  transcripts: {},
  addLine: (kind, text, files) =>
    set((s) => {
      lineCounter += 1
      const line: Line = { id: `line-${lineCounter}`, kind, text }
      if (files && files.length > 0) line.files = files
      const lines = [...s.lines, line]
      return { lines, transcripts: { ...s.transcripts, [s.transcriptKey]: lines } }
    }),
  setConnection: (connection) => set({ connection }),
  switchTranscript: (key) =>
    set((s) => {
      if (key === s.transcriptKey) return s
      // The first key the backend reports adopts whatever is already on screen
      // (connection banners, errors) rather than throwing it away — at that
      // point nothing has been switched away from yet.
      const carried = s.transcriptKey === INITIAL_KEY ? s.lines : (s.transcripts[key] ?? [])
      const transcripts = { ...s.transcripts, [s.transcriptKey]: s.lines, [key]: carried }
      delete transcripts[INITIAL_KEY]
      return { transcriptKey: key, lines: carried, transcripts }
    }),
  clearTranscript: () =>
    set((s) => ({ lines: [], transcripts: { ...s.transcripts, [s.transcriptKey]: [] } })),
  reset: () =>
    set({ connection: 'idle', lines: [], transcriptKey: INITIAL_KEY, transcripts: {} }),
}))
