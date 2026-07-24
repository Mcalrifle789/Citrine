import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Prompt } from './Prompt'

describe('Prompt', () => {
  it('submits the typed value on Enter', async () => {
    const onSubmit = vi.fn()
    render(<Prompt onSubmit={onSubmit} />)
    await userEvent.type(screen.getByRole('textbox'), 'hello{Enter}')
    expect(onSubmit).toHaveBeenCalledWith('hello')
  })

  it('clears the input after submitting', async () => {
    render(<Prompt onSubmit={vi.fn()} />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'hello{Enter}')
    expect(input.value).toBe('')
  })

  it('does not submit an empty or whitespace-only value', async () => {
    const onSubmit = vi.fn()
    render(<Prompt onSubmit={onSubmit} />)
    await userEvent.type(screen.getByRole('textbox'), '   {Enter}')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('inserts a newline on Shift+Enter instead of submitting', async () => {
    const onSubmit = vi.fn()
    render(<Prompt onSubmit={onSubmit} />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'one{Shift>}{Enter}{/Shift}two')
    expect(onSubmit).not.toHaveBeenCalled()
    expect(input.value).toBe('one\ntwo')
  })

  it('recalls the previous entry with ArrowUp', async () => {
    render(<Prompt onSubmit={vi.fn()} />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'first{Enter}')
    await userEvent.type(input, '{ArrowUp}')
    expect(input.value).toBe('first')
  })

  it('walks back through multiple entries', async () => {
    render(<Prompt onSubmit={vi.fn()} />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'first{Enter}')
    await userEvent.type(input, 'second{Enter}')
    await userEvent.type(input, '{ArrowUp}{ArrowUp}')
    expect(input.value).toBe('first')
  })

  it('returns to an empty input when walking forward past the newest entry', async () => {
    render(<Prompt onSubmit={vi.fn()} />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'only{Enter}')
    await userEvent.type(input, '{ArrowUp}{ArrowDown}')
    expect(input.value).toBe('')
  })

  it('does not submit while disabled', async () => {
    const onSubmit = vi.fn()
    render(<Prompt onSubmit={onSubmit} disabled />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'hello{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
