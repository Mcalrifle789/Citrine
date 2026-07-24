export type SegmentTone = 'accent' | 'gold' | 'ok' | 'err' | 'dim'

export interface Segment {
  id: string
  label: string
  tone?: SegmentTone
}

interface StatusBarProps {
  segments: Segment[]
  right: Segment[]
}

/** Powerline-style status strip. Tone is a data attribute; CSS owns colour. */
export function StatusBar({ segments, right }: StatusBarProps) {
  return (
    <div className="ct-statusbar" role="status">
      <div className="ct-statusbar__left">
        {segments.map((s) => (
          <span key={s.id} className="ct-statusbar__seg" data-tone={s.tone ?? 'dim'}>
            {s.label}
          </span>
        ))}
      </div>
      <div className="ct-statusbar__right">
        {right.map((s) => (
          <span key={s.id} className="ct-statusbar__seg" data-tone={s.tone ?? 'dim'}>
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
