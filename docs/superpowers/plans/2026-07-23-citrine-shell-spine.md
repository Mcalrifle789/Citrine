# Citrine Shell & Spine — Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Citrine desktop shell — an Electron window matching the reference mockup, backed by a supervised Python sidecar over an authenticated local WebSocket, with a live echo round-trip proving the full spine.

**Architecture:** Three processes. Electron main spawns and supervises a Python FastAPI/uvicorn sidecar bound to `127.0.0.1` on an OS-assigned ephemeral port, discovering that port from a JSON handshake line on the child's stdout. A hardened preload exposes only `{port, token}` to the renderer, which opens its own authenticated WebSocket. All UI is styled DOM (React), never a terminal emulator, with every color read from CSS custom properties so themes are a single token-block swap.

**Tech Stack:** Electron + electron-vite + React 19 + TypeScript + Zustand + Vitest + Playwright (renderer); Python 3.11 + FastAPI + uvicorn + pydantic + pytest, managed by `uv` (backend).

**Spec:** `docs/superpowers/specs/2026-07-23-citrine-shell-providers-design.md`

**Plan 2** (written after this plan lands) covers: secrets/keyring, the `Provider` interface, the LiteLLM adapter, the 24-entry registry, onboarding, streaming chat UI, SQLite sessions, and packaging.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec.

- **Primary accent is cyan `#5CE1FF`. Gold `#E8A33D` is secondary only** — git branch segment, tools indicator, warnings. Never swap these.
- **No component hardcodes a color.** Every color reads from a CSS custom property defined in `src/styles/tokens.css`.
- **No rounded corners. No drop shadows. No material elevation.** Depth comes from translucency and glow only.
- **Glow (`text-shadow`) applies only to headings, the wordmark, the caret, and active states.** Never to body text or scrollback.
- **Bind `127.0.0.1` only. Never `0.0.0.0`.**
- **Electron hardening is mandatory:** `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`.
- **Key material is redacted at the logger**, never at call sites.
- **Fonts are bundled**, never fetched from a remote URL at runtime.
- **CI never touches a live API.**
- Python 3.11 (`uv venv --python 3.11`). Node 24.
- Text is `--c-text` (`#C8D6E5`), never pure `#FFF`.

---

### Task 1: Repository scaffold, toolchain, and cross-platform paths

Establishes both toolchains and delivers one real, tested module: OS path resolution. This is not a throwaway smoke test — Windows redirects `Documents` to OneDrive on this machine, so naive `Path.home() / "Documents"` produces a wrong agents directory.

**Files:**
- Create: `package.json`, `tsconfig.json`, `tsconfig.node.json`, `electron.vite.config.ts`, `index.html`
- Create: `electron/main.ts`, `electron/preload.ts`
- Create: `src/main.tsx`, `src/App.tsx`
- Create: `backend/pyproject.toml`, `backend/citrine/__init__.py`, `backend/citrine/paths.py`
- Test: `backend/tests/test_paths.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `citrine.paths.citrine_home() -> Path`, `citrine.paths.config_path() -> Path`, `citrine.paths.logs_dir() -> Path`, `citrine.paths.sessions_db_path() -> Path`, `citrine.paths.agents_dir() -> Path`, `citrine.paths.documents_dir() -> Path`. All return absolute `pathlib.Path`; none create directories except `ensure_dirs() -> None`.

- [ ] **Step 1: Initialise the Node project and install dependencies**

```bash
cd ~/citrine
npm init -y
npm pkg set name="citrine" version="0.1.0" description="Local-first personal AI terminal agent" license="MIT" type="module" main="out/main/main.js"
npm install react react-dom zustand
npm install -D electron electron-vite vite typescript @vitejs/plugin-react vitest @types/react @types/react-dom @types/node
```

- [ ] **Step 2: Create the TypeScript and build configuration**

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src", "electron", "*.config.ts"]
}
```

`electron.vite.config.ts`:

```ts
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig({
  main: {
    build: { lib: { entry: resolve(__dirname, 'electron/main.ts') } },
  },
  preload: {
    build: { lib: { entry: resolve(__dirname, 'electron/preload.ts') } },
  },
  renderer: {
    root: '.',
    build: { rollupOptions: { input: resolve(__dirname, 'index.html') } },
    plugins: [react()],
    resolve: { alias: { '@': resolve(__dirname, 'src') } },
  },
})
```

- [ ] **Step 3: Create the minimal Electron entry points and React root**

`electron/main.ts`:

```ts
import { app, BrowserWindow } from 'electron'
import { resolve } from 'node:path'

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1680,
    height: 960,
    backgroundColor: '#05030F',
    show: false,
    webPreferences: {
      preload: resolve(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  win.once('ready-to-show', () => win.show())

  if (process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void win.loadFile(resolve(__dirname, '../renderer/index.html'))
  }
}

void app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
```

`electron/preload.ts`:

```ts
import { contextBridge } from 'electron'

// Task 7 replaces this stub with the real backend handshake.
contextBridge.exposeInMainWorld('citrine', {
  getBackendInfo: async (): Promise<{ port: number; token: string } | null> => null,
})
```

`index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src ws://127.0.0.1:*" />
    <title>Citrine</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

`src/App.tsx`:

```tsx
export function App() {
  return <div>Citrine</div>
}
```

- [ ] **Step 4: Add npm scripts**

```bash
npm pkg set scripts.dev="electron-vite dev"
npm pkg set scripts.build="electron-vite build"
npm pkg set scripts.typecheck="tsc --noEmit"
npm pkg set scripts.test="vitest run"
```

- [ ] **Step 5: Verify the window opens**

Run: `npm run dev`
Expected: an Electron window opens, 1680×960, near-black background, showing the text `Citrine`. Close it.

- [ ] **Step 6: Create the Python environment and project**

```bash
cd ~/citrine/backend
uv venv --python 3.11
uv pip install pytest
```

`backend/pyproject.toml`:

```toml
[project]
name = "citrine-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create empty `backend/citrine/__init__.py`.

- [ ] **Step 7: Write the failing test for paths**

`backend/tests/test_paths.py`:

```python
import os
from pathlib import Path

import pytest

from citrine import paths


def test_citrine_home_defaults_under_user_home(monkeypatch):
    monkeypatch.delenv("CITRINE_HOME", raising=False)
    assert paths.citrine_home() == Path.home() / ".citrine"


def test_citrine_home_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path))
    assert paths.citrine_home() == tmp_path


def test_derived_paths_live_under_citrine_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path))
    assert paths.config_path() == tmp_path / "config.json"
    assert paths.logs_dir() == tmp_path / "logs"
    assert paths.sessions_db_path() == tmp_path / "sessions.sqlite3"


def test_all_paths_are_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path))
    for p in (paths.citrine_home(), paths.config_path(), paths.logs_dir(),
              paths.documents_dir(), paths.agents_dir()):
        assert p.is_absolute(), f"{p} is not absolute"


def test_agents_dir_lives_under_documents(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_DOCUMENTS", str(tmp_path))
    assert paths.agents_dir() == tmp_path / "Citrine" / "Agents"


def test_documents_dir_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_DOCUMENTS", str(tmp_path))
    assert paths.documents_dir() == tmp_path


@pytest.mark.skipif(os.name != "nt", reason="Windows shell-folder redirection")
def test_documents_dir_follows_windows_redirection(monkeypatch):
    """Documents is frequently redirected to OneDrive; the naive
    home/Documents guess is wrong on such machines."""
    monkeypatch.delenv("CITRINE_DOCUMENTS", raising=False)
    resolved = paths.documents_dir()
    assert resolved.name.lower() == "documents"


def test_ensure_dirs_creates_missing_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CITRINE_DOCUMENTS", str(tmp_path / "docs"))
    paths.ensure_dirs()
    assert (tmp_path / "home" / "logs").is_dir()
    assert (tmp_path / "docs" / "Citrine" / "Agents").is_dir()
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `cd ~/citrine/backend && uv run pytest tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'citrine.paths'`

- [ ] **Step 9: Implement the paths module**

`backend/citrine/paths.py`:

```python
"""Cross-platform filesystem locations for Citrine.

Windows redirects the Documents folder (commonly to OneDrive), so the
location is read from the shell-folder registry rather than assumed to be
``~/Documents``. Every path is overridable by environment variable to keep
tests hermetic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = ".citrine"
PRODUCT_NAME = "Citrine"


def citrine_home() -> Path:
    """Application-private directory: config, logs, session database."""
    override = os.environ.get("CITRINE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / APP_DIR_NAME


def config_path() -> Path:
    return citrine_home() / "config.json"


def logs_dir() -> Path:
    return citrine_home() / "logs"


def sessions_db_path() -> Path:
    return citrine_home() / "sessions.sqlite3"


def documents_dir() -> Path:
    """The user's Documents folder, honouring Windows shell redirection."""
    override = os.environ.get("CITRINE_DOCUMENTS")
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "win32":
        redirected = _windows_documents_dir()
        if redirected is not None:
            return redirected

    return Path.home() / "Documents"


def _windows_documents_dir() -> Path | None:
    """Read the real Documents location from the shell-folder registry.

    Returns None if the key is unreadable, letting the caller fall back.
    """
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")
    except OSError:
        return None

    expanded = os.path.expandvars(value)
    return Path(expanded).resolve() if expanded else None


def agents_dir() -> Path:
    """User-visible agent files. Slice 5 populates this."""
    return documents_dir() / PRODUCT_NAME / "Agents"


def ensure_dirs() -> None:
    """Create every directory Citrine writes to. Safe to call repeatedly."""
    for directory in (citrine_home(), logs_dir(), agents_dir()):
        directory.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `cd ~/citrine/backend && uv run pytest tests/test_paths.py -v`
Expected: PASS — 8 passed.

- [ ] **Step 11: Verify the Windows redirection actually resolves correctly**

Run: `cd ~/citrine/backend && uv run python -c "from citrine import paths; print(paths.agents_dir())"`
Expected: a path ending in `Citrine\Agents`. On this machine it should sit under the OneDrive-redirected Documents folder, **not** `C:\Users\hextu\Documents`. If it prints the non-redirected path, `_windows_documents_dir()` is failing silently — debug before continuing, because slice 5 depends on it.

- [ ] **Step 12: Commit**

```bash
cd ~/citrine
git add -A
git commit -m "feat: scaffold Electron + Python toolchains and path resolution

Documents is read from the Windows shell-folder registry rather than
assumed to be ~/Documents, since OneDrive redirection is common and would
otherwise place agent files in a directory the user never sees."
```

---

### Task 2: Design tokens and theme engine

The theme *engine* ships in this slice even though the `/theme` selector is slice 3, because retrofitting token-driven theming after components are written means touching every file.

**Files:**
- Create: `src/styles/tokens.css`, `src/styles/global.css`, `src/themes/citrine.css`
- Create: `src/lib/theme.ts`
- Create: `vitest.config.ts`
- Test: `src/lib/theme.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `applyTheme(name: ThemeName): void`, `listThemes(): ThemeName[]`, `getActiveTheme(): ThemeName`, `type ThemeName = 'citrine'`. `applyTheme` sets `data-theme` on `document.documentElement` and persists to `localStorage` under key `citrine.theme`.

- [ ] **Step 1: Install the test toolchain**

```bash
cd ~/citrine
npm install -D jsdom @testing-library/react @testing-library/dom @testing-library/user-event
```

`vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
```

- [ ] **Step 2: Write the failing test**

`src/lib/theme.test.ts`:

```ts
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- src/lib/theme.test.ts`
Expected: FAIL — cannot resolve `./theme`.

- [ ] **Step 4: Implement the theme module**

`src/lib/theme.ts`:

```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- src/lib/theme.test.ts`
Expected: PASS — 6 passed.

- [ ] **Step 6: Write the token stylesheet**

`src/styles/tokens.css` — values copied verbatim from spec §4.1:

```css
/*
 * The single source of truth for every colour in Citrine.
 * A theme is this block, redefined. Nothing else may hardcode a colour.
 *
 * The primary accent is CYAN. Gold is secondary, reserved for the git
 * branch segment, the tools indicator, and warnings.
 */
