import { useCallback, useState } from 'react'
import { AppShell } from './components/AppShell'
import { LaunchAnimation } from './components/LaunchAnimation'
import { markLaunchPlayed, shouldPlayLaunch } from './lib/launch'

export function App() {
  // Decided once, on mount. Re-evaluating would restart the intro whenever
  // something unrelated caused a render.
  const [launching, setLaunching] = useState(() => shouldPlayLaunch())

  const finishLaunch = useCallback(() => {
    markLaunchPlayed()
    setLaunching(false)
  }, [])

  return (
    <>
      <div className="citrine-backdrop" aria-hidden="true" />
      {/*
        The shell mounts underneath the intro rather than after it, so the
        backend connection and the command catalog are already in flight while
        the logo is falling. By the time the overlay clears, the prompt is live.
      */}
      <AppShell />
      {launching && <LaunchAnimation onComplete={finishLaunch} />}
    </>
  )
}
