import { beforeEach, describe, expect, it } from 'vitest'
import { applyTheme, getActiveTheme, listThemes, DEFAULT_THEME } from './theme'

describe('theme engine', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('lists the themes that ship with the app', () => {
    expect(listThemes()).toContain('citrine')
  })

  it('applies a theme by setting data-theme on the document element', () => {
    applyTheme('citrine')
    expect(document.documentElement.dataset.theme).toBe('citrine')
  })

  it('persists the applied theme', () => {
    applyTheme('citrine')
    expect(localStorage.getItem('citrine.theme')).toBe('citrine')
  })

  it('reports the default theme before anything is applied', () => {
    expect(getActiveTheme()).toBe(DEFAULT_THEME)
  })

  it('reports the persisted theme after application', () => {
    applyTheme('citrine')
    expect(getActiveTheme()).toBe('citrine')
  })

  it('falls back to the default when persisted value is unknown', () => {
    localStorage.setItem('citrine.theme', 'not-a-real-theme')
    expect(getActiveTheme()).toBe(DEFAULT_THEME)
  })
})
