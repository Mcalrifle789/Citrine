import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBar } from './StatusBar'

describe('StatusBar', () => {
  it('renders left and right segments', () => {
    render(
      <StatusBar
        segments={[{ id: 'app', label: 'citrine' }]}
        right={[{ id: 'clock', label: '11:58 PM' }]}
      />,
    )
    expect(screen.getByText('citrine')).toBeDefined()
    expect(screen.getByText('11:58 PM')).toBeDefined()
  })

  it('applies the tone as a data attribute so CSS owns the colour', () => {
    render(<StatusBar segments={[{ id: 'git', label: 'main', tone: 'gold' }]} right={[]} />)
    expect(screen.getByText('main').dataset.tone).toBe('gold')
  })
})
