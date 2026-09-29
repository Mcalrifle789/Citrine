import { useEffect, useRef, useState } from 'react'
import treeMarkup from '../assets/blueberry-tree.svg?raw'
import wordmark from '../assets/wordmark.png'
import {
  LAUNCH_TRAJECTORY,
  SETTLE_HOLD_MS,
  frameTransform,
  sampleTrajectory,
} from '../lib/launch'

interface LaunchAnimationProps {
  onComplete: () => void
}

/** Phases exist so CSS can react to the flight without reading frame data. */
type Phase = 'hanging' | 'flight' | 'landed' | 'done'

/**
 * Citrine's cold-open: the logo detaches from a blueberry tree, arcs out,
 * falls, bounces, and settles — then hands off to the shell.
 *
 * The motion is not authored here. It is solved offline by a physics
 * integrator (native/trajectory/trajectory.c) and read out of a baked table,
 * because the realism the brief asks for comes from drag, restitution and
 * fall-driven growth, none of which a CSS keyframe list can express.
 *
 * Per-frame updates are written straight to the node's style. Driving this
 * through React state would re-render the whole overlay — which contains
 * several hundred SVG nodes — sixty times a second, for a tree that never
 * changes.
 */
export function LaunchAnimation({ onComplete }: LaunchAnimationProps) {
  const stageRef = useRef<HTMLDivElement>(null)
  const logoRef = useRef<HTMLImageElement>(null)
  const [phase, setPhase] = useState<Phase>('hanging')

  // Held in a ref so the rAF loop and the skip handler share one latch without
  // the loop having to be torn down and rebuilt when it flips.
  const finished = useRef(false)

  useEffect(() => {
    const stage = stageRef.current
    const logo = logoRef.current
    if (!stage || !logo) return

    let raf = 0
    let start: number | null = null
    let landed = false

    const finish = (): void => {
      if (finished.current) return
      finished.current = true
      setPhase('done')
      // The fade-out is a CSS transition on the overlay; unmounting happens
      // when the parent responds to onComplete.
      window.setTimeout(onComplete, 260)
    }

    /** Jump to the resting pose. Used by the skip affordances. */
    const settle = (): void => {
      const last = sampleTrajectory(Number.POSITIVE_INFINITY)
      const { width, height } = stage.getBoundingClientRect()
      logo.style.transform = frameTransform(last, width, height)
      logo.style.opacity = '1'
      setPhase('landed')
      finish()
    }

    const tick = (now: number): void => {
      if (start === null) start = now
      const elapsed = now - start
      const frame = sampleTrajectory(elapsed / 1000)

      // Read the size every frame: the window can be resized mid-flight, and
      // a stale size would leave the logo landing off its mark.
      const { width, height } = stage.getBoundingClientRect()
      logo.style.transform = frameTransform(frame, width, height)
      logo.style.opacity = String(frame.opacity)

      if (!landed && elapsed >= LAUNCH_TRAJECTORY.landedAtMs) {
        landed = true
        setPhase('landed')
      }

      if (elapsed >= LAUNCH_TRAJECTORY.durationMs + SETTLE_HOLD_MS) {
        finish()
        return
      }
      raf = window.requestAnimationFrame(tick)
    }

    setPhase('flight')
    raf = window.requestAnimationFrame(tick)

    // Any deliberate input means "get on with it". Nobody should have to sit
    // through an intro twice, and the second time is always one time too many.
    const skip = (): void => {
      window.cancelAnimationFrame(raf)
      settle()
    }
    window.addEventListener('keydown', skip)
    window.addEventListener('pointerdown', skip)

    return () => {
      window.cancelAnimationFrame(raf)
      window.removeEventListener('keydown', skip)
      window.removeEventListener('pointerdown', skip)
    }
  }, [onComplete])

  return (
    <div
      className="ct-launch"
      data-phase={phase}
      data-testid="launch-animation"
      role="presentation"
    >
      <div className="ct-launch__stage" ref={stageRef}>
        {/*
          Inlined rather than loaded through <img> so the theme's CSS reaches
          the branches, foliage and fruit. An <img> is an opaque document; its
          internals cannot be recoloured or swayed from outside.
        */}
        <div
          className="ct-launch__tree"
          // The markup is a build artifact from native/tree/tree.cpp, committed
          // in this repo — not user or network input.
          dangerouslySetInnerHTML={{ __html: treeMarkup }}
        />
        <img
          ref={logoRef}
          className="ct-launch__logo citrine-wordmark"
          src={wordmark}
          alt=""
          draggable={false}
        />
      </div>
      <p className="ct-launch__skip" aria-hidden="true">
        press any key to skip
      </p>
    </div>
  )
}