:root,
:root[data-theme='citrine'] {
  --c-bg: #05030f;
  --c-panel: rgba(10, 8, 24, 0.72);
  --c-border: #24405e;
  --c-accent: #5ce1ff;
  --c-accent-glow: #7df9ff;
  --c-gold: #e8a33d;
  --c-text: #c8d6e5;
  --c-text-dim: #6b7c93;
  --c-ok: #5fd98a;
  --c-err: #ff5c8a;

  /* Glow is two layered shadows: a tight core and a diffuse halo.
     Applied only to headings, the wordmark, the caret, and active states. */
  --glow-accent: 0 0 8px rgb(124 249 255 / 45%), 0 0 20px rgb(124 249 255 / 22%);
  --glow-gold: 0 0 8px rgb(232 163 61 / 40%), 0 0 20px rgb(232 163 61 / 18%);

  --font-mono: 'JetBrains Mono', ui-monospace, 'Cascadia Mono', Consolas, monospace;
  --fs-base: 13px;
  --lh-base: 1.55;

  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 24px;

  --border-w: 1px;
  --rail-w: 320px;
}
```

`src/themes/citrine.css`:

```css
/* The default theme is the token block itself. Additional themes (slice 3)
   redefine the same custom properties under their own [data-theme] selector.
   This file exists so theme files have a consistent home from day one. */
@import '../styles/tokens.css';
```

- [ ] **Step 7: Write the global stylesheet**

`src/styles/global.css`:

```css
@import '../themes/citrine.css';

*,
*::before,
*::after {
  box-sizing: border-box;
  /* No rounded corners anywhere in Citrine. */
  border-radius: 0;
}

html,
body,
#root {
  height: 100%;
  margin: 0;
}

body {
  background-color: var(--c-bg);
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: var(--fs-base);
  line-height: var(--lh-base);
  /* Terminal feel: no rubber-band scroll, no text inflation on zoom. */
  overflow: hidden;
  text-size-adjust: none;
}

::selection {
  background: var(--c-accent);
  color: var(--c-bg);
}

/* Scrollbars are part of the aesthetic, not an afterthought. */
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--c-border);
}
::-webkit-scrollbar-thumb:hover {
  background: var(--c-accent);
}
```

- [ ] **Step 8: Apply the theme at startup and verify visually**

Modify `src/main.tsx` — add the stylesheet import and theme application above `createRoot`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { applyTheme, getActiveTheme } from './lib/theme'
import './styles/global.css'

applyTheme(getActiveTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Run: `npm run dev`
Expected: the window renders `Citrine` in monospace, soft blue-white (`#C8D6E5`) on near-black. Inspect the DOM: `<html data-theme="citrine">`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: add design tokens and theme engine

Themes are a data-theme attribute swap over CSS custom properties, so
switching is instant and no component re-renders. The engine ships now
even though the /theme selector is slice 3, because retrofitting
token-driven theming later would touch every component."
```

---

### Task 3: Visual assets — fonts, wordmark, and procedural background

**Design decision made here:** the nebula backdrop is **procedural CSS plus a generated starfield tile**, not a photographic asset. Three reasons: it is themeable (the nebula recolours with the token set, which a JPEG cannot), it is a few KB rather than a few MB, and it sidesteps extracting a clean background from the logo art. The wordmark *is* extracted from the logo, using luminance as alpha — a technique that works precisely because the wordmark is a bright glow on a dark field, so the glow falloff becomes a natural alpha ramp.

**Files:**
- Create: `scripts/extract_wordmark.py`, `scripts/gen_starfield.py`
- Create: `src/assets/lattice.svg`
- Create: `src/styles/fonts.css`, `src/styles/background.css`
- Generated: `src/assets/wordmark.png`, `src/assets/starfield.png`
- Test: `backend/tests/test_asset_scripts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `src/assets/wordmark.png` (RGBA, transparent background), `src/assets/starfield.png` (512×512 seamlessly tileable RGBA), CSS classes `.citrine-backdrop` and font-family `JetBrains Mono`.

- [ ] **Step 1: Install the bundled font**

```bash
cd ~/citrine
npm install @fontsource/jetbrains-mono
```

This vendors woff2 files into `node_modules` and bundles them at build time — no runtime network fetch, satisfying the global constraint.

`src/styles/fonts.css`:

```css
/* Bundled locally via @fontsource — never fetched at runtime.
   A webfont that fails to load would collapse the aesthetic to Courier. */
@import '@fontsource/jetbrains-mono/400.css';
@import '@fontsource/jetbrains-mono/500.css';
@import '@fontsource/jetbrains-mono/700.css';
```

Add `@import './fonts.css';` as the first line of `src/styles/global.css`.

- [ ] **Step 2: Install Pillow for the asset scripts**

```bash
cd ~/citrine/backend
uv pip install pillow
```

Add `"pillow>=10"` to the `dev` extras list in `backend/pyproject.toml`.

- [ ] **Step 3: Write the failing test for the asset scripts**

`backend/tests/test_asset_scripts.py`:

```python
"""The asset scripts are build tooling, but they encode real decisions
(alpha derivation, tile seamlessness) that regress silently if untested."""

import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_wordmark import alpha_from_luminance  # noqa: E402
from gen_starfield import generate_starfield  # noqa: E402


def test_alpha_from_luminance_makes_dark_pixels_transparent():
    source = Image.new("RGB", (2, 1))
    source.putpixel((0, 0), (0, 0, 0))        # background
    source.putpixel((1, 0), (92, 225, 255))   # glowing wordmark
    result = alpha_from_luminance(source)
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((1, 0))[3] > 200


def test_alpha_from_luminance_preserves_colour():
    source = Image.new("RGB", (1, 1), (92, 225, 255))
    r, g, b, _ = alpha_from_luminance(source).getpixel((0, 0))
    assert (r, g, b) == (92, 225, 255)


def test_alpha_from_luminance_ramps_glow_falloff():
    """A mid-brightness glow pixel must be partially transparent, which is
    what makes the extracted wordmark composite cleanly over any backdrop."""
    source = Image.new("RGB", (1, 1), (46, 112, 128))
    alpha = alpha_from_luminance(source).getpixel((0, 0))[3]
    assert 40 < alpha < 215


def test_starfield_is_the_expected_size_and_mode():
    img = generate_starfield(size=512, seed=7)
    assert img.size == (512, 512)
    assert img.mode == "RGBA"


def test_starfield_is_deterministic_for_a_seed():
    assert generate_starfield(size=64, seed=3).tobytes() == \
           generate_starfield(size=64, seed=3).tobytes()


def test_starfield_differs_between_seeds():
    assert generate_starfield(size=64, seed=3).tobytes() != \
           generate_starfield(size=64, seed=4).tobytes()


def test_starfield_is_mostly_transparent():
    """Stars are sparse; a dense field reads as noise, not space."""
    img = generate_starfield(size=128, seed=11)
    opaque = sum(1 for px in img.getdata() if px[3] > 8)
    assert 0 < opaque < (128 * 128) * 0.05


def test_starfield_tiles_seamlessly():
    """Stars must not be clipped at the edges, or the tile seam shows."""
    img = generate_starfield(size=128, seed=5)
    px = img.load()
    for i in range(128):
        assert px[0, i][3] == 0 or px[127, i][3] == 0 or True
    left = [px[0, i][3] for i in range(128)]
    right = [px[127, i][3] for i in range(128)]
    assert left == right, "left and right edges must match for seamless tiling"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd ~/citrine/backend && uv run pytest tests/test_asset_scripts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extract_wordmark'`

- [ ] **Step 5: Implement the wordmark extraction script**

`scripts/extract_wordmark.py`:

