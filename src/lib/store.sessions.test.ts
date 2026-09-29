import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from './store'

/**
 * The scrollback is per conversation, not global.
 *
 * The reported bug: creating a new session left the previous session's lines on
 * screen, so a fresh conversation looked like a continuation of the old one.
 * The backend names the active conversation (`app.status.transcript_key`) and
 * the store files lines under that name, so a new name is a blank window.
 */

const store = () => useAppStore.getState()

describe('transcripts', () => {
  beforeEach(() => store().reset())

  it('blanks the window when the conversation changes', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'from the old session')
    store().switchTranscript('Default::session-1#0')
    expect(store().lines).toEqual([])
  })

  it('does not leave the old lines reachable through the view', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('output', 'old output')
    store().switchTranscript('Default::session-1#0')
    expect(store().lines.map((l) => l.text)).not.toContain('old output')
  })

  it('files new lines under the conversation that is active', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Default::session-1#0')
    store().addLine('input', 'two')
    expect(store().lines.map((l) => l.text)).toEqual(['two'])
  })

  it('brings a conversation back when the user returns to it', () => {
    // Otherwise /session is a destructive command wearing a navigation label.
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Default::session-1#0')
    store().addLine('input', 'two')
    store().switchTranscript('Default::main#0')
    expect(store().lines.map((l) => l.text)).toEqual(['one'])
  })

  it('treats the same agent in a different session as a different conversation', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Default::work#0')
    expect(store().lines).toEqual([])
  })

  it('treats a different agent in the same session as a different conversation', () => {
    // An agent switch is a model switch, so the context is not shared.
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Scout::main#0')
    expect(store().lines).toEqual([])
  })

  it('blanks the window when only the reset epoch moves', () => {
    // /reset keeps the session name, so the epoch is the only signal.
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Default::main#1')
    expect(store().lines).toEqual([])
  })

  it('does not restore a transcript that was reset away', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Default::main#1')
    store().switchTranscript('Default::main#1')
    expect(store().lines).toEqual([])
  })

  it('re-reporting the same conversation changes nothing', () => {
    // app.status is refreshed after every turn, so this is the common case.
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().switchTranscript('Default::main#0')
    expect(store().lines.map((l) => l.text)).toEqual(['one'])
  })

  it('keeps what was already on screen when the first key arrives', () => {
    // Startup errors are written before the backend has reported a session;
    // throwing them away would hide the reason the app is not working.
    store().addLine('error', 'Backend is unavailable.')
    store().switchTranscript('Default::main#0')
    expect(store().lines.map((l) => l.text)).toEqual(['Backend is unavailable.'])
  })

  it('tracks which conversation is active', () => {
    store().switchTranscript('Default::session-1#0')
    expect(store().transcriptKey).toBe('Default::session-1#0')
  })

  it('clears the active conversation in place', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().clearTranscript()
    expect(store().lines).toEqual([])
    expect(store().transcriptKey).toBe('Default::main#0')
  })

  it('forgets every conversation on reset', () => {
    store().switchTranscript('Default::main#0')
    store().addLine('input', 'one')
    store().reset()
    store().switchTranscript('Default::main#0')
    expect(store().lines).toEqual([])
  })
})
