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

interface AppState {
  connection: ConnectionState
  lines: Line[]
  addLine: (kind: LineKind, text: string, files?: string[]) => void
  setConnection: (state: ConnectionState) => void
  reset: () => void
}

let lineCounter = 0

export const useAppStore = create<AppState>((set) => ({
  connection: 'idle',
  lines: [],
  addLine: (kind, text, files) =>
    set((s) => {
      lineCounter += 1
      const line: Line = { id: `line-${lineCounter}`, kind, text }
      if (files && files.length > 0) line.files = files
      return { lines: [...s.lines, line] }
    }),
  setConnection: (connection) => set({ connection }),
  reset: () => set({ connection: 'idle', lines: [] }),
}))
