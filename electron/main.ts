import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { resolve } from 'node:path'
import { Sidecar, type BackendInfo } from './sidecar'

const projectRoot = resolve(__dirname, '../..')
const rendererOrigin = process.env.ELECTRON_RENDERER_URL
  ? new URL(process.env.ELECTRON_RENDERER_URL).origin
  : 'file://'

let sidecar: Sidecar | null = null
let backendInfo: BackendInfo | null = null

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1680,
    height: 960,
    backgroundColor: '#05030F',
    show: false,
    webPreferences: {
      preload: resolve(__dirname, '../preload/preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  win.once('ready-to-show', () => win.show())

  if (process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void win.loadFile(resolve(__dirname, '../renderer/index.html'))
  }
  return win
}

function broadcast(channel: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send(channel, payload)
  }
}

void app.whenReady().then(async () => {
  ipcMain.handle('citrine:getBackendInfo', () => backendInfo)

  sidecar = new Sidecar(projectRoot, rendererOrigin)
  sidecar.onStateChange((state) => {
    if (state !== 'ready') backendInfo = null
    else backendInfo = sidecar?.getInfo() ?? null
    broadcast('citrine:sidecarState', state)
  })

  try {
    backendInfo = await sidecar.start()
  } catch (error) {
    // A silent failure here is the most likely way to waste an hour, so it
    // is always surfaced with the captured stderr rather than a blank window.
    dialog.showErrorBox(
      'Citrine backend failed to start',
      error instanceof Error ? error.message : String(error),
    )
    app.quit()
    return
  }

  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => sidecar?.stop())
