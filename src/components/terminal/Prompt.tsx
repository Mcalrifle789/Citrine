import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

interface PromptProps {
  onSubmit: (value: string) => void
  disabled?: boolean
  value?: string
  onValueChange?: (value: string) => void
  focusToken?: number
  meta?: string
  suggestions?: Array<{ label: string; value: string }>
}

/**
 * The always-focused input line. Owns its own history: index -1 means "the
 * live draft", and walking forward past the newest entry returns to it.
 */
export function Prompt({
  onSubmit,
  disabled = false,
  value: controlledValue,
  onValueChange,
  focusToken,
  meta,
  suggestions = [],
}: PromptProps) {
  const [internalValue, setInternalValue] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [index, setIndex] = useState(-1)
  const ref = useRef<HTMLTextAreaElement>(null)
  const value = controlledValue ?? internalValue

  useEffect(() => {
    if (focusToken === undefined) return
    ref.current?.focus()
    const length = ref.current?.value.length ?? 0
    ref.current?.setSelectionRange(length, length)
  }, [focusToken])

  function setValue(nextValue: string): void {
    onValueChange?.(nextValue)
    if (controlledValue === undefined) {
      setInternalValue(nextValue)
    }
  }

  function recall(nextIndex: number): void {
    if (nextIndex < 0) {
      setIndex(-1)
      setValue('')
      return
    }
    const clamped = Math.min(nextIndex, history.length - 1)
    setIndex(clamped)
    setValue(history[clamped] ?? '')
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (disabled) return
      const trimmed = value.trim()
      if (!trimmed) return
      onSubmit(trimmed)
      // Newest first, so ArrowUp reaches the most recent entry immediately.
      setHistory((prev) => [trimmed, ...prev])
      setIndex(-1)
      setValue('')
      return
    }

    if (event.key === 'ArrowUp' && !event.shiftKey) {
      if (history.length === 0) return
      event.preventDefault()
      recall(index + 1)
      return
    }

    if (event.key === 'ArrowDown' && !event.shiftKey) {
      if (index < 0) return
      event.preventDefault()
      recall(index - 1)
    }
  }

  return (
    <div className="ct-promptwrap">
      {suggestions.length > 0 && (
        <div className="ct-command-popover" role="listbox" aria-label="Command suggestions">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.value}
              type="button"
              className="ct-command-popover__item"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                setValue(suggestion.value)
                ref.current?.focus()
              }}
            >
              {suggestion.label}
            </button>
          ))}
        </div>
      )}
      <div className="ct-prompt">
        {meta && <span className="ct-prompt__meta">{meta}</span>}
        <span className="ct-prompt__sigil" aria-hidden="true">
          &gt;
        </span>
        <textarea
          ref={ref}
          className="ct-prompt__input"
          rows={1}
          spellCheck={false}
          autoComplete="off"
          aria-label="Citrine prompt"
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
      </div>
    </div>
  )
}
