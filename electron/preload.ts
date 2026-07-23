import { contextBridge } from 'electron'

// Task 7 replaces this stub with the real backend handshake.
contextBridge.exposeInMainWorld('citrine', {
  getBackendInfo: async (): Promise<{ port: number; token: string } | null> => null,
})
