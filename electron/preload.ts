import { contextBridge, ipcRenderer } from 'electron'

/** The entire renderer-facing surface. Nothing else crosses the bridge. */
contextBridge.exposeInMainWorld('citrine', {
  getBackendInfo: (): Promise<{ port: number; token: string } | null> =>
    ipcRenderer.invoke('citrine:getBackendInfo'),
  onSidecarState: (cb: (state: string) => void): void => {
    ipcRenderer.on('citrine:sidecarState', (_event, state: string) => cb(state))
  },
})