```python
"""Extract the glowing Citrine wordmark from the logo art.

The source logo has a nebula baked into it. Compositing it over the app's
own procedural nebula would show a seam and put two starfields in conflict,
so the wordmark is lifted onto transparency instead.

The technique: the wordmark is a bright cyan glow on a near-black field, so
per-pixel luminance is already an excellent alpha mask. Using it directly
preserves the soft glow falloff, which a hard-threshold cutout would destroy.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# Rec. 709 luminance weights.
_R, _G, _B = 0.2126, 0.7152, 0.0722


def alpha_from_luminance(image: Image.Image, gamma: float = 0.85) -> Image.Image:
    """Return an RGBA copy whose alpha channel is derived from luminance.

    ``gamma`` below 1.0 lifts the mid-tones so the glow halo stays visible
    rather than fading out too aggressively.
    """
    rgb = image.convert("RGB")
    luminance = rgb.convert("L", matrix=(_R, _G, _B, 0, _R, _G, _B, 0, _R, _G, _B, 0))
    if gamma != 1.0:
        table = [min(255, round(255 * ((i / 255) ** gamma))) for i in range(256)]
        luminance = luminance.point(table)

    out = rgb.convert("RGBA")
    out.putalpha(luminance)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="path to 'Citrine logo.png'")
    parser.add_argument("dest", type=Path, help="output RGBA png")
    parser.add_argument("--crop", type=int, nargs=4, metavar=("L", "T", "R", "B"),
                        help="optional crop box around the wordmark")
    args = parser.parse_args()

    image = Image.open(args.source)
    if args.crop:
        image = image.crop(tuple(args.crop))

    result = alpha_from_luminance(image)
    result = result.crop(result.getbbox() or result.getbbox())
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.dest)
    print(f"wrote {args.dest} ({result.width}x{result.height})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Implement the starfield generator**

`scripts/gen_starfield.py`:

```python
"""Generate a seamlessly tileable starfield.

Procedural rather than photographic so the backdrop stays a few KB and can
be recoloured by the theme. Seeded for reproducible builds.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image

STAR_DENSITY = 0.0022  # stars per pixel — sparse enough to read as space


def generate_starfield(size: int = 512, seed: int = 1337) -> Image.Image:
    """Return an RGBA tile of white stars on full transparency.

    Stars are drawn as single pixels with a dim neighbour cross so they
    survive downscaling. Column 0 is copied to column ``size - 1`` (and the
    same for rows) so opposing edges match exactly and the tile is seamless.
    """
    rng = random.Random(seed)
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    px = img.load()

    count = int(size * size * STAR_DENSITY)
    for _ in range(count):
        x = rng.randrange(1, size - 1)
        y = rng.randrange(1, size - 1)
        brightness = rng.randint(90, 255)
        px[x, y] = (255, 255, 255, brightness)
        halo = brightness // 5
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            hx, hy = x + dx, y + dy
            if px[hx, hy][3] < halo:
                px[hx, hy] = (255, 255, 255, halo)

    # Make opposing edges identical so the tile repeats without a visible seam.
    for i in range(size):
        px[size - 1, i] = px[0, i]
        px[i, size - 1] = px[i, 0]

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    img = generate_starfield(size=args.size, seed=args.seed)
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.dest)
    print(f"wrote {args.dest} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd ~/citrine/backend && uv run pytest tests/test_asset_scripts.py -v`
Expected: PASS — 8 passed.

- [ ] **Step 8: Generate the assets**

```bash
cd ~/citrine
uv run --project backend python scripts/gen_starfield.py src/assets/starfield.png
uv run --project backend python scripts/extract_wordmark.py \
  "C:/Users/hextu/OneDrive/Documents/Terminal GUIs/Citrine/Citrine logo.png" \
  src/assets/wordmark.png --crop 60 330 1470 640
```

Open `src/assets/wordmark.png` in an image viewer with a checkerboard background.
Expected: the cyan "Citrine / AI Project" wordmark with its glow, on transparency, no nebula.

**If the extraction looks wrong** (nebula stars still visible as speckle), raise the gamma toward `1.4` — this darkens the faint background stars faster than the bright wordmark. If it still fails, the spec's defined fallback is the ASCII block wordmark; record that decision and move on rather than burning time.

- [ ] **Step 9: Create the lattice overlay**

`src/assets/lattice.svg` — the faint quatrefoil grid visible in the mockup:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">
  <defs>
    <pattern id="quatrefoil" width="120" height="120" patternUnits="userSpaceOnUse">
      <path d="M60 0 A30 30 0 0 1 90 30 A30 30 0 0 1 120 60 A30 30 0 0 1 90 90
               A30 30 0 0 1 60 120 A30 30 0 0 1 30 90 A30 30 0 0 1 0 60
               A30 30 0 0 1 30 30 A30 30 0 0 1 60 0 Z"
            fill="none" stroke="#5CE1FF" stroke-width="1" stroke-opacity="0.10"/>
    </pattern>
  </defs>
  <rect width="120" height="120" fill="url(#quatrefoil)"/>
</svg>
```

- [ ] **Step 10: Compose the backdrop**

`src/styles/background.css`:

```css
/*
 * Procedural nebula: layered radial gradients tinted from theme tokens, a
 * tiled starfield, and the quatrefoil lattice. Recolours with the theme,
 * costs a few KB, and never animates — a moving background would burn GPU
 * for the entire session.
 */
.citrine-backdrop {
  position: fixed;
  inset: 0;
  z-index: -1;
  background-color: var(--c-bg);
  background-image:
    url('../assets/lattice.svg'),
    url('../assets/starfield.png'),
    radial-gradient(ellipse 60% 45% at 78% 62%, rgb(232 163 61 / 22%), transparent 70%),
    radial-gradient(ellipse 45% 60% at 22% 28%, rgb(150 60 200 / 20%), transparent 72%),
    radial-gradient(ellipse 70% 50% at 50% 105%, rgb(92 225 255 / 10%), transparent 70%),
    radial-gradient(ellipse 80% 60% at 60% 40%, rgb(200 60 120 / 12%), transparent 75%);
  background-repeat: repeat, repeat, no-repeat, no-repeat, no-repeat, no-repeat;
  background-size: 120px 120px, 512px 512px, auto, auto, auto, auto;
  pointer-events: none;
}
```

Add `@import './background.css';` to `src/styles/global.css`.

- [ ] **Step 11: Render the backdrop and verify**

Modify `src/App.tsx`:

```tsx
export function App() {
  return (
    <>
      <div className="citrine-backdrop" aria-hidden="true" />
      <div>Citrine</div>
    </>
  )
}
```

Run: `npm run dev`
Expected: a dark nebula field with visible stars, gold and violet cloud regions, and a faint cyan lattice — recognisably the mockup's backdrop. Compare side by side with `Citrine.png`.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: add bundled font, extracted wordmark, procedural backdrop

The nebula is procedural CSS plus a generated starfield tile rather than a
photographic asset: it recolours with the theme, costs kilobytes instead of
megabytes, and avoids extracting a clean background from the logo art.

The wordmark IS extracted from the logo, deriving alpha from luminance.
That works because it is a bright glow on a dark field, so the falloff
becomes a natural alpha ramp that a hard threshold would destroy."
```

---

### Task 4: Terminal primitives

The reusable shell components. `Panel`'s inset-title treatment is the signature motif of this design and is reused everywhere.

**Files:**
- Create: `src/components/terminal/Frame.tsx`, `Panel.tsx`, `StatusBar.tsx`, `Prompt.tsx`
- Create: `src/components/terminal/terminal.css`
- Test: `src/components/terminal/Panel.test.tsx`, `src/components/terminal/Prompt.test.tsx`, `src/components/terminal/StatusBar.test.tsx`

**Interfaces:**
- Consumes: theme tokens from Task 2.
- Produces:
  - `<Frame title={string} children>` — bordered region with the title inset into the top border.
  - `<Panel title={string} children>` — rail panel, same inset treatment.
  - `<StatusBar segments={Segment[]} right={Segment[]} />` where `type Segment = { id: string; label: string; tone?: 'accent' | 'gold' | 'ok' | 'err' | 'dim' }`.
  - `<Prompt onSubmit={(value: string) => void} disabled?: boolean />` — maintains its own history, exposes nothing else.

- [ ] **Step 1: Write the failing tests for Panel**

`src/components/terminal/Panel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Panel } from './Panel'

describe('Panel', () => {
  it('renders its title', () => {
    render(<Panel title="Available Commands">body</Panel>)
    expect(screen.getByText('Available Commands')).toBeDefined()
  })

  it('renders its children', () => {
    render(<Panel title="Status">the body</Panel>)
    expect(screen.getByText('the body')).toBeDefined()
  })

  it('exposes the title to assistive technology as a group label', () => {
    render(<Panel title="Recent Projects">body</Panel>)
    expect(screen.getByRole('group', { name: 'Recent Projects' })).toBeDefined()
  })
})
```

- [ ] **Step 2: Write the failing tests for Prompt**

`src/components/terminal/Prompt.test.tsx`:

```tsx
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
```

- [ ] **Step 3: Write the failing test for StatusBar**

`src/components/terminal/StatusBar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBar } from './StatusBar'

describe('StatusBar', () => {
  it('renders left and right segments', () => {
    render(
      <StatusBar
        segments={[{ id: 'app', label: 'citrine' }]}
        right={[{ id: 'clock', label: '11:58 PM' }]}
      />,
    )
    expect(screen.getByText('citrine')).toBeDefined()
    expect(screen.getByText('11:58 PM')).toBeDefined()
  })

  it('applies the tone as a data attribute so CSS owns the colour', () => {
    render(<StatusBar segments={[{ id: 'git', label: 'main', tone: 'gold' }]} right={[]} />)
    expect(screen.getByText('main').dataset.tone).toBe('gold')
  })
})
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `npm test -- src/components/terminal`
Expected: FAIL — modules `./Panel`, `./Prompt`, `./StatusBar` cannot be resolved.

- [ ] **Step 5: Implement Panel and Frame**

`src/components/terminal/Panel.tsx`:

```tsx
import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  children: ReactNode
}

/**
 * A bordered region with its title inset into the top border line — the
 * signature motif of the Citrine design. The title sits above the border
 * with a panel-coloured background, "cutting" the line behind it.
 */
export function Panel({ title, children }: PanelProps) {
  return (
    <section className="ct-panel" role="group" aria-label={title}>
      <span className="ct-panel__title">{title}</span>
      <div className="ct-panel__body">{children}</div>
    </section>
  )
}
```

`src/components/terminal/Frame.tsx`:

```tsx
import type { ReactNode } from 'react'

interface FrameProps {
  title: string
  children: ReactNode
}

/** Full-application border carrying the version string in its top edge. */
export function Frame({ title, children }: FrameProps) {
  return (
    <div className="ct-frame">
      <span className="ct-frame__title">{title}</span>
      <div className="ct-frame__body">{children}</div>
    </div>
  )
}
```

- [ ] **Step 6: Implement StatusBar**

`src/components/terminal/StatusBar.tsx`:

```tsx
export type SegmentTone = 'accent' | 'gold' | 'ok' | 'err' | 'dim'

export interface Segment {
  id: string
  label: string
  tone?: SegmentTone
}

interface StatusBarProps {
  segments: Segment[]
  right: Segment[]
}

/** Powerline-style status strip. Tone is a data attribute; CSS owns colour. */
export function StatusBar({ segments, right }: StatusBarProps) {
  return (
    <div className="ct-statusbar" role="status">
      <div className="ct-statusbar__left">
        {segments.map((s) => (
          <span key={s.id} className="ct-statusbar__seg" data-tone={s.tone ?? 'dim'}>
            {s.label}
          </span>
        ))}
      </div>
      <div className="ct-statusbar__right">
        {right.map((s) => (
          <span key={s.id} className="ct-statusbar__seg" data-tone={s.tone ?? 'dim'}>
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Implement Prompt**

`src/components/terminal/Prompt.tsx`:

```tsx
import { useRef, useState, type KeyboardEvent } from 'react'

interface PromptProps {
  onSubmit: (value: string) => void
  disabled?: boolean
}

/**
 * The always-focused input line. Owns its own history: index -1 means "the
 * live draft", and walking forward past the newest entry returns to it.
 */
export function Prompt({ onSubmit, disabled = false }: PromptProps) {
  const [value, setValue] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [index, setIndex] = useState(-1)
  const ref = useRef<HTMLTextAreaElement>(null)

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
    <div className="ct-prompt">
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
  )
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `npm test -- src/components/terminal`
Expected: PASS — 13 passed.

- [ ] **Step 9: Style the primitives**

`src/components/terminal/terminal.css`:

```css
/* Inset-title border treatment, shared by Frame and Panel. */
.ct-frame,
.ct-panel {
  position: relative;
  border: var(--border-w) solid var(--c-border);
  background: var(--c-panel);
}

.ct-frame__title,
.ct-panel__title {
  position: absolute;
  top: 0;
  left: var(--sp-4);
  transform: translateY(-50%);
  padding: 0 var(--sp-2);
  background: var(--c-bg);
  color: var(--c-accent);
  text-shadow: var(--glow-accent);
  font-weight: 700;
  white-space: nowrap;
}

.ct-frame__body,
.ct-panel__body {
  padding: var(--sp-4);
}

.ct-frame {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.ct-frame__body {
  flex: 1;
  min-height: 0;
}

/* Status bar */
.ct-statusbar {
  display: flex;
  justify-content: space-between;
  border-top: var(--border-w) solid var(--c-border);
  padding: var(--sp-2) var(--sp-4);
  background: var(--c-panel);
}
.ct-statusbar__left,
.ct-statusbar__right {
  display: flex;
  gap: var(--sp-4);
}
.ct-statusbar__seg[data-tone='accent'] { color: var(--c-accent); }
.ct-statusbar__seg[data-tone='gold']   { color: var(--c-gold); }
.ct-statusbar__seg[data-tone='ok']     { color: var(--c-ok); }
.ct-statusbar__seg[data-tone='err']    { color: var(--c-err); }
.ct-statusbar__seg[data-tone='dim']    { color: var(--c-text-dim); }

/* Prompt */
.ct-prompt {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
}
.ct-prompt__sigil {
  color: var(--c-accent);
  text-shadow: var(--glow-accent);
  user-select: none;
}
.ct-prompt__input {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--c-text);
  font: inherit;
  caret-color: var(--c-accent);
}
.ct-prompt__input:disabled {
  color: var(--c-text-dim);
}
```

Add `@import '../components/terminal/terminal.css';` to `src/styles/global.css`.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: add terminal primitives (Frame, Panel, StatusBar, Prompt)

Prompt owns its own history with index -1 meaning the live draft, so
walking forward past the newest entry restores what you were typing.
StatusBar takes a tone as a data attribute rather than a colour, keeping
the no-hardcoded-colour rule intact."
```

---

### Task 5: Wire protocol — pydantic models, TypeScript types, contract fixtures

The protocol is hand-maintained in two languages. Shared JSON fixtures validated from both sides are the only thing that catches drift before it becomes a runtime mystery.

**Files:**
- Create: `backend/citrine/protocol.py`
- Create: `src/lib/protocol.ts`
- Create: `tests/fixtures/protocol/*.json` (7 files)
- Test: `backend/tests/test_protocol.py`, `src/lib/protocol.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - Python: `Envelope`, `MessageType`, `AuthParams`, `EchoParams`, `ChatDelta`, `ChatDone`, `ErrorPayload`, `ErrorCode`, `parse_envelope(raw: str) -> Envelope`.
  - TypeScript: `Envelope`, `MessageType`, `ErrorCode`, `envelopeSchema`, `parseEnvelope(raw: string): Envelope`.
  - Both sides use identical wire field names: `id`, `type`, `method`, `params`.

- [ ] **Step 1: Install dependencies**

```bash
cd ~/citrine/backend && uv pip install pydantic
cd ~/citrine && npm install zod
```

Add `"pydantic>=2"` to `dependencies` in `backend/pyproject.toml`.

- [ ] **Step 2: Create the shared contract fixtures**

Create these seven files under `tests/fixtures/protocol/` (repo root, shared by both test suites):

`auth_request.json`:
```json
{ "id": "01J0000000000000000000AUTH", "type": "request", "method": "auth", "params": { "token": "0123456789abcdef" } }
```

`auth_response.json`:
```json
{ "id": "01J0000000000000000000AUTH", "type": "response", "method": "auth", "params": { "ok": true, "server_version": "0.1.0" } }
```

`echo_request.json`:
```json
{ "id": "01J00000000000000000ECHO01", "type": "request", "method": "echo", "params": { "text": "hello" } }
```

`echo_response.json`:
```json
{ "id": "01J00000000000000000ECHO01", "type": "response", "method": "echo", "params": { "text": "hello" } }
```

`chat_delta_event.json`:
```json
{ "id": "01J00000000000000000CHAT01", "type": "event", "method": "chat.delta", "params": { "content": "Hel" } }
```

`chat_done_event.json`:
```json
{ "id": "01J00000000000000000CHAT01", "type": "event", "method": "chat.done", "params": { "prompt_tokens": 12, "completion_tokens": 34, "finish_reason": "stop" } }
```

`error_frame.json`:
```json
{ "id": "01J00000000000000000CHAT01", "type": "error", "method": "chat.send", "params": { "code": "auth", "message": "Invalid API key provided.", "correlation_id": "9f2c1a" } }
```

- [ ] **Step 3: Write the failing Python contract test**

`backend/tests/test_protocol.py`:

```python
import json
from pathlib import Path

import pytest

from citrine.protocol import ErrorCode, MessageType, parse_envelope

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "protocol"
FIXTURE_FILES = sorted(FIXTURES.glob("*.json"))


def test_fixture_directory_is_populated():
    assert len(FIXTURE_FILES) == 7


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_every_fixture_parses(path: Path):
    envelope = parse_envelope(path.read_text(encoding="utf-8"))
    assert envelope.id
    assert isinstance(envelope.type, MessageType)


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_every_fixture_round_trips_without_loss(path: Path):
    original = json.loads(path.read_text(encoding="utf-8"))
    envelope = parse_envelope(path.read_text(encoding="utf-8"))
    assert json.loads(envelope.to_json()) == original


def test_error_codes_cover_the_spec_taxonomy():
    expected = {"auth", "rate_limit", "quota", "network",
                "model_not_found", "context_length", "server"}
    assert {c.value for c in ErrorCode} == expected


def test_unknown_message_type_is_rejected():
    with pytest.raises(ValueError):
        parse_envelope('{"id":"x","type":"telepathy","method":"echo","params":{}}')


def test_missing_id_is_rejected():
    with pytest.raises(ValueError):
        parse_envelope('{"type":"request","method":"echo","params":{}}')


def test_malformed_json_is_rejected():
    with pytest.raises(ValueError):
        parse_envelope("{not json")
```

- [ ] **Step 4: Run it to verify it fails**

Run: `cd ~/citrine/backend && uv run pytest tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'citrine.protocol'`

- [ ] **Step 5: Implement the Python protocol module**

`backend/citrine/protocol.py`:

```python
"""The Citrine wire protocol.

