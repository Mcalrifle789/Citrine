import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
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

  it('supports a controlled draft value', async () => {
    const onSubmit = vi.fn()
    function ControlledPrompt() {
      const [value, setValue] = useState('/chat ')
      return <Prompt value={value} onValueChange={setValue} onSubmit={onSubmit} />
    }

    render(<ControlledPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(input.value).toBe('/chat ')
    await userEvent.type(input, 'hello{Enter}')
    expect(onSubmit).toHaveBeenCalledWith('/chat hello')
    expect(input.value).toBe('')
  })

  it('shows meta and lets suggestions fill the prompt', async () => {
    const user = userEvent.setup()
    function SuggestedPrompt() {
      const [value, setValue] = useState('/model ')
      return (
        <Prompt
          value={value}
          onValueChange={setValue}
          onSubmit={vi.fn()}
          meta="OpenAI · gpt-4o-mini · 128k/128k"
          suggestions={[{ label: 'gpt-4o', value: '/model gpt-4o' }]}
        />
      )
    }

    render(<SuggestedPrompt />)
    expect(screen.getByText('OpenAI · gpt-4o-mini · 128k/128k').textContent).toBe(
      'OpenAI · gpt-4o-mini · 128k/128k',
    )
    await user.click(screen.getByRole('button', { name: 'gpt-4o' }))
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('/model gpt-4o')
  })
})
