import {
  LAUNCH_TRAJECTORY,
  type LaunchFrame,
  type LaunchTrajectory,
} from '../generated/launchTrajectory'

/**
 * Playback for the launch animation's baked trajectory.
 *
 * The motion itself is solved offline (native/trajectory/trajectory.c) and
 * committed as a keyframe table. All that is left at runtime is reading the
 * table at the current time — which is deliberately a pure function so it can
 * be tested without a DOM or a clock.
 */

export type { LaunchFrame, LaunchTrajectory }
export { LAUNCH_TRAJECTORY }

const STORAGE_KEY = 'citrine.launch.lastPlayed'

/** How long the logo holds on its mark before the shell takes over. */
export const SETTLE_HOLD_MS = 420

function lerp(a: number, b: number, alpha: number): number {
  return a + (b - a) * alpha
}

function interpolate(a: LaunchFrame, b: LaunchFrame, alpha: number): LaunchFrame {
  return {
    t: lerp(a.t, b.t, alpha),
    x: lerp(a.x, b.x, alpha),
    y: lerp(a.y, b.y, alpha),
    sx: lerp(a.sx, b.sx, alpha),
    sy: lerp(a.sy, b.sy, alpha),
    rotate: lerp(a.rotate, b.rotate, alpha),
    opacity: lerp(a.opacity, b.opacity, alpha),
  }
}

/**
 * Read the trajectory at `seconds`, interpolating between baked frames.
 *
 * The table is sampled at a fixed rate but displays are not — a 120 Hz panel
 * asks for positions the solver never wrote. Interpolating rather than
 * snapping to the nearest frame is what keeps the motion smooth there instead
 * of stepping at 60 Hz on a faster display.
 *
 * Times outside the table clamp to its ends, so an overrun holds the final
 * resting pose rather than reading past the array.
 */
export function sampleTrajectory(
  seconds: number,
  trajectory: LaunchTrajectory = LAUNCH_TRAJECTORY,
): LaunchFrame {
  const { frames } = trajectory
  if (frames.length === 0) {
    throw new Error('launch trajectory has no frames')
  }

  const first = frames[0]!
  const last = frames[frames.length - 1]!

  // NaN needs its own check because every comparison against it is false, so
  // it would otherwise fall through to the interpolation and poison it. The
  // infinities are left to the clamps below, which handle them correctly and
  // give callers a cheap way to ask for the final resting pose.
  if (Number.isNaN(seconds) || seconds <= first.t) return first
  if (seconds >= last.t) return last

  // Frames are evenly spaced, so the bracketing pair is an index calculation
  // rather than a search. The clamp covers the last interval, where rounding
  // can otherwise index one past the end.
  const step = 1 / trajectory.fps
  const approximate = Math.floor((seconds - first.t) / step)
  let index = Math.min(Math.max(approximate, 0), frames.length - 2)

  // Guard against drift if the table is ever not perfectly uniform.
  while (index > 0 && frames[index]!.t > seconds) index -= 1
  while (index < frames.length - 2 && frames[index + 1]!.t <= seconds) index += 1

  const a = frames[index]!
  const b = frames[index + 1]!
  const span = b.t - a.t
  const alpha = span > 1e-9 ? (seconds - a.t) / span : 0

  return interpolate(a, b, alpha)
}

/**
 * The CSS transform for a frame, given the stage's pixel size.
 *
 * Positions are stage-relative, so the same table drives any window size.
 * `translate(-50%, -50%)` comes first so the logo is positioned by its centre
 * — rotating and scaling about a corner would swing it around visibly.
 */
export function frameTransform(
  frame: LaunchFrame,
  stageWidth: number,
  stageHeight: number,
): string {
  const x = frame.x * stageWidth
  const y = frame.y * stageHeight
  return (
    `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) ` +
    `translate(-50%, -50%) ` +
    `rotate(${frame.rotate.toFixed(2)}deg) ` +
    `scale(${frame.sx.toFixed(4)}, ${frame.sy.toFixed(4)})`
  )
}

/**
 * Whether the user has asked for reduced motion.
 *
 * A logo tumbling out of a tree is exactly the kind of large, unprompted
 * movement that setting exists to suppress, so the animation is skipped
 * outright rather than merely shortened.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Whether the animation should play on this start.
 *
 * It plays on a genuine app launch but not on a renderer reload — during
 * development the reload happens on every save, and sitting through the fall
 * each time gets old within about a minute.
 */
export function shouldPlayLaunch(withinMs = 8000): boolean {
  if (prefersReducedMotion()) return false
  try {
    const previous = window.sessionStorage.getItem(STORAGE_KEY)
    if (previous && Date.now() - Number(previous) < withinMs) return false
  } catch {
    // Storage can be unavailable (private mode, restrictive policy). Playing
    // the animation is the harmless outcome, so fall through to it.
  }
  return true
}

/** Record that the animation has played, for `shouldPlayLaunch`. */
export function markLaunchPlayed(): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, String(Date.now()))
  } catch {
    // Not being able to remember is not worth failing a launch over.
  }
}
