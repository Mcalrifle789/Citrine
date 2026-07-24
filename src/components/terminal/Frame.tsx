import type { ReactNode } from 'react'

interface FrameProps {
  title: string
  children: ReactNode
}

/** Full-application border carrying the version string in its top edge. */
export function Frame({ title, children }: FrameProps) {
  return (
    <div className="ct-frame">
      <span className="ct-frame__title">{title}</span>
      <div className="ct-frame__body">{children}</div>
    </div>
  )
}
