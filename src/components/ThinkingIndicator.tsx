import { useEffect, useState } from 'react'

interface ThinkingIndicatorProps {
  /** Attachment names, when the turn started with files. */
  files?: string[]
}

/**
 * Stages the indicator walks through while a turn is in flight.
 *
 * These are honest about what is knowable. The backend does not report
 * progress, so this does not claim to: it says the request is out and time is
 * passing, which is true, rather than inventing a percentage.
 */
const STAGES: Array<{ at: number; label: string }> = [
  { at: 0, label: 'thinking' },
  { at: 1200, label: 'working through it' },
  { at: 4000, label: 'still working' },
  { at: 12000, label: 'this one is taking a while' },
]

const FILE_STAGES: Array<{ at: number; label: string }> = [
  { at: 0, label: 'reading your files' },
  { at: 900, label: 'thinking' },
  { at: 3000, label: 'working through it' },
  { at: 9000, label: 'still working' },
  { at: 20000, label: 'this one is taking a while' },
]

function stageFor(elapsed: number, stages: typeof STAGES): string {
  let label = stages[0]!.label
  for (const stage of stages) {
    if (elapsed >= stage.at) label = stage.label
  }
  return label
}

/**
 * Shown between sending a turn and the reply arriving.
 *
 * Without it a request that takes eight seconds is indistinguishable from one
 * that has failed silently, and dropping in a large file makes that worse
 * because the pause gets longer exactly when the user is least sure anything
 * was received. So it names the files it has and counts the seconds.
 */
export function ThinkingIndicator({ files = [] }: ThinkingIndicatorProps) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    // 100 ms rather than per-frame: the only thing moving is a tenth-of-a-
    // second counter, and this runs while the app is otherwise waiting.
    const timer = window.setInterval(() => setElapsed(Date.now() - started), 100)
    return () => window.clearInterval(timer)
  }, [])

  const stages = files.length > 0 ? FILE_STAGES : STAGES
  const label = stageFor(elapsed, stages)
  const seconds = (elapsed / 1000).toFixed(1)

  return (
    <div
      className="ct-thinking"
      data-testid="thinking-indicator"
      role="status"
      aria-live="polite"
    >
      <span className="ct-thinking__orb" aria-hidden="true">
        <span className="ct-thinking__ring" />
        <span className="ct-thinking__ring" />
        <span className="ct-thinking__core" />
      </span>

      <span className="ct-thinking__label">
        Citrine is {label}
        <span className="ct-thinking__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </span>

      {files.length > 0 && (
        <span className="ct-thinking__files">
          {files.map((name) => (
            <span key={name} className="ct-thinking__file">
              {name}
            </span>
          ))}
        </span>
      )}

      <span className="ct-thinking__elapsed">{seconds}s</span>
    </div>
  )
}