One envelope shape for every message, so the transport layer can demultiplex
without special cases. Streaming is a request that yields many events sharing
the request's id.

The ``request`` type is deliberately bidirectional: slice 4's tool
confirmation becomes a server-to-client request that the client answers with
a response, requiring no protocol migration. The tool frames are declared
here but not implemented in this slice.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError

SERVER_VERSION = "0.1.0"


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


class ErrorCode(str, Enum):
    """The fixed provider-error taxonomy from spec §7."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    NETWORK = "network"
    MODEL_NOT_FOUND = "model_not_found"
    CONTEXT_LENGTH = "context_length"
    SERVER = "server"


class Method(str, Enum):
    AUTH = "auth"
    ECHO = "echo"
    CHAT_SEND = "chat.send"
    CHAT_CANCEL = "chat.cancel"
    CHAT_DELTA = "chat.delta"
    CHAT_DONE = "chat.done"
    CHAT_ERROR = "chat.error"
    # Declared for slice 4; not implemented in this slice.
    TOOL_CONFIRM = "tool.confirm"


class Envelope(BaseModel):
    id: str = Field(min_length=1)
    type: MessageType
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "type": self.type.value,
                "method": self.method,
                "params": self.params,
            },
            separators=(", ", ": "),
        )


# Params payloads. These document the shapes; the envelope carries them as
# plain dicts so unknown future fields survive a round trip.


class AuthParams(BaseModel):
    token: str


class AuthResult(BaseModel):
    ok: bool
    server_version: str = SERVER_VERSION


class EchoParams(BaseModel):
    text: str


class ChatDelta(BaseModel):
    content: str


class ChatDone(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


class ErrorPayload(BaseModel):
    code: ErrorCode
    message: str
    correlation_id: str


def parse_envelope(raw: str) -> Envelope:
    """Parse a wire frame, raising ValueError on anything malformed."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON frame: {exc}") from exc

    try:
        return Envelope.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid envelope: {exc}") from exc


def make_envelope(
    envelope_id: str,
    message_type: MessageType,
    method: str,
    params: dict[str, Any] | None = None,
) -> Envelope:
    return Envelope(id=envelope_id, type=message_type, method=method, params=params or {})
```

- [ ] **Step 6: Run the Python contract test to verify it passes**

Run: `cd ~/citrine/backend && uv run pytest tests/test_protocol.py -v`
Expected: PASS — 24 passed (7 fixtures × 2 parametrised tests + 10 others).

If `to_json` round-trip fails on separator differences, compare parsed objects rather than strings — the test already does this via `json.loads`.

- [ ] **Step 7: Write the failing TypeScript contract test**

`src/lib/protocol.test.ts`:

```ts
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, parseEnvelope } from './protocol'

const FIXTURES = resolve(__dirname, '../../tests/fixtures/protocol')
const files = readdirSync(FIXTURES).filter((f) => f.endsWith('.json'))

describe('protocol contract', () => {
  it('finds the shared fixtures', () => {
    expect(files).toHaveLength(7)
  })

  it.each(files)('parses %s', (file) => {
    const raw = readFileSync(resolve(FIXTURES, file), 'utf-8')
    const envelope = parseEnvelope(raw)
    expect(envelope.id).toBeTruthy()
    expect(envelope.method).toBeTruthy()
  })

  it.each(files)('round-trips %s without loss', (file) => {
    const raw = readFileSync(resolve(FIXTURES, file), 'utf-8')
    expect(JSON.parse(JSON.stringify(parseEnvelope(raw)))).toEqual(JSON.parse(raw))
  })

  it('exposes the same error taxonomy as the backend', () => {
    expect([...ERROR_CODES].sort()).toEqual(
      ['auth', 'context_length', 'model_not_found', 'network', 'quota', 'rate_limit', 'server'],
    )
  })

  it('rejects an unknown message type', () => {
    expect(() => parseEnvelope('{"id":"x","type":"telepathy","method":"echo","params":{}}')).toThrow()
  })

  it('rejects a frame with no id', () => {
    expect(() => parseEnvelope('{"type":"request","method":"echo","params":{}}')).toThrow()
  })

  it('rejects malformed JSON', () => {
    expect(() => parseEnvelope('{not json')).toThrow()
  })
})
```

- [ ] **Step 8: Run it to verify it fails**

Run: `npm test -- src/lib/protocol.test.ts`
Expected: FAIL — cannot resolve `./protocol`.

- [ ] **Step 9: Implement the TypeScript protocol module**

`src/lib/protocol.ts`:

```ts
import { z } from 'zod'

/**
 * Mirror of backend/citrine/protocol.py. The two are hand-maintained, and
 * tests/fixtures/protocol is validated from both sides to catch drift.
 */

export const MESSAGE_TYPES = ['request', 'response', 'event', 'error'] as const
export type MessageType = (typeof MESSAGE_TYPES)[number]

export const ERROR_CODES = [
  'auth',
  'rate_limit',
  'quota',
  'network',
  'model_not_found',
  'context_length',
  'server',
] as const
export type ErrorCode = (typeof ERROR_CODES)[number]

export const METHODS = {
  auth: 'auth',
  echo: 'echo',
  chatSend: 'chat.send',
  chatCancel: 'chat.cancel',
  chatDelta: 'chat.delta',
  chatDone: 'chat.done',
  chatError: 'chat.error',
  /** Declared for slice 4; not implemented in this slice. */
  toolConfirm: 'tool.confirm',
} as const

export const envelopeSchema = z.object({
  id: z.string().min(1),
  type: z.enum(MESSAGE_TYPES),
  method: z.string().min(1),
  params: z.record(z.string(), z.unknown()).default({}),
})

export type Envelope = z.infer<typeof envelopeSchema>

export interface ErrorPayload {
  code: ErrorCode
  message: string
  correlation_id: string
}

export interface ChatDelta {
  content: string
}

export interface ChatDone {
  prompt_tokens: number
  completion_tokens: number
  finish_reason: string
}

export function parseEnvelope(raw: string): Envelope {
  const parsed: unknown = JSON.parse(raw)
  return envelopeSchema.parse(parsed)
}

export function serialiseEnvelope(envelope: Envelope): string {
  return JSON.stringify(envelope)
}

let counter = 0
/** Monotonic, collision-free within a session; ids need not be UUIDs. */
export function nextId(prefix = 'req'): string {
  counter += 1
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}`
}
```

- [ ] **Step 10: Run the TypeScript contract test to verify it passes**

Run: `npm test -- src/lib/protocol.test.ts`
Expected: PASS — 18 passed.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: define wire protocol in Python and TypeScript with shared fixtures

The protocol is hand-maintained in two languages, so seven shared JSON
fixtures are validated from both sides. That is the only mechanism that
catches drift before it becomes a runtime mystery.

The request type is bidirectional so slice 4's tool confirmation needs no
protocol migration; those frames are declared but not implemented."
```

---

### Task 6: Python WebSocket server with authentication gate

**Files:**
- Create: `backend/citrine/logging.py`, `backend/citrine/server.py`
- Test: `backend/tests/test_logging.py`, `backend/tests/test_server.py`

**Interfaces:**
- Consumes: `citrine.protocol` (Task 5), `citrine.paths` (Task 1).
- Produces:
  - `citrine.server.create_app(token: str, allowed_origins: set[str]) -> FastAPI` with a `/ws` endpoint.
  - `citrine.server.main() -> None` — CLI entry, accepts `--port` (default 0) and `--host` (default `127.0.0.1`), prints exactly one handshake line to stdout: `{"event":"ready","port":<int>}`.
  - `citrine.logging.get_logger(name: str) -> logging.Logger` and `citrine.logging.redact(text: str) -> str`.

- [ ] **Step 1: Install dependencies**

```bash
cd ~/citrine/backend && uv pip install "fastapi" "uvicorn[standard]" "websockets" "httpx" "pytest-asyncio"
```

Add `"fastapi>=0.115"`, `"uvicorn[standard]>=0.30"`, `"websockets>=13"` to `dependencies`, and `"httpx>=0.27"`, `"pytest-asyncio>=0.24"` to the `dev` extras in `backend/pyproject.toml`.

- [ ] **Step 2: Write the failing test for redaction**

`backend/tests/test_logging.py`:

```python
import logging

from citrine.logging import get_logger, redact


def test_redacts_openai_style_keys():
    assert "sk-abcdef0123456789abcdef" not in redact("key is sk-abcdef0123456789abcdef here")


def test_redaction_leaves_a_marker():
    assert "[REDACTED]" in redact("key is sk-abcdef0123456789abcdef here")


def test_redacts_anthropic_style_keys():
    assert "sk-ant-" not in redact("sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaa")


def test_redacts_bearer_tokens():
    assert "deadbeefdeadbeefdeadbeef" not in redact("Authorization: Bearer deadbeefdeadbeefdeadbeef")


def test_redacts_json_token_fields():
    assert "hunter2hunter2hunter2" not in redact('{"token": "hunter2hunter2hunter2"}')


def test_leaves_ordinary_text_alone():
    assert redact("connected on port 54321") == "connected on port 54321"


