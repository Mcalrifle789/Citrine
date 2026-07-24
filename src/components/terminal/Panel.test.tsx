import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Panel } from './Panel'

describe('Panel', () => {
  it('renders its title', () => {
    render(<Panel title="Available Commands">body</Panel>)
    expect(screen.getByText('Available Commands')).toBeDefined()
  })

  it('renders its children', () => {
    render(<Panel title="Status">the body</Panel>)
    expect(screen.getByText('the body')).toBeDefined()
  })

  it('exposes the title to assistive technology as a group label', () => {
    render(<Panel title="Recent Projects">body</Panel>)
    expect(screen.getByRole('group', { name: 'Recent Projects' })).toBeDefined()
  })
})
