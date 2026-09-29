import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LaunchAnimation } from './LaunchAnimation'
import { LAUNCH_TRAJECTORY } from '../lib/launch'

/**
 * The launch overlay.
 *
 * The motion itself is covered where it is produced — by the solver's tests in
 * backend/tests/test_native_tools.py and the sampler's in src/lib/launch.test.ts.
 * What is left for here is the part jsdom can actually observe: that the tree
 * and logo are on screen, that the frame loop drives the logo's transform, and
 * that the overlay always gets out of the way.
 */
describe('LaunchAnimation', () => {
  let frame: ((now: number) => void) | null = null
  let now = 0

  beforeEach(() => {
    vi.useFakeTimers()
    now = 0
    frame = null

    // A controllable clock: each flush advances time and runs whatever the
    // component scheduled, so the flight can be stepped deterministically.
    vi.stubGlobal(
      'requestAnimationFrame',
      (callback: (t: number) => void) => {
        frame = callback
        return 1
      },
    )
    vi.stubGlobal('cancelAnimationFrame', () => {
      frame = null
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  function flush(ms: number): void {
    now += ms
    const callback = frame
    frame = null
    if (callback) act(() => callback(now))
  }

  it('shows the blueberry tree', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    expect(document.querySelector('.bt-tree')).toBeTruthy()
  })

  it('grows the tree from the committed asset', () => {
    // Inlined rather than loaded through <img> so the theme's CSS reaches the
    // branches and fruit.
    render(<LaunchAnimation onComplete={vi.fn()} />)
    expect(document.querySelectorAll('.bt-branch').length).toBeGreaterThan(20)
    expect(document.querySelectorAll('.bt-berry').length).toBeGreaterThan(5)
  })

  it('marks the branch the logo departs from', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    expect(document.querySelector('#bt-anchor')).toBeTruthy()
  })

  it('shows the logo', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    expect(document.querySelector('.ct-launch__logo')).toBeTruthy()
  })

  it('hides the logo from assistive tech', () => {
    // The wordmark is decorative here; the shell underneath carries the name.
    render(<LaunchAnimation onComplete={vi.fn()} />)
    expect(document.querySelector('.ct-launch__logo')?.getAttribute('alt')).toBe('')
  })

  it('enters the flight phase immediately', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    expect(screen.getByTestId('launch-animation').dataset.phase).toBe('flight')
  })

  it('drives the logo transform from the trajectory', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    const logo = document.querySelector('.ct-launch__logo') as HTMLElement

    flush(0)
    const first = logo.style.transform
    flush(300)

    expect(first).toContain('translate')
    expect(logo.style.transform).not.toBe(first)
  })

  it('fades the logo in rather than popping it on', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    const logo = document.querySelector('.ct-launch__logo') as HTMLElement
    flush(0)
    expect(Number(logo.style.opacity)).toBeLessThan(0.1)
  })

  it('reports the landing so the tree can react to it', () => {
    render(<LaunchAnimation onComplete={vi.fn()} />)
    flush(0)
    flush(LAUNCH_TRAJECTORY.landedAtMs + 50)
    expect(screen.getByTestId('launch-animation').dataset.phase).toBe('landed')
  })

  it('hands off once the flight is over', () => {
    const onComplete = vi.fn()
    render(<LaunchAnimation onComplete={onComplete} />)

    flush(0)
    flush(LAUNCH_TRAJECTORY.durationMs + 1000)
    act(() => {
      vi.advanceTimersByTime(400)
    })

    expect(onComplete).toHaveBeenCalled()
  })

  it('settles on its mark when skipped', () => {
    // Nobody should have to sit through an intro twice.
    const onComplete = vi.fn()
    render(<LaunchAnimation onComplete={onComplete} />)
    flush(0)

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
      vi.advanceTimersByTime(400)
    })

    const logo = document.querySelector('.ct-launch__logo') as HTMLElement
    expect(logo.style.opacity).toBe('1')
    expect(logo.style.transform).toContain('scale(1.0000, 1.0000)')
    expect(onComplete).toHaveBeenCalled()
  })

  it('can be skipped by clicking', () => {
    const onComplete = vi.fn()
    render(<LaunchAnimation onComplete={onComplete} />)
    flush(0)

    act(() => {
      window.dispatchEvent(new Event('pointerdown'))
      vi.advanceTimersByTime(400)
    })

    expect(onComplete).toHaveBeenCalled()
  })

  it('hands off exactly once however often it is skipped', () => {
    const onComplete = vi.fn()
    render(<LaunchAnimation onComplete={onComplete} />)
    flush(0)

    act(() => {
      window.dispatchEvent(new Event('pointerdown'))
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
      vi.advanceTimersByTime(800)
    })

    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('stops listening after it unmounts', () => {
    const onComplete = vi.fn()
    const { unmount } = render(<LaunchAnimation onComplete={onComplete} />)
    flush(0)
    unmount()

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
      vi.advanceTimersByTime(800)
    })

    expect(onComplete).not.toHaveBeenCalled()
  })
})