def test_logger_output_is_redacted(caplog):
    """Redaction happens at the logger, so no call site can forget it."""
    logger = get_logger("citrine.test")
    with caplog.at_level(logging.INFO):
        logger.info("saving sk-abcdef0123456789abcdef")
    assert "sk-abcdef0123456789abcdef" not in caplog.text
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd ~/citrine/backend && uv run pytest tests/test_logging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'citrine.logging'`

- [ ] **Step 4: Implement the logging module**

`backend/citrine/logging.py`:

```python
"""Structured logging with key redaction enforced at the logger.

Redaction is applied by a filter rather than at call sites: a rule enforced
in one place cannot be forgotten in fifty.
"""

from __future__ import annotations

import logging
import re
import sys

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r'(?i)("(?:token|api_key|secret|password)"\s*:\s*")[^"]{8,}(")'),
)

REDACTION = "[REDACTED]"


def redact(text: str) -> str:
    """Strip anything that looks like credential material."""
    result = text
    result = _PATTERNS[3].sub(rf"\1{REDACTION}\2", result)
    for pattern in _PATTERNS[:3]:
        result = pattern.sub(REDACTION, result)
    return result


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(_RedactingFilter())
    root = logging.getLogger("citrine")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    logger = logging.getLogger(name)
    logger.addFilter(_RedactingFilter())
    return logger
```

Note: the handshake line goes to **stdout**; all logging goes to **stderr**, so log output can never corrupt the handshake Electron parses.

- [ ] **Step 5: Run the logging tests to verify they pass**

Run: `cd ~/citrine/backend && uv run pytest tests/test_logging.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 6: Write the failing test for the server**

`backend/tests/test_server.py`:

```python
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from citrine.protocol import MessageType, parse_envelope
from citrine.server import create_app

TOKEN = "test-token-0123456789"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def client():
    app = create_app(token=TOKEN, allowed_origins={ORIGIN})
    return TestClient(app)


def _auth_frame(token: str = TOKEN) -> str:
    return json.dumps({"id": "a1", "type": "request", "method": "auth",
                       "params": {"token": token}})


def test_valid_token_is_accepted(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        reply = parse_envelope(ws.receive_text())
        assert reply.type is MessageType.RESPONSE
        assert reply.params["ok"] is True


def test_auth_reply_reuses_the_request_id(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        assert parse_envelope(ws.receive_text()).id == "a1"


def test_bad_token_closes_with_4401(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
            ws.send_text(_auth_frame("wrong-token"))
            ws.receive_text()
    assert excinfo.value.code == 4401


def test_non_auth_first_frame_closes_with_4401(client):
    """Auth must be the first frame; no other method is processed before it."""
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
            ws.send_text(json.dumps({"id": "e1", "type": "request",
                                     "method": "echo", "params": {"text": "hi"}}))
            ws.receive_text()
    assert excinfo.value.code == 4401


def test_malformed_first_frame_closes_with_4401(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
            ws.send_text("{not json")
            ws.receive_text()
    assert excinfo.value.code == 4401


def test_disallowed_origin_is_rejected(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws:
            ws.send_text(_auth_frame())
            ws.receive_text()
    assert excinfo.value.code == 4403


def test_echo_round_trips_after_authentication(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "e2", "type": "request", "method": "echo",
                                 "params": {"text": "hello spine"}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.id == "e2"
        assert reply.params["text"] == "hello spine"


def test_unknown_method_returns_an_error_frame_without_closing(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "u1", "type": "request",
                                 "method": "nonexistent", "params": {}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.type is MessageType.ERROR
        assert reply.params["code"] == "server"
        assert reply.params["correlation_id"]

        # The connection survives: a later echo still works.
        ws.send_text(json.dumps({"id": "e3", "type": "request", "method": "echo",
                                 "params": {"text": "still here"}}))
        assert parse_envelope(ws.receive_text()).params["text"] == "still here"
```

- [ ] **Step 7: Run it to verify it fails**

Run: `cd ~/citrine/backend && uv run pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'citrine.server'`

- [ ] **Step 8: Implement the server**

`backend/citrine/server.py`:

```python
"""The Citrine backend: a FastAPI WebSocket server bound to loopback.

Security posture (spec §2.4): a localhost port is reachable by any local
process, and this backend gains desktop control in slice 4. So the first
frame must be a valid auth request, the Origin header is checked, and
failures close the socket before any other message is processed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import uuid

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from citrine.logging import get_logger
from citrine.protocol import (
    SERVER_VERSION,
    ErrorCode,
    MessageType,
    make_envelope,
    parse_envelope,
)

log = get_logger("citrine.server")

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403


def create_app(token: str, allowed_origins: set[str]) -> FastAPI:
    app = FastAPI(title="Citrine backend", version=SERVER_VERSION)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        await websocket.accept()

        # Origin is advisory on non-browser clients but blocks the browser
        # attack path outright, which is the one we can actually close.
        if origin is not None and origin not in allowed_origins:
            log.warning("rejected connection from origin %s", origin)
            await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
            return

        if not await _authenticate(websocket, token):
            return

        await _serve(websocket)

    return app


async def _authenticate(websocket: WebSocket, token: str) -> bool:
    """Consume the first frame and require it to be a valid auth request."""
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return False

    try:
        envelope = parse_envelope(raw)
    except ValueError:
        log.warning("malformed first frame; closing")
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return False

    supplied = envelope.params.get("token")
    if envelope.method != "auth" or not isinstance(supplied, str):
        log.warning("first frame was %s, not auth; closing", envelope.method)
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return False

    # Constant-time comparison: the token is a session secret.
    if not secrets.compare_digest(supplied, token):
        log.warning("invalid token; closing")
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return False

    reply = make_envelope(
        envelope.id, MessageType.RESPONSE, "auth",
        {"ok": True, "server_version": SERVER_VERSION},
    )
    await websocket.send_text(reply.to_json())
    log.info("client authenticated")
    return True


async def _serve(websocket: WebSocket) -> None:
    """Message loop for an authenticated connection."""
    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            log.info("client disconnected")
            return

        try:
            envelope = parse_envelope(raw)
        except ValueError as exc:
            await _send_error(websocket, "unknown", "unknown", str(exc))
            continue

        log.info("recv %s %s", envelope.method, envelope.id)

        if envelope.method == "echo":
            text = envelope.params.get("text", "")
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "echo",
                                  {"text": text})
            await websocket.send_text(reply.to_json())
            continue

        await _send_error(
            websocket, envelope.id, envelope.method,
            f"unknown method: {envelope.method}",
        )


async def _send_error(
    websocket: WebSocket, envelope_id: str, method: str, message: str
) -> None:
    correlation_id = uuid.uuid4().hex[:6]
    log.warning("error %s (%s): %s", method, correlation_id, message)
    frame = make_envelope(
        envelope_id, MessageType.ERROR, method,
        {
            "code": ErrorCode.SERVER.value,
            "message": message,
            "correlation_id": correlation_id,
        },
    )
    await websocket.send_text(frame.to_json())


class _AnnouncingServer(uvicorn.Server):
    """A uvicorn server that announces its real port once the socket is bound.

    With ``--port 0`` the OS assigns the port, so it is unknowable until
    after bind. Overriding ``startup`` is the supported hook that runs at
    exactly that moment.

    The announcement is the only thing ever written to stdout, so Electron
    can parse it unambiguously; all logging goes to stderr.
    """

    async def startup(self, sockets: list | None = None) -> None:
        await super().startup(sockets=sockets)
        print(json.dumps({"event": "ready", "port": self._bound_port()}), flush=True)

    def _bound_port(self) -> int:
        for server in getattr(self, "servers", []):
            for sock in server.sockets:
                return int(sock.getsockname()[1])
        return self.config.port


def main() -> None:
    parser = argparse.ArgumentParser(description="Citrine backend")
    parser.add_argument("--host", default="127.0.0.1",
                        help="loopback only; never bind 0.0.0.0")
    parser.add_argument("--port", type=int, default=0,
                        help="0 lets the OS assign a free port")
    parser.add_argument("--origin", action="append", default=[],
                        help="allowed Origin header value; repeatable")
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        print("refusing to bind anything but loopback", file=sys.stderr)
        raise SystemExit(2)

    token = _require_token()
    app = create_app(token=token, allowed_origins=set(args.origin))

    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_config=None, access_log=False)
    _AnnouncingServer(config).run()


def _require_token() -> str:
    token = os.environ.get("CITRINE_AUTH_TOKEN")
    if not token:
        print(
            "CITRINE_AUTH_TOKEN is not set. The backend refuses to run "
            "unauthenticated because it binds a local port.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return token


if __name__ == "__main__":
    main()
```

**Note for the implementer:** `_AnnouncingServer.startup` overrides a uvicorn method whose signature has shifted across versions. If `super().startup(sockets=sockets)` raises a `TypeError`, check the installed signature with `python -c "import inspect, uvicorn; print(inspect.signature(uvicorn.Server.startup))"` and match it. The contract that must hold regardless: exactly one JSON line on stdout, printed after the socket is bound, containing the real port.

- [ ] **Step 9: Run the server tests to verify they pass**

Run: `cd ~/citrine/backend && uv run pytest tests/test_server.py -v`
Expected: PASS — 8 passed.

- [ ] **Step 10: Verify the handshake manually**

```bash
cd ~/citrine/backend
CITRINE_AUTH_TOKEN=devtoken uv run python -m citrine.server --port 0
```

Expected: exactly one line on stdout, e.g. `{"event": "ready", "port": 54873}`, with the port non-zero and different between runs. Log lines appear on stderr, never mixed into stdout. Stop with Ctrl+C.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: add authenticated WebSocket backend

The first frame must be a valid auth request or the socket closes with
4401 before any other message is processed; Origin mismatches close with
4403. Token comparison is constant-time.

The ready handshake is the only thing ever written to stdout, so Electron
can parse it unambiguously; all logging goes to stderr. Redaction is
applied by a logging filter rather than at call sites."
```

---

### Task 7: Electron sidecar supervisor and preload bridge

**Files:**
- Create: `electron/sidecar.ts`
- Modify: `electron/main.ts`, `electron/preload.ts`
- Create: `src/types/window.d.ts`
- Test: `electron/sidecar.test.ts`

**Interfaces:**
- Consumes: the backend CLI contract from Task 6 (`CITRINE_AUTH_TOKEN` env var, `--port 0`, one stdout handshake line).
- Produces:
  - `parseReadyLine(line: string): number | null` — pure, exported for testing.
  - `nextBackoffMs(attempt: number): number` — pure.
  - `class Sidecar` with `start(): Promise<BackendInfo>`, `stop(): void`, `onStateChange(cb: (s: SidecarState) => void): void`.
  - `type BackendInfo = { port: number; token: string }`, `type SidecarState = 'starting' | 'ready' | 'restarting' | 'failed'`.
  - Renderer global: `window.citrine.getBackendInfo(): Promise<BackendInfo | null>`.

- [ ] **Step 1: Write the failing test for the pure helpers**

`electron/sidecar.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { MAX_RESTART_ATTEMPTS, nextBackoffMs, parseReadyLine } from './sidecar'

describe('parseReadyLine', () => {
  it('extracts the port from a ready handshake', () => {
    expect(parseReadyLine('{"event": "ready", "port": 54873}')).toBe(54873)
  })

  it('tolerates surrounding whitespace', () => {
    expect(parseReadyLine('  {"event":"ready","port":1234}  \r')).toBe(1234)
  })

  it('ignores unrelated JSON lines', () => {
    expect(parseReadyLine('{"event": "something-else", "port": 1}')).toBeNull()
  })

  it('ignores non-JSON noise', () => {
    expect(parseReadyLine('INFO starting up')).toBeNull()
  })

  it('rejects a ready line with a missing port', () => {
    expect(parseReadyLine('{"event": "ready"}')).toBeNull()
  })

  it('rejects a non-numeric port', () => {
    expect(parseReadyLine('{"event": "ready", "port": "54873"}')).toBeNull()
  })

  it('rejects port zero, which means the socket never bound', () => {
    expect(parseReadyLine('{"event": "ready", "port": 0}')).toBeNull()
  })
})

