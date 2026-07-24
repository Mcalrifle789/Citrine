/**
 * Theme switching is a single attribute swap on the document element.
 * Every token lives in CSS, so no component re-renders when the theme
 * changes — the cascade does the work.
 */

export const THEMES = ['citrine'] as const
export type ThemeName = (typeof THEMES)[number]

export const DEFAULT_THEME: ThemeName = 'citrine'
const STORAGE_KEY = 'citrine.theme'

export function listThemes(): ThemeName[] {
  return [...THEMES]
}

function isThemeName(value: string | null): value is ThemeName {
  return value !== null && (THEMES as readonly string[]).includes(value)
}

export function applyTheme(name: ThemeName): void {
  document.documentElement.dataset.theme = name
  localStorage.setItem(STORAGE_KEY, name)
}

export function getActiveTheme(): ThemeName {
  const stored = localStorage.getItem(STORAGE_KEY)
  return isThemeName(stored) ? stored : DEFAULT_THEME
}
