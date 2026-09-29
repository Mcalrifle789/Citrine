import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Prompt } from './Prompt'

/**
 * The "/" command menu.
 *
 * Three features want the arrow keys — history, the command catalog, and
 * argument completions — so most of what is worth pinning down here is which
 * one has them at any given moment.
 */

const CATALOG = [
  { name: 'provider', description: 'Add or switch model providers' },
  { name: 'model', description: 'Browse models from the selected provider' },
  { name: 'theme', description: 'Switch visual themes' },
  { name: 'status', description: 'Show current system status' },
  { name: 'help', description: 'Show help information' },
]

function CatalogPrompt({ onSubmit = vi.fn() }: { onSubmit?: (v: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <Prompt
      value={value}
      onValueChange={setValue}
      onSubmit={onSubmit}
      commands={CATALOG}
    />
  )
}

describe('the command menu opens and filters', () => {
  it('stays closed until a slash is typed', () => {
    render(<CatalogPrompt />)
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('opens the whole catalog on "/"', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/')
    expect(screen.getAllByRole('option')).toHaveLength(CATALOG.length)
  })

  it('shows each command with its description', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/')
    expect(screen.getByText('Switch visual themes')).toBeTruthy()
  })

  it('filters as the command name is typed', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/the')
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(options[0]!.textContent).toContain('/theme')
  })

  it('matches anywhere in the name, not only the start', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/vide')
    expect(screen.getAllByRole('option')[0]!.textContent).toContain('/provider')
  })

  it('closes once a space starts the arguments', async () => {
    // The space is the boundary between "which command" and "what arguments",
    // so the catalog gets out of the way and stops competing for the arrows.
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/theme ')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('offers nothing when the filter matches no command', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/zzzz')
    expect(screen.queryByRole('listbox')).toBeNull()
  })
})

describe('the command menu is navigable by keyboard', () => {
  it('highlights the first entry by default', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/')
    expect(screen.getAllByRole('option')[0]!.getAttribute('aria-selected')).toBe('true')
  })

  it('walks the list with ArrowDown', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/{ArrowDown}')
    expect(screen.getAllByRole('option')[1]!.getAttribute('aria-selected')).toBe('true')
  })

  it('walks back with ArrowUp', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(
      screen.getByRole('textbox'),
      '/{ArrowDown}{ArrowDown}{ArrowUp}',
    )
    expect(screen.getAllByRole('option')[1]!.getAttribute('aria-selected')).toBe('true')
  })

  it('wraps from the end back to the start', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(
      screen.getByRole('textbox'),
      `/${'{ArrowDown}'.repeat(CATALOG.length)}`,
    )
    expect(screen.getAllByRole('option')[0]!.getAttribute('aria-selected')).toBe('true')
  })

  it('wraps from the start back to the end', async () => {
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/{ArrowUp}')
    const options = screen.getAllByRole('option')
    expect(options[options.length - 1]!.getAttribute('aria-selected')).toBe('true')
  })

  it('resets the highlight when the filter changes', async () => {
    // The old index could point past the end of the new list, or at an entry
    // the user has just typed away from.
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/{ArrowDown}{ArrowDown}m')
    expect(screen.getAllByRole('option')[0]!.getAttribute('aria-selected')).toBe('true')
  })
})

describe('the command menu selects and dismisses', () => {
  it('fills the prompt with the highlighted command on Enter', async () => {
    const onSubmit = vi.fn()
    render(<CatalogPrompt onSubmit={onSubmit} />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, '/{ArrowDown}{Enter}')
    expect(input.value).toBe('/model ')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('also selects with Tab', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, '/the{Tab}')
    expect(input.value).toBe('/theme ')
  })

  it('leaves a trailing space so arguments can follow', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, '/the{Enter}')
    expect(input.value).toBe('/theme ')
  })

  it('selects with the mouse', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, '/')
    await userEvent.click(screen.getByRole('option', { name: /status/ }))
    expect(input.value).toBe('/status ')
  })

  it('moves the highlight to whatever the pointer is over', async () => {
    // One highlight for both input methods; a second would misrepresent which
    // entry Enter is about to pick.
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/')
    const option = screen.getByRole('option', { name: /status/ })
    await userEvent.hover(option)
    expect(option.getAttribute('aria-selected')).toBe('true')
  })

  it('closes on Escape without clearing the draft', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, '/the{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(input.value).toBe('/the')
  })

  it('submits on Enter once the menu is dismissed', async () => {
    const onSubmit = vi.fn()
    render(<CatalogPrompt onSubmit={onSubmit} />)
    await userEvent.type(screen.getByRole('textbox'), '/the{Escape}{Enter}')
    expect(onSubmit).toHaveBeenCalledWith('/the')
  })

  it('reopens when the draft changes after an Escape', async () => {
    // Escape dismisses the menu for the current draft, not for the session.
    render(<CatalogPrompt />)
    await userEvent.type(screen.getByRole('textbox'), '/the{Escape}m')
    expect(screen.queryByRole('listbox')).not.toBeNull()
  })

  it('submits an unmatched command rather than swallowing Enter', async () => {
    const onSubmit = vi.fn()
    render(<CatalogPrompt onSubmit={onSubmit} />)
    await userEvent.type(screen.getByRole('textbox'), '/zzzz{Enter}')
    expect(onSubmit).toHaveBeenCalledWith('/zzzz')
  })
})

describe('the command menu and history share the arrow keys', () => {
  it('leaves history to the arrows while the menu is closed', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'first{Enter}')
    await userEvent.type(input, '{ArrowUp}')
    expect(input.value).toBe('first')
  })

  it('does not recall history while the menu is open', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox') as HTMLTextAreaElement
    await userEvent.type(input, 'earlier{Enter}')
    await userEvent.type(input, '/{ArrowUp}')
    expect(input.value).toBe('/')
  })
})

describe('the command menu is announced to assistive technology', () => {
  it('points the input at the highlighted option', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, '/{ArrowDown}')
    const activeId = input.getAttribute('aria-activedescendant')
    expect(activeId).toBeTruthy()
    expect(document.getElementById(activeId!)?.getAttribute('aria-selected')).toBe(
      'true',
    )
  })

  it('reports whether it is expanded', async () => {
    render(<CatalogPrompt />)
    const input = screen.getByRole('textbox')
    expect(input.getAttribute('aria-expanded')).toBe('false')
    await userEvent.type(input, '/')
    expect(input.getAttribute('aria-expanded')).toBe('true')
  })
})