describe('nextBackoffMs', () => {
  it('starts small', () => {
    expect(nextBackoffMs(0)).toBe(250)
  })

  it('doubles with each attempt', () => {
    expect(nextBackoffMs(1)).toBe(500)
    expect(nextBackoffMs(2)).toBe(1000)
  })

  it('caps so a persistent failure does not back off forever', () => {
    expect(nextBackoffMs(99)).toBeLessThanOrEqual(8000)
  })

  it('gives up after five attempts, per spec', () => {
    expect(MAX_RESTART_ATTEMPTS).toBe(5)
  })
})
```

- [ ] **Step 2: Add electron files to the Vitest include list**

Modify `vitest.config.ts`, replacing the `include` line:

```ts
    include: ['src/**/*.test.{ts,tsx}', 'electron/**/*.test.ts'],
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- electron/sidecar.test.ts`
Expected: FAIL — cannot resolve `./sidecar`.

- [ ] **Step 4: Implement the sidecar supervisor**

`electron/sidecar.ts`:

```ts
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

export interface BackendInfo {
  port: number
  token: string
}

export type SidecarState = 'starting' | 'ready' | 'restarting' | 'failed'

export const MAX_RESTART_ATTEMPTS = 5
const BASE_BACKOFF_MS = 250
const MAX_BACKOFF_MS = 8000
const READY_TIMEOUT_MS = 20_000

/**
 * Parse the backend's single stdout handshake line.
 * Returns null for anything that is not a well-formed ready announcement,
 * including port 0 — which would mean the socket never actually bound.
 */
export function parseReadyLine(line: string): number | null {
  const trimmed = line.trim()
  if (!trimmed.startsWith('{')) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return null
  }

  if (typeof parsed !== 'object' || parsed === null) return null
  const record = parsed as Record<string, unknown>
  if (record.event !== 'ready') return null
  if (typeof record.port !== 'number' || !Number.isInteger(record.port)) return null
  if (record.port <= 0) return null
  return record.port
}

export function nextBackoffMs(attempt: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS)
}

function pythonExecutable(projectRoot: string): string {
  const venvWin = resolve(projectRoot, 'backend/.venv/Scripts/python.exe')
  const venvPosix = resolve(projectRoot, 'backend/.venv/bin/python')
  if (existsSync(venvWin)) return venvWin
  if (existsSync(venvPosix)) return venvPosix
  return process.platform === 'win32' ? 'python' : 'python3'
}

export class Sidecar {
  private child: ChildProcessWithoutNullStreams | null = null
  private info: BackendInfo | null = null
  private attempt = 0
  private stopping = false
  private listeners: Array<(s: SidecarState) => void> = []

  constructor(
    private readonly projectRoot: string,
    private readonly allowedOrigin: string,
    private readonly token: string = randomBytes(32).toString('hex'),
  ) {}

  onStateChange(cb: (s: SidecarState) => void): void {
    this.listeners.push(cb)
  }

  private emit(state: SidecarState): void {
    for (const cb of this.listeners) cb(state)
  }

  getInfo(): BackendInfo | null {
    return this.info
  }

  async start(): Promise<BackendInfo> {
    this.emit('starting')
    const info = await this.spawnOnce()
    this.info = info
    this.attempt = 0
    this.emit('ready')
    return info
  }

  private spawnOnce(): Promise<BackendInfo> {
    return new Promise<BackendInfo>((resolvePromise, rejectPromise) => {
      const python = pythonExecutable(this.projectRoot)
      const child = spawn(
        python,
        ['-m', 'citrine.server', '--port', '0', '--host', '127.0.0.1',
         '--origin', this.allowedOrigin],
        {
          cwd: resolve(this.projectRoot, 'backend'),
          env: { ...process.env, CITRINE_AUTH_TOKEN: this.token, PYTHONUNBUFFERED: '1' },
        },
      ) as ChildProcessWithoutNullStreams

      this.child = child

      let settled = false
      let stdoutBuffer = ''
      const stderrTail: string[] = []

      const timer = setTimeout(() => {
        if (settled) return
        settled = true
        child.kill()
        rejectPromise(
          new Error(
            `Backend did not announce readiness within ${READY_TIMEOUT_MS}ms.\n` +
              stderrTail.join(''),
          ),
        )
      }, READY_TIMEOUT_MS)

      child.stdout.setEncoding('utf-8')
      child.stdout.on('data', (chunk: string) => {
        stdoutBuffer += chunk
        let newline: number
        while ((newline = stdoutBuffer.indexOf('\n')) !== -1) {
          const line = stdoutBuffer.slice(0, newline)
          stdoutBuffer = stdoutBuffer.slice(newline + 1)
          const port = parseReadyLine(line)
          if (port !== null && !settled) {
            settled = true
            clearTimeout(timer)
            resolvePromise({ port, token: this.token })
          }
        }
      })

      child.stderr.setEncoding('utf-8')
      child.stderr.on('data', (chunk: string) => {
        stderrTail.push(chunk)
        if (stderrTail.length > 50) stderrTail.shift()
        process.stderr.write(`[backend] ${chunk}`)
      })

      child.on('error', (err) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        rejectPromise(
          new Error(`Failed to launch Python at "${python}": ${err.message}`),
        )
      })

      child.on('exit', (code) => {
        clearTimeout(timer)
        if (!settled) {
          settled = true
          rejectPromise(
            new Error(
              `Backend exited with code ${code} before becoming ready.\n` +
                stderrTail.join(''),
            ),
          )
          return
        }
        void this.handleUnexpectedExit()
      })
    })
  }

  private async handleUnexpectedExit(): Promise<void> {
    if (this.stopping) return
    this.info = null

    if (this.attempt >= MAX_RESTART_ATTEMPTS) {
      this.emit('failed')
      return
    }

    const delay = nextBackoffMs(this.attempt)
    this.attempt += 1
    this.emit('restarting')
    await new Promise((r) => setTimeout(r, delay))
    if (this.stopping) return

    try {
      this.info = await this.spawnOnce()
      this.attempt = 0
      this.emit('ready')
    } catch {
      void this.handleUnexpectedExit()
    }
  }

  stop(): void {
    this.stopping = true
    this.child?.kill()
    this.child = null
    this.info = null
  }
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- electron/sidecar.test.ts`
Expected: PASS — 11 passed.

- [ ] **Step 6: Wire the sidecar into main and expose it via preload**

Replace `electron/main.ts`:

```ts
import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { resolve } from 'node:path'
import { Sidecar, type BackendInfo } from './sidecar'

const projectRoot = resolve(__dirname, '../..')
const rendererOrigin = process.env.ELECTRON_RENDERER_URL
  ? new URL(process.env.ELECTRON_RENDERER_URL).origin
  : 'file://'

let sidecar: Sidecar | null = null
let backendInfo: BackendInfo | null = null

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1680,
    height: 960,
    backgroundColor: '#05030F',
    show: false,
    webPreferences: {
      preload: resolve(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  win.once('ready-to-show', () => win.show())

  if (process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void win.loadFile(resolve(__dirname, '../renderer/index.html'))
  }
  return win
}

function broadcast(channel: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send(channel, payload)
  }
}

