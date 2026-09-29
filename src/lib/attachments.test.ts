import { describe, expect, it } from 'vitest'
import {
  MAX_FILES,
  MAX_TEXT_BYTES,
  formatBytes,
  isProbablyText,
  readAttachments,
  summarise,
  toWire,
  type Attachment,
} from './attachments'

function file(name: string, content: string, mime = ''): File {
  return new File([content], name, { type: mime })
}

describe('isProbablyText', () => {
  it('accepts anything the browser calls text', () => {
    expect(isProbablyText('a.txt', 'text/plain')).toBe(true)
  })

  it('accepts structured formats the browser calls application/*', () => {
    expect(isProbablyText('package.json', 'application/json')).toBe(true)
  })

  it('falls back to the extension when the browser has no opinion', () => {
    // Browsers report "" for plenty of ordinary source files.
    expect(isProbablyText('main.rs', '')).toBe(true)
    expect(isProbablyText('Cargo.toml', '')).toBe(true)
    expect(isProbablyText('server.ts', '')).toBe(true)
  })

  it('rejects images and archives', () => {
    expect(isProbablyText('logo.png', 'image/png')).toBe(false)
    expect(isProbablyText('clip.mp4', 'video/mp4')).toBe(false)
    expect(isProbablyText('bundle.zip', '')).toBe(false)
  })

  it('treats SVG as text, because it is', () => {
    expect(isProbablyText('icon.svg', 'image/svg+xml')).toBe(true)
  })

  it('rejects an unknown extension with no MIME type', () => {
    expect(isProbablyText('data.bin', '')).toBe(false)
  })

  it('is case-insensitive about extensions', () => {
    expect(isProbablyText('README.MD', '')).toBe(true)
  })
})

describe('readAttachments', () => {
  it('reads a text file', async () => {
    const [attachment] = await readAttachments([file('notes.md', '# hello')])
    expect(attachment!.name).toBe('notes.md')
    expect(attachment!.text).toBe('# hello')
    expect(attachment!.truncated).toBe(false)
  })

  it('does not attempt to decode a binary file', async () => {
    const [attachment] = await readAttachments([file('logo.png', 'x', 'image/png')])
    expect(attachment!.text).toBeNull()
  })

  it('still reports a binary file rather than dropping it', async () => {
    // "I dropped in a PNG and nothing happened" is the worse outcome.
    const [attachment] = await readAttachments([file('logo.png', 'x', 'image/png')])
    expect(attachment!.name).toBe('logo.png')
  })

  it('truncates a file that would swamp the prompt', async () => {
    const huge = file('big.txt', 'a'.repeat(MAX_TEXT_BYTES + 5000), 'text/plain')
    const [attachment] = await readAttachments([huge])
    expect(attachment!.truncated).toBe(true)
    expect(attachment!.text!.length).toBe(MAX_TEXT_BYTES)
  })

  it('does not flag a file that fits', async () => {
    const [attachment] = await readAttachments([file('small.txt', 'ok', 'text/plain')])
    expect(attachment!.truncated).toBe(false)
  })

  it('caps how many files one drop can contribute', async () => {
    const many = Array.from({ length: 25 }, (_, i) =>
      file(`f${i}.txt`, 'x', 'text/plain'),
    )
    expect(await readAttachments(many)).toHaveLength(MAX_FILES)
  })

  it('reads several files in one drop', async () => {
    const result = await readAttachments([
      file('a.py', 'print(1)', 'text/x-python'),
      file('b.py', 'print(2)', 'text/x-python'),
    ])
    expect(result.map((a) => a.text)).toEqual(['print(1)', 'print(2)'])
  })

  it('returns nothing for an empty drop', async () => {
    expect(await readAttachments([])).toEqual([])
  })
})

describe('toWire', () => {
  it('carries what the backend needs', async () => {
    const attachments = await readAttachments([file('a.txt', 'body', 'text/plain')])
    const [wire] = toWire(attachments)
    expect(wire).toMatchObject({
      name: 'a.txt',
      mime: 'text/plain',
      text: 'body',
      truncated: false,
    })
  })

  it('omits the error key when there was no error', async () => {
    const attachments = await readAttachments([file('a.txt', 'body', 'text/plain')])
    expect(toWire(attachments)[0]).not.toHaveProperty('error')
  })

  it('forwards a read failure so the agent can say why', () => {
    const broken: Attachment = {
      name: 'locked.txt',
      size: 10,
      mime: 'text/plain',
      text: null,
      truncated: false,
      error: 'permission denied',
    }
    expect(toWire([broken])[0]).toHaveProperty('error', 'permission denied')
  })
})

describe('formatBytes', () => {
  it('uses bytes below a kilobyte', () => {
    expect(formatBytes(512)).toBe('512 B')
  })

  it('uses kilobytes', () => {
    expect(formatBytes(2048)).toBe('2.0 KB')
  })

  it('uses megabytes', () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})

describe('summarise', () => {
  it('is empty when nothing is attached', () => {
    expect(summarise([])).toBe('')
  })

  it('is singular for one file', async () => {
    const attachments = await readAttachments([file('a.txt', 'x', 'text/plain')])
    expect(summarise(attachments)).toBe('1 file · a.txt')
  })

  it('lists every name', async () => {
    const attachments = await readAttachments([
      file('a.txt', 'x', 'text/plain'),
      file('b.txt', 'y', 'text/plain'),
    ])
    expect(summarise(attachments)).toBe('2 files · a.txt, b.txt')
  })
})
