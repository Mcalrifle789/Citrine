import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ThinkingIndicator } from './ThinkingIndicator'

describe('ThinkingIndicator', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  function advance(ms: number): void {
    act(() => {
      vi.advanceTimersByTime(ms)
    })
  }

  it('says who is working', () => {
    render(<ThinkingIndicator />)
    expect(screen.getByTestId('thinking-indicator').textContent).toContain('Citrine is')
  })

  it('starts by saying it is thinking', () => {
    render(<ThinkingIndicator />)
    expect(screen.getByTestId('thinking-indicator').textContent).toContain('thinking')
  })

  it('leads with the files when the turn started with some', () => {
    // Dropping in a large file makes the pause longer exactly when the user is
    // least sure the file was received, so that is what it addresses first.
    render(<ThinkingIndicator files={['main.py']} />)
    expect(screen.getByTestId('thinking-indicator').textContent).toContain(
      'reading your files',
    )
  })

  it('names every attached file', () => {
    render(<ThinkingIndicator files={['main.py', 'notes.md']} />)
    const text = screen.getByTestId('thinking-indicator').textContent
    expect(text).toContain('main.py')
    expect(text).toContain('notes.md')
  })

  it('counts up so a long wait is visibly still running', () => {
    render(<ThinkingIndicator />)
    advance(2500)
    expect(screen.getByTestId('thinking-indicator').textContent).toContain('2.5s')
  })

  it('escalates its wording as the wait grows', () => {
    render(<ThinkingIndicator />)
    advance(5000)
    expect(screen.getByTestId('thinking-indicator').textContent).toContain(
      'still working',
    )
  })

  it('acknowledges an unusually long wait', () => {
    render(<ThinkingIndicator />)
    advance(13000)
    expect(screen.getByTestId('thinking-indicator').textContent).toContain(
      'taking a while',
    )
  })

  it('is announced politely rather than interrupting', () => {
    // It updates ten times a second; an assertive region would talk over
    // everything else on screen.
    render(<ThinkingIndicator />)
    const indicator = screen.getByTestId('thinking-indicator')
    expect(indicator.getAttribute('role')).toBe('status')
    expect(indicator.getAttribute('aria-live')).toBe('polite')
  })

  it('stops its timer when it goes away', () => {
    const { unmount } = render(<ThinkingIndicator />)
    unmount()
    expect(() => advance(5000)).not.toThrow()
  })
})
