export {}

declare global {
  interface Window {
    citrine: {
      getBackendInfo: () => Promise<{ port: number; token: string } | null>
      onSidecarState: (cb: (state: string) => void) => void
    }
  }
}