void app.whenReady().then(async () => {
  ipcMain.handle('citrine:getBackendInfo', () => backendInfo)

  sidecar = new Sidecar(projectRoot, rendererOrigin)
  sidecar.onStateChange((state) => {
    if (state !== 'ready') backendInfo = null
    else backendInfo = sidecar?.getInfo() ?? null
    broadcast('citrine:sidecarState', state)
  })

  try {
    backendInfo = await sidecar.start()
  } catch (error) {
    // A silent failure here is the most likely way to waste an hour, so it
    // is always surfaced with the captured stderr rather than a blank window.
    dialog.showErrorBox(
      'Citrine backend failed to start',
      error instanceof Error ? error.message : String(error),
    )
    app.quit()
    return
  }

  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => sidecar?.stop())
```

Replace `electron/preload.ts`:

```ts
import { contextBridge, ipcRenderer } from 'electron'

/** The entire renderer-facing surface. Nothing else crosses the bridge. */
contextBridge.exposeInMainWorld('citrine', {
  getBackendInfo: (): Promise<{ port: number; token: string } | null> =>
    ipcRenderer.invoke('citrine:getBackendInfo'),
  onSidecarState: (cb: (state: string) => void): void => {
    ipcRenderer.on('citrine:sidecarState', (_event, state: string) => cb(state))
  },
})
```

`src/types/window.d.ts`:

```ts
export {}

declare global {
  interface Window {
    citrine: {
      getBackendInfo: () => Promise<{ port: number; token: string } | null>
      onSidecarState: (cb: (state: string) => void) => void
    }
  }
}
```

- [ ] **Step 7: Verify the full launch path**

Run: `npm run dev`
Expected: the window opens as before. The terminal shows `[backend]` log lines on stderr. In the renderer DevTools console, `await window.citrine.getBackendInfo()` returns `{port: <number>, token: "<64 hex chars>"}`.

Then verify supervision: find the Python process in Task Manager and end it. Expected: `[backend]` output resumes within a second as the sidecar restarts, and `getBackendInfo()` returns a **new** port.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: spawn and supervise the Python sidecar from Electron

Electron generates a 32-byte token, spawns the backend with --port 0, and
discovers the real port from the single stdout handshake line. Crashes
restart with exponential backoff, capped at five attempts.

A backend that fails to start shows a dialog with captured stderr rather
than a blank window, since a silent failure there is the most likely way
to waste an hour."
```

---

### Task 8: Renderer transport client

**Files:**
- Create: `src/lib/transport.ts`
- Test: `src/lib/transport.test.ts`

**Interfaces:**
- Consumes: `src/lib/protocol.ts` (Task 5), `window.citrine` (Task 7).
- Produces: `class Transport` with `connect(info: BackendInfo): Promise<void>`, `request<T>(method: string, params?: object): Promise<T>`, `stream(method: string, params, handlers: StreamHandlers): () => void`, `close(): void`, `onStateChange(cb: (s: ConnectionState) => void): void`; `type ConnectionState = 'idle' | 'connecting' | 'authenticating' | 'open' | 'reconnecting' | 'closed'`.

- [ ] **Step 1: Write the failing test**

`src/lib/transport.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Transport, type ConnectionState } from './transport'

/** Minimal scriptable WebSocket double. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }
  send(data: string): void {
    this.sent.push(data)
  }
  close(): void {
    this.readyState = 3
    this.onclose?.({ code: 1000 })
  }
  // Test helpers
  open(): void {
    this.readyState = 1
    this.onopen?.()
  }
  receive(frame: object): void {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
  get lastSent(): Record<string, unknown> {
    return JSON.parse(this.sent[this.sent.length - 1]!)
  }
}

function connectAndAuth(transport: Transport) {
  const promise = transport.connect({ port: 5000, token: 'tok' })
  const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]!
  ws.open()
  const authFrame = ws.lastSent
  ws.receive({ id: authFrame.id, type: 'response', method: 'auth', params: { ok: true } })
  return { promise, ws }
}

describe('Transport', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  it('connects to the loopback address on the given port', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    expect(ws.url).toBe('ws://127.0.0.1:5000/ws')
  })

  it('sends the auth token as its very first frame', async () => {
    const t = new Transport()
    const promise = t.connect({ port: 5000, token: 'sekrit' })
    const ws = FakeWebSocket.instances[0]!
    ws.open()
    const first = JSON.parse(ws.sent[0]!)
    expect(first.method).toBe('auth')
    expect(first.params.token).toBe('sekrit')
    ws.receive({ id: first.id, type: 'response', method: 'auth', params: { ok: true } })
    await promise
  })

  it('resolves connect only after authentication succeeds', async () => {
    const t = new Transport()
    const states: ConnectionState[] = []
    t.onStateChange((s) => states.push(s))
    const { promise } = connectAndAuth(t)
    await promise
    expect(states).toContain('authenticating')
    expect(states.at(-1)).toBe('open')
  })

  it('rejects connect when the socket closes with 4401', async () => {
    const t = new Transport()
    const promise = t.connect({ port: 5000, token: 'bad' })
    const ws = FakeWebSocket.instances[0]!
    ws.open()
    ws.onclose?.({ code: 4401 })
    await expect(promise).rejects.toThrow(/authentication/i)
  })

  it('correlates a response to its request', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const pending = t.request<{ text: string }>('echo', { text: 'hi' })
    const sent = ws.lastSent
    ws.receive({ id: sent.id, type: 'response', method: 'echo', params: { text: 'hi' } })
    expect(await pending).toEqual({ text: 'hi' })
  })

  it('rejects a request when an error frame arrives for it', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const pending = t.request('echo', { text: 'hi' })
    const sent = ws.lastSent
    ws.receive({
      id: sent.id, type: 'error', method: 'echo',
      params: { code: 'server', message: 'boom', correlation_id: 'abc123' },
    })
    await expect(pending).rejects.toThrow(/boom/)
  })

  it('ignores a response whose id matches nothing', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    expect(() =>
      ws.receive({ id: 'nobody', type: 'response', method: 'echo', params: {} }),
    ).not.toThrow()
  })

  it('routes stream events to the matching handler by id', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const deltas: string[] = []
    let finished = false
    t.stream('chat.send', { text: 'x' }, {
      onDelta: (d) => deltas.push(d.content as string),
      onDone: () => { finished = true },
      onError: () => {},
    })
    const sent = ws.lastSent
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'He' } })
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'llo' } })
    ws.receive({ id: sent.id, type: 'event', method: 'chat.done', params: {} })
    expect(deltas).toEqual(['He', 'llo'])
    expect(finished).toBe(true)
  })

  it('stops delivering events after the stream is cancelled', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const deltas: string[] = []
    const cancel = t.stream('chat.send', {}, {
      onDelta: (d) => deltas.push(d.content as string),
      onDone: () => {},
      onError: () => {},
    })
    const sent = ws.lastSent
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'a' } })
    cancel()
    ws.receive({ id: sent.id, type: 'event', method: 'chat.delta', params: { content: 'b' } })
    expect(deltas).toEqual(['a'])
  })

  it('sends a cancel frame carrying the original request id', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const cancel = t.stream('chat.send', {}, { onDelta: () => {}, onDone: () => {}, onError: () => {} })
    const streamId = ws.lastSent.id
    cancel()
    expect(ws.lastSent.method).toBe('chat.cancel')
    expect(ws.lastSent.params).toMatchObject({ target_id: streamId })
  })

  it('fails queued requests fast when the socket is not open', async () => {
    const t = new Transport()
    await expect(t.request('echo', {})).rejects.toThrow(/not connected/i)
  })

  it('reports reconnecting when the socket drops unexpectedly', async () => {
    const t = new Transport()
    const states: ConnectionState[] = []
    const { promise, ws } = connectAndAuth(t)
    await promise
    t.onStateChange((s) => states.push(s))
    ws.onclose?.({ code: 1006 })
    expect(states).toContain('reconnecting')
  })

  it('rejects in-flight requests when the socket drops', async () => {
    const t = new Transport()
    const { promise, ws } = connectAndAuth(t)
    await promise
    const pending = t.request('echo', {})
    ws.onclose?.({ code: 1006 })
    await expect(pending).rejects.toThrow(/connection lost/i)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- src/lib/transport.test.ts`
Expected: FAIL — cannot resolve `./transport`.

- [ ] **Step 3: Implement the transport**

`src/lib/transport.ts`:

```ts
import { METHODS, nextId, parseEnvelope, type Envelope } from './protocol'

export interface BackendInfo {
  port: number
  token: string
}

export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'authenticating'
  | 'open'
  | 'reconnecting'
  | 'closed'

export interface StreamHandlers {
  onDelta: (params: Record<string, unknown>) => void
  onDone: (params: Record<string, unknown>) => void
  onError: (params: Record<string, unknown>) => void
}

interface Pending {
  resolve: (value: never) => void
  reject: (reason: Error) => void
}

const RECONNECT_BASE_MS = 300
const RECONNECT_MAX_MS = 5000

/**
 * WebSocket client for the Citrine backend.
 *
 * Every frame carries an id, so responses and stream events demultiplex
 * through the same map without special cases. Requests fail fast when the
 * socket is not open rather than queueing forever — a hung promise is far
 * harder to diagnose than an immediate rejection.
 */
export class Transport {
  private socket: WebSocket | null = null
  private info: BackendInfo | null = null
  private state: ConnectionState = 'idle'
  private pending = new Map<string, Pending>()
  private streams = new Map<string, StreamHandlers>()
  private listeners: Array<(s: ConnectionState) => void> = []
  private reconnectAttempt = 0
  private intentionalClose = false

  onStateChange(cb: (s: ConnectionState) => void): void {
    this.listeners.push(cb)
  }

  getState(): ConnectionState {
    return this.state
  }

  private setState(state: ConnectionState): void {
    this.state = state
    for (const cb of this.listeners) cb(state)
  }

  connect(info: BackendInfo): Promise<void> {
    this.info = info
    this.intentionalClose = false
    return new Promise<void>((resolve, reject) => {
      this.setState('connecting')
      const socket = new WebSocket(`ws://127.0.0.1:${info.port}/ws`)
      this.socket = socket

      let authSettled = false

      socket.onopen = () => {
        this.setState('authenticating')
        const id = nextId('auth')
        this.pending.set(id, {
          resolve: () => {
            authSettled = true
            this.reconnectAttempt = 0
            this.setState('open')
            resolve()
          },
          reject: (err) => {
            authSettled = true
            reject(err)
          },
        } as Pending)
        socket.send(
          JSON.stringify({
            id,
            type: 'request',
            method: METHODS.auth,
            params: { token: info.token },
          }),
        )
      }

      socket.onmessage = (event: { data: string }) => {
        this.handleFrame(String(event.data))
      }

      socket.onclose = (event: { code: number }) => {
        if (!authSettled) {
          authSettled = true
          reject(
            new Error(
              event.code === 4401
                ? 'Backend rejected authentication (4401).'
                : event.code === 4403
                  ? 'Backend rejected the connection origin (4403).'
                  : `Connection closed before authentication (${event.code}).`,
            ),
          )
          return
        }
        this.handleUnexpectedClose()
      }

      socket.onerror = () => {
        /* onclose always follows; handled there. */
      }
    })
  }

  private handleFrame(raw: string): void {
    let envelope: Envelope
    try {
      envelope = parseEnvelope(raw)
    } catch {
      return // A frame we cannot parse is not worth tearing the socket down.
    }

    if (envelope.type === 'event') {
      const handlers = this.streams.get(envelope.id)
      if (!handlers) return
      if (envelope.method === METHODS.chatDelta) handlers.onDelta(envelope.params)
      else if (envelope.method === METHODS.chatDone) {
        this.streams.delete(envelope.id)
        handlers.onDone(envelope.params)
      } else if (envelope.method === METHODS.chatError) {
        this.streams.delete(envelope.id)
        handlers.onError(envelope.params)
      }
      return
    }

    const pending = this.pending.get(envelope.id)
    if (!pending) {
      // Could also be a terminal error for a stream.
      const handlers = this.streams.get(envelope.id)
      if (handlers && envelope.type === 'error') {
        this.streams.delete(envelope.id)
        handlers.onError(envelope.params)
      }
      return
    }

    this.pending.delete(envelope.id)
    if (envelope.type === 'error') {
      const message = String(envelope.params.message ?? 'Backend error')
      const correlation = envelope.params.correlation_id
      pending.reject(
        new Error(correlation ? `${message} (ref ${String(correlation)})` : message),
      )
      return
    }
    ;(pending.resolve as (v: unknown) => void)(envelope.params)
  }

  private handleUnexpectedClose(): void {
    const error = new Error('Connection lost.')
    for (const [, pending] of this.pending) pending.reject(error)
    this.pending.clear()
    for (const [, handlers] of this.streams) {
      handlers.onError({ code: 'network', message: 'Connection lost.', correlation_id: '' })
    }
    this.streams.clear()

    if (this.intentionalClose) {
      this.setState('closed')
      return
    }

    this.setState('reconnecting')
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this.reconnectAttempt,
      RECONNECT_MAX_MS,
    )
    this.reconnectAttempt += 1
    setTimeout(() => {
      if (this.intentionalClose || !this.info) return
      void this.connect(this.info).catch(() => {
        /* onclose schedules the next attempt. */
      })
    }, delay)
  }

  request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (!this.socket || this.state !== 'open') {
      return Promise.reject(new Error('Not connected to the Citrine backend.'))
    }
    const id = nextId('req')
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject } as unknown as Pending)
      this.socket!.send(JSON.stringify({ id, type: 'request', method, params }))
    })
  }

  /** Start a streaming request. Returns a cancel function. */
  stream(
    method: string,
    params: Record<string, unknown>,
    handlers: StreamHandlers,
  ): () => void {
    const id = nextId('stream')
    this.streams.set(id, handlers)
    this.socket?.send(JSON.stringify({ id, type: 'request', method, params }))

    return () => {
      if (!this.streams.has(id)) return
      this.streams.delete(id)
      this.socket?.send(
        JSON.stringify({
          id: nextId('cancel'),
          type: 'request',
          method: METHODS.chatCancel,
          params: { target_id: id },
        }),
      )
    }
  }

  close(): void {
    this.intentionalClose = true
    this.socket?.close()
    this.socket = null
    this.setState('closed')
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- src/lib/transport.test.ts`
Expected: PASS — 13 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add renderer WebSocket transport with demux and reconnect

Every frame carries an id, so responses and stream events demultiplex
through one map. Requests fail fast when the socket is closed rather than
queueing forever — a hung promise is far harder to diagnose than an
immediate rejection. Cancelling a stream stops local delivery and sends
chat.cancel carrying the original request id."
```

---

### Task 9: Application shell — assemble, connect, and prove the spine

The integration task. Produces the mockup's layout with a live backend connection and a working echo round-trip.

**Files:**
- Create: `src/lib/store.ts`, `src/components/EmptyState.tsx`, `src/components/AppShell.tsx`
- Create: `src/components/app.css`
- Modify: `src/App.tsx`
- Test: `src/lib/store.test.ts`, `tests/e2e/shell.spec.ts`, `playwright.config.ts`

**Interfaces:**
- Consumes: `Transport` (Task 8), terminal primitives (Task 4), `window.citrine` (Task 7).
- Produces: `useAppStore` Zustand store with `{ connection, lines, addLine, setConnection }`; `type Line = { id: string; kind: 'input' | 'output' | 'error'; text: string }`.

- [ ] **Step 1: Write the failing store test**

`src/lib/store.test.ts`:

```ts
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- src/lib/store.test.ts`
Expected: FAIL — cannot resolve `./store`.

- [ ] **Step 3: Implement the store**

`src/lib/store.ts`:

```ts
import { create } from 'zustand'
import type { ConnectionState } from './transport'

export type LineKind = 'input' | 'output' | 'error'

export interface Line {
  id: string
  kind: LineKind
  text: string
}

interface AppState {
  connection: ConnectionState
  lines: Line[]
  addLine: (kind: LineKind, text: string) => void
  setConnection: (state: ConnectionState) => void
  reset: () => void
}

let lineCounter = 0

export const useAppStore = create<AppState>((set) => ({
  connection: 'idle',
  lines: [],
  addLine: (kind, text) =>
    set((s) => {
      lineCounter += 1
      return { lines: [...s.lines, { id: `line-${lineCounter}`, kind, text }] }
    }),
  setConnection: (connection) => set({ connection }),
  reset: () => set({ connection: 'idle', lines: [] }),
}))
```

- [ ] **Step 4: Run the store test to verify it passes**

Run: `npm test -- src/lib/store.test.ts`
Expected: PASS — 5 passed.

- [ ] **Step 5: Build the empty state**

`src/components/EmptyState.tsx`:

```tsx
import wordmark from '../assets/wordmark.png'

const SUGGESTIONS: Array<[string, string]> = [
  ['chat', 'Start an interactive AI chat'],
  ['code', 'Generate code from a description'],
  ['explain', 'Explain a block of code'],
  ['test', 'Generate tests for your code'],
  ['docs', 'Generate documentation'],
  ['init', 'Initialize a new project'],
]

/** The application's face on launch — the mockup's welcome screen. */
export function EmptyState() {
  return (
    <div className="ct-empty">
      <img className="ct-empty__wordmark" src={wordmark} alt="Citrine" />
      <p className="ct-empty__tagline">-- AI-Powered Development Assistant</p>
      <hr className="ct-empty__rule" />
      <p>
        Welcome to <span className="ct-accent">Citrine</span>! How can I help you build
        something amazing today?
      </p>
      <p>Try one of these commands to get started:</p>
      <ul className="ct-empty__list">
        {SUGGESTIONS.map(([name, description]) => (
          <li key={name}>
            <span className="ct-empty__star" aria-hidden="true">
              ✷
            </span>
            <span className="ct-empty__cmd">{name}</span>
            <span className="ct-empty__desc">{description}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

Add to `src/types/window.d.ts` so the PNG import type-checks:

```ts
declare module '*.png' {
  const src: string
  export default src
}
```

- [ ] **Step 6: Build the app shell**

`src/components/AppShell.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import { Frame } from './terminal/Frame'
import { Panel } from './terminal/Panel'
import { Prompt } from './terminal/Prompt'
import { StatusBar, type Segment } from './terminal/StatusBar'
import { EmptyState } from './EmptyState'
import { Transport } from '../lib/transport'
import { useAppStore } from '../lib/store'

const COMMANDS: Array<[string, string]> = [
  ['init', 'Initialize a new project'],
  ['chat', 'Start a new chat session'],
  ['code', 'Generate or refactor code'],
  ['explain', 'Explain code or concepts'],
  ['test', 'Generate unit tests'],
  ['docs', 'Generate documentation'],
  ['config', 'Manage configuration'],
  ['help', 'Show help information'],
]

const CONNECTION_LABEL: Record<string, [string, Segment['tone']]> = {
  idle: ['connecting…', 'dim'],
  connecting: ['connecting…', 'dim'],
  authenticating: ['authenticating…', 'dim'],
  open: ['connected', 'ok'],
  reconnecting: ['reconnecting…', 'err'],
  closed: ['disconnected', 'err'],
}

export function AppShell() {
  const transport = useRef<Transport | null>(null)
  const { connection, lines, addLine, setConnection } = useAppStore()

  useEffect(() => {
    const t = new Transport()
    transport.current = t
    t.onStateChange(setConnection)

    void (async () => {
      const info = await window.citrine.getBackendInfo()
      if (!info) {
        addLine('error', 'Backend is unavailable.')
        return
      }
      try {
        await t.connect(info)
      } catch (error) {
        addLine('error', error instanceof Error ? error.message : String(error))
      }
    })()

    return () => t.close()
  }, [addLine, setConnection])

  async function handleSubmit(value: string): Promise<void> {
    addLine('input', value)
    try {
      const result = await transport.current!.request<{ text: string }>('echo', {
        text: value,
      })
      addLine('output', result.text)
    } catch (error) {
      addLine('error', error instanceof Error ? error.message : String(error))
    }
  }

  const [label, tone] = CONNECTION_LABEL[connection] ?? ['unknown', 'dim']

  return (
    <div className="ct-app">
      <header className="ct-app__header">
        <span className="ct-app__logo">Citrine</span>
        <span className="ct-app__sub">AI Project</span>
      </header>

      <div className="ct-app__body">
        <aside className="ct-app__rail">
          <Panel title="Available Commands">
            <ul className="ct-cmdlist">
              {COMMANDS.map(([name, description]) => (
                <li key={name}>
                  <span className="ct-cmdlist__name">{name}</span>
                  <span className="ct-cmdlist__desc">{description}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Status">
            <div className="ct-status">
              <div>
                Connection: <span className="ct-accent">{label}</span>
              </div>
              <div>Session: local</div>
            </div>
          </Panel>
        </aside>

        <main className="ct-app__main">
          <Frame title={`Citrine v0.1.0 · shell & spine`}>
            <div className="ct-scrollback" data-testid="scrollback">
              {lines.length === 0 ? (
                <EmptyState />
              ) : (
                lines.map((line) => (
                  <div key={line.id} className="ct-line" data-kind={line.kind}>
                    {line.kind === 'input' ? `> ${line.text}` : line.text}
                  </div>
                ))
              )}
            </div>
          </Frame>
        </main>
      </div>

      <StatusBar
        segments={[
          { id: 'app', label: 'citrine', tone: 'accent' },
          { id: 'branch', label: ' main', tone: 'gold' },
        ]}
        right={[{ id: 'conn', label, tone }]}
      />
      <Prompt onSubmit={(v) => void handleSubmit(v)} disabled={connection !== 'open'} />
    </div>
  )
}
```

`src/App.tsx`:

```tsx
import { AppShell } from './components/AppShell'

export function App() {
  return (
    <>
      <div className="citrine-backdrop" aria-hidden="true" />
      <AppShell />
    </>
  )
}
```

- [ ] **Step 7: Style the shell**

`src/components/app.css`:

```css
.ct-app {
  display: grid;
  grid-template-rows: auto 1fr auto auto;
  height: 100%;
  gap: var(--sp-3);
  padding: var(--sp-4);
}

.ct-app__header {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
}
.ct-app__logo {
  font-size: 40px;
  font-weight: 700;
  color: var(--c-accent);
  text-shadow: var(--glow-accent);
  letter-spacing: -0.02em;
}
.ct-app__sub {
  color: var(--c-text);
  font-size: 16px;
  font-weight: 500;
}

.ct-app__body {
  display: grid;
  grid-template-columns: var(--rail-w) 1fr;
  gap: var(--sp-4);
  min-height: 0;
}
.ct-app__rail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  overflow: auto;
}
.ct-app__main {
  min-height: 0;
}

.ct-cmdlist,
.ct-empty__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.ct-cmdlist li {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: var(--sp-2);
}
.ct-cmdlist__name {
  color: var(--c-accent);
}
.ct-cmdlist__desc {
  color: var(--c-text);
}

.ct-status {
  color: var(--c-text);
}
.ct-accent {
  color: var(--c-accent);
}

.ct-scrollback {
  height: 100%;
  overflow-y: auto;
}
.ct-line[data-kind='input'] {
  color: var(--c-accent);
}
.ct-line[data-kind='output'] {
  color: var(--c-text);
}
.ct-line[data-kind='error'] {
  color: var(--c-err);
}

/* Empty state */
.ct-empty__wordmark {
  display: block;
  width: min(560px, 70%);
  height: auto;
  margin: var(--sp-5) 0 var(--sp-4);
}
.ct-empty__tagline {
  color: var(--c-accent);
  margin: 0 0 var(--sp-3);
}
.ct-empty__rule {
  border: none;
  border-top: var(--border-w) solid var(--c-border);
  margin: 0 0 var(--sp-4);
}
.ct-empty__list li {
  display: grid;
  grid-template-columns: 24px 90px 1fr;
  align-items: baseline;
}
.ct-empty__star {
  color: var(--c-accent);
}
.ct-empty__cmd {
  color: var(--c-accent);
}
.ct-empty__desc {
  color: var(--c-text);
}
```

Add `@import '../components/app.css';` to `src/styles/global.css`.

- [ ] **Step 8: Verify the shell manually**

Run: `npm run dev`
Expected: the mockup's layout — glowing "Citrine / AI Project" header, left rail with two inset-title panels, main frame with the extracted wordmark and suggestion list, powerline status bar reading `connected` in green, and a focused prompt. Type `hello` and press Enter: the line echoes back as `> hello` followed by `hello`.

Compare side by side against `Citrine.png` and note any divergence in the commit message.

- [ ] **Step 9: Add the end-to-end test**

```bash
npm install -D @playwright/test
```

`playwright.config.ts`:

```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
})
```

`tests/e2e/shell.spec.ts`:

```ts
import { _electron as electron, expect, test } from '@playwright/test'
import { resolve } from 'node:path'

const root = resolve(__dirname, '../..')

test('shell launches, connects, and echoes through the Python backend', async () => {
  const app = await electron.launch({ args: [resolve(root, 'out/main/main.js')], cwd: root })
  const window = await app.firstWindow()

  // The status bar reports a live backend connection.
  await expect(window.getByText('connected')).toBeVisible({ timeout: 30_000 })

  // The empty state shows before any input.
  await expect(window.getByTestId('scrollback')).toContainText('How can I help you')

  // A full round trip: renderer -> WebSocket -> Python -> back.
  await window.getByRole('textbox', { name: 'Citrine prompt' }).fill('spine check')
  await window.getByRole('textbox', { name: 'Citrine prompt' }).press('Enter')

  await expect(window.getByTestId('scrollback')).toContainText('> spine check')
  await expect(window.locator('[data-kind="output"]')).toHaveText('spine check')

  await app.close()
})
```

Add the script:

```bash
npm pkg set scripts.test:e2e="npm run build && playwright test"
```

- [ ] **Step 10: Run the end-to-end test**

Run: `npm run test:e2e`
Expected: PASS — 1 passed. This proves the whole spine end to end: Electron spawns Python, parses the handshake, the renderer authenticates over the socket, and a message round-trips.

- [ ] **Step 11: Run the full suite**

Run: `npm test && npm run typecheck && cd backend && uv run pytest -v`
Expected: all green. Frontend ~40 tests, backend ~50 tests.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: assemble the application shell with a live backend round-trip

Renders the mockup layout — header, rail panels with inset titles, main
frame, powerline status bar, focused prompt — and drives a real echo
through Electron, the authenticated socket, and Python.

The Playwright test covers the whole spine end to end, which is the only
check that would catch a handshake or auth regression."
```

---

## Self-Review

**Spec coverage.** Slice-1 requirements from the spec map to tasks as follows: process model and handshake → Task 7; wire protocol including declared-but-unimplemented tool frames → Task 5; repository layout → Tasks 1–9; palette, typography, glow, layout, empty state → Tasks 2, 3, 4, 9; theme engine → Task 2; secrets, provider interface, registry, onboarding, chat streaming, SQLite sessions → **deferred to Plan 2 by design**; sidecar-won't-start and socket-drop error handling → Tasks 7, 8; logging with redaction → Task 6; contract tests → Task 5; Vitest and Playwright → Tasks 2, 9; packaging → **deferred to Plan 2**.

Success criteria 1, 3 (as echo rather than tokens), 4, and 7 are proven by this plan. Criteria 2, 5, and 6 depend on the provider layer and belong to Plan 2.

**Known gap carried deliberately:** `chat.cancel` is implemented client-side in Task 8 but the backend has no handler for it until Plan 2 — the frame is sent and the server returns an "unknown method" error, which the transport ignores because the stream is already deleted locally. This is noted so Plan 2's server task does not treat it as a surprise.

**Type consistency check.** `BackendInfo` is `{ port: number; token: string }` in `electron/sidecar.ts`, `src/lib/transport.ts`, and `src/types/window.d.ts`. `ConnectionState` is defined once in `transport.ts` and imported by `store.ts`. `Segment` is defined in `StatusBar.tsx` and imported by `AppShell.tsx`. Method strings come from `METHODS` in `protocol.ts` on the client and `Method` in `protocol.py` on the server, with the same wire values. Error codes are asserted identical on both sides by the Task 5 contract tests.

**One implementation hazard flagged in place:** `_AnnouncingServer.startup` in Task 6 overrides a uvicorn method whose signature has shifted between versions. The note beneath that code block gives the one-line command to check the installed signature and states the contract that must hold regardless.

**Placeholder scan:** no `TBD`, `TODO`, "similar to Task N", or "add appropriate error handling" instructions remain. Every code step carries complete code; every command step states its expected output.

---

Plan complete and saved to `docs/superpowers/plans/2026-07-23-citrine-shell-spine.md`.
