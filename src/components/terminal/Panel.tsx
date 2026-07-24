import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  children: ReactNode
}

/**
 * A bordered region with its title inset into the top border line — the
 * signature motif of the Citrine design. The title sits above the border
 * with a panel-coloured background, "cutting" the line behind it.
 */
export function Panel({ title, children }: PanelProps) {
  return (
    <section className="ct-panel" role="group" aria-label={title}>
      <span className="ct-panel__title">{title}</span>
      <div className="ct-panel__body">{children}</div>
    </section>
  )
}
