import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from './store'

describe('app store', () => {
  beforeEach(() => useAppStore.getState().reset())

  it('starts with no lines and an idle connection', () => {
    expect(useAppStore.getState().lines).toEqual([])
    expect(useAppStore.getState().connection).toBe('idle')
  })

  it('appends lines in order', () => {
    useAppStore.getState().addLine('input', 'first')
    useAppStore.getState().addLine('output', 'second')
    expect(useAppStore.getState().lines.map((l) => l.text)).toEqual(['first', 'second'])
  })

  it('assigns each line a unique id', () => {
    useAppStore.getState().addLine('input', 'a')
    useAppStore.getState().addLine('input', 'a')
    const [one, two] = useAppStore.getState().lines
    expect(one!.id).not.toBe(two!.id)
  })

  it('records the line kind so the view can style it', () => {
    useAppStore.getState().addLine('error', 'boom')
    expect(useAppStore.getState().lines[0]!.kind).toBe('error')
  })

  it('updates the connection state', () => {
    useAppStore.getState().setConnection('open')
    expect(useAppStore.getState().connection).toBe('open')
  })
})
