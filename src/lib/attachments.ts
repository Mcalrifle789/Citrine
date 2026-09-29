/**
 * Reading files the user drops onto Citrine.
 *
 * Files are read in the renderer through the File API rather than by path.
 * Electron stopped exposing `File.path` in v32, so the path route now needs
 * `webUtils.getPathForFile` plumbed through the preload bridge — and widening
 * that bridge to hand the backend arbitrary filesystem paths is a real
 * escalation for a feature that only needs the bytes. Reading here keeps the
 * bridge as narrow as it is, and keeps this module testable in jsdom.
 */

/** Per-file text cap. Enough for a source file; short of wedging a prompt. */
export const MAX_TEXT_BYTES = 64 * 1024

/**
 * Per-file binary cap. Generous on purpose: this is what lets the agent read
 * an image, a PDF or an Office document instead of being told it cannot. The
 * backend refuses anything larger with a reason rather than truncating it.
 */
export const MAX_BINARY_BYTES = 8 * 1024 * 1024

/** Files past this in one drop are ignored rather than silently truncated. */
export const MAX_FILES = 10

export interface Attachment {
  name: string
  size: number
  /** The browser's MIME guess. Empty string when it has none. */
  mime: string
  /** Decoded text, or null when the file is binary or was unreadable. */
  text: string | null
  /** Base64 of the raw bytes for binary files, or null for text files. */
  dataBase64: string | null
  /** True when `text` holds only the first MAX_TEXT_BYTES of the file. */
  truncated: boolean
  /** Set when the file could not be read; surfaced to the user. */
  error?: string
}

const TEXT_MIME_PREFIXES = ['text/']
const TEXT_MIME_EXACT = new Set([
  'application/json',
  'application/xml',
  'application/javascript',
  'application/typescript',
  'application/x-sh',
  'application/x-yaml',
  'application/yaml',
  'application/toml',
  'image/svg+xml',
])

// Extensions carry the decision when the MIME type does not. Browsers report
// "" for plenty of ordinary source files — .ts, .rs and .toml among them.
const TEXT_EXTENSIONS = new Set([
  'txt', 'md', 'markdown', 'rst', 'log', 'csv', 'tsv',
  'json', 'jsonc', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf', 'env',
  'xml', 'html', 'htm', 'css', 'scss', 'less', 'svg',
  'js', 'jsx', 'mjs', 'cjs', 'ts', 'tsx', 'vue', 'svelte',
  'py', 'rb', 'go', 'rs', 'java', 'kt', 'swift', 'php', 'lua', 'pl',
  'c', 'h', 'cpp', 'cc', 'cxx', 'hpp', 'hh', 'cs',
  'sh', 'bash', 'zsh', 'fish', 'ps1', 'bat', 'cmd', 'vbs',
  'sql', 'graphql', 'gql', 'proto', 'diff', 'patch',
  'dockerfile', 'gitignore', 'editorconfig',
])

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  if (dot <= 0 || dot === name.length - 1) return ''
  return name.slice(dot + 1).toLowerCase()
}

/** Whether a file is worth trying to decode as text. */
export function isProbablyText(name: string, mime: string): boolean {
  const type = mime.toLowerCase()
  if (TEXT_MIME_PREFIXES.some((prefix) => type.startsWith(prefix))) return true
  if (TEXT_MIME_EXACT.has(type)) return true
  if (type && !type.startsWith('application/')) return false
  return TEXT_EXTENSIONS.has(extensionOf(name))
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Base64-encode an ArrayBuffer.
 *
 * Chunked rather than one `String.fromCharCode(...new Uint8Array(buffer))`
 * call: spreading a multi-megabyte array blows the argument limit and throws
 * "Maximum call stack size exceeded", which is exactly the size of file this
 * function now has to handle.
 */
export function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  const chunkSize = 0x8000
  let binary = ''
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize))
  }
  return btoa(binary)
}

async function readOne(file: File): Promise<Attachment> {
  const base: Attachment = {
    name: file.name,
    size: file.size,
    mime: file.type ?? '',
    text: null,
    dataBase64: null,
    truncated: false,
  }

  try {
    if (isProbablyText(file.name, base.mime)) {
      const slice = file.size > MAX_TEXT_BYTES ? file.slice(0, MAX_TEXT_BYTES) : file
      const text = await slice.text()
      return { ...base, text, truncated: file.size > MAX_TEXT_BYTES }
    }

    // Binary: hand over the bytes. Too large a file is reported rather than
    // silently dropped, so the user knows why the agent cannot see it.
    if (file.size > MAX_BINARY_BYTES) {
      return {
        ...base,
        error: `binary file is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_BINARY_BYTES)}`,
      }
    }
    const dataBase64 = toBase64(await file.arrayBuffer())
    return { ...base, dataBase64 }
  } catch (error) {
    return {
      ...base,
      error: error instanceof Error ? error.message : 'could not be read',
    }
  }
}

/**
 * Read dropped or pasted files into attachments.
 *
 * Every file resolves to an attachment, including ones that could not be read
 * — the agent is told the file was offered and why it is not readable, which
 * is more use than the file vanishing without explanation.
 */
export async function readAttachments(files: ArrayLike<File>): Promise<Attachment[]> {
  const list = Array.from(files).slice(0, MAX_FILES)
  return Promise.all(list.map(readOne))
}

/** The wire shape sent to the backend with `chat.send`. */
export function toWire(attachments: Attachment[]): Array<Record<string, unknown>> {
  return attachments.map((attachment) => ({
    name: attachment.name,
    size: attachment.size,
    mime: attachment.mime,
    text: attachment.text,
    dataBase64: attachment.dataBase64,
    truncated: attachment.truncated,
    ...(attachment.error ? { error: attachment.error } : {}),
  }))
}

/** A one-line summary for the transcript, e.g. "2 files · main.py, notes.md". */
export function summarise(attachments: Attachment[]): string {
  if (attachments.length === 0) return ''
  const names = attachments.map((attachment) => attachment.name).join(', ')
  const count = attachments.length === 1 ? '1 file' : `${attachments.length} files`
  return `${count} · ${names}`
}
