import { create } from 'zustand'
import type { ConnectionState } from './transport'

export type LineKind = 'input' | 'output' | 'error'

export interface Line {
  id: string
  kind: LineKind
  text: string
}

interface AppState {
  connection: ConnectionState
  lines: Line[]
  addLine: (kind: LineKind, text: string) => void
  setConnection: (state: ConnectionState) => void
  reset: () => void
}

let lineCounter = 0

export const useAppStore = create<AppState>((set) => ({
  connection: 'idle',
  lines: [],
  addLine: (kind, text) =>
    set((s) => {
      lineCounter += 1
      return { lines: [...s.lines, { id: `line-${lineCounter}`, kind, text }] }
    }),
  setConnection: (connection) => set({ connection }),
  reset: () => set({ connection: 'idle', lines: [] }),
}))
