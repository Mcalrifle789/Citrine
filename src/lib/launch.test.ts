import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  LAUNCH_TRAJECTORY,
  frameTransform,
  markLaunchPlayed,
  prefersReducedMotion,
  sampleTrajectory,
  shouldPlayLaunch,
  type LaunchTrajectory,
} from './launch'

function stubMatchMedia(matches: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({ matches, media: '', addEventListener: vi.fn() }),
  )
}

describe('sampleTrajectory', () => {
  it('returns the first frame at time zero', () => {
    const frame = sampleTrajectory(0)
    expect(frame.x).toBeCloseTo(LAUNCH_TRAJECTORY.anchor.x, 4)
    expect(frame.y).toBeCloseTo(LAUNCH_TRAJECTORY.anchor.y, 4)
  })

  it('holds the resting pose past the end of the table', () => {
    // An overrun must not read past the array or snap back to the start.
    const frame = sampleTrajectory(999)
    expect(frame.x).toBeCloseTo(LAUNCH_TRAJECTORY.rest.x, 4)
    expect(frame.sx).toBeCloseTo(1, 3)
  })

  it('clamps a negative time to the first frame', () => {
    expect(sampleTrajectory(-5)).toEqual(sampleTrajectory(0))
  })

  it('survives a NaN time', () => {
    // requestAnimationFrame arithmetic can produce NaN if a timestamp is
    // missing; the animation should hold a pose rather than throw. Every
    // comparison against NaN is false, so without an explicit check it would
    // fall through to the interpolation and poison the result.
    const frame = sampleTrajectory(Number.NaN)
    expect(Number.isNaN(frame.x)).toBe(false)
  })

  it('treats infinity as "the end", which is how skipping asks for it', () => {
    const frame = sampleTrajectory(Number.POSITIVE_INFINITY)
    expect(frame.sx).toBeCloseTo(1, 3)
    expect(frame.x).toBeCloseTo(LAUNCH_TRAJECTORY.rest.x, 4)
  })

  it('interpolates between baked frames', () => {
    // A 120 Hz display asks for positions the 60 Hz table never wrote.
    // Snapping instead of interpolating is what makes that step visibly.
    const a = LAUNCH_TRAJECTORY.frames[10]!
    const b = LAUNCH_TRAJECTORY.frames[11]!
    const midpoint = sampleTrajectory((a.t + b.t) / 2)

    expect(midpoint.x).toBeCloseTo((a.x + b.x) / 2, 4)
    expect(midpoint.x).not.toBeCloseTo(a.x, 6)
  })

  it('lands on the exact baked frame at a baked time', () => {
    const target = LAUNCH_TRAJECTORY.frames[30]!
    const sampled = sampleTrajectory(target.t)
    expect(sampled.x).toBeCloseTo(target.x, 5)
    expect(sampled.rotate).toBeCloseTo(target.rotate, 5)
  })

  it('advances monotonically across the whole flight', () => {
    let previous = -1
    for (let t = 0; t <= LAUNCH_TRAJECTORY.durationMs / 1000; t += 0.01) {
      const frame = sampleTrajectory(t)
      expect(frame.t).toBeGreaterThanOrEqual(previous)
      previous = frame.t
    }
  })

  it('rejects a trajectory with no frames', () => {
    const empty = { ...LAUNCH_TRAJECTORY, frames: [] } as LaunchTrajectory
    expect(() => sampleTrajectory(0, empty)).toThrow(/no frames/)
  })
})

describe('frameTransform', () => {
  it('positions by the centre of the logo', () => {
    // Without the -50% the logo would rotate and scale about its top-left
    // corner, swinging it visibly off the path.
    const transform = frameTransform(sampleTrajectory(0), 1000, 600)
    expect(transform).toContain('translate(-50%, -50%)')
  })

  it('scales stage-relative positions to pixels', () => {
    const frame = { t: 0, x: 0.5, y: 0.25, sx: 1, sy: 1, rotate: 0, opacity: 1 }
    const transform = frameTransform(frame, 1000, 800)
    expect(transform).toContain('translate(500.00px, 200.00px)')
  })

  it('carries rotation and non-uniform scale', () => {
    const frame = { t: 0, x: 0, y: 0, sx: 0.8, sy: 1.2, rotate: -30, opacity: 1 }
    const transform = frameTransform(frame, 100, 100)
    expect(transform).toContain('rotate(-30.00deg)')
    expect(transform).toContain('scale(0.8000, 1.2000)')
  })
})

describe('prefersReducedMotion', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reports the media query', () => {
    stubMatchMedia(true)
    expect(prefersReducedMotion()).toBe(true)
  })

  it('defaults to false when matchMedia is unavailable', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(prefersReducedMotion()).toBe(false)
  })
})

describe('shouldPlayLaunch', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    stubMatchMedia(false)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('plays on a cold start', () => {
    expect(shouldPlayLaunch()).toBe(true)
  })

  it('does not replay on a quick reload', () => {
    // During development the renderer reloads on every save, and sitting
    // through the fall each time gets old within about a minute.
    markLaunchPlayed()
    expect(shouldPlayLaunch()).toBe(false)
  })

  it('plays again once the window has passed', () => {
    markLaunchPlayed()
    expect(shouldPlayLaunch(0)).toBe(true)
  })

  it('never plays when reduced motion is requested', () => {
    stubMatchMedia(true)
    expect(shouldPlayLaunch()).toBe(false)
  })

  it('plays when storage is unavailable', () => {
    // Private mode or a restrictive policy. Playing is the harmless outcome.
    const broken = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
    }
    Object.defineProperty(window, 'sessionStorage', {
      value: broken,
      configurable: true,
    })
    expect(shouldPlayLaunch()).toBe(true)
    expect(() => markLaunchPlayed()).not.toThrow()
  })
})
