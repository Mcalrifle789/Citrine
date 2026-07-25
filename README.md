# Citrine

A local-first personal AI terminal agent. Electron + React renderer over a
supervised Python sidecar, talking on an authenticated loopback WebSocket.

**Current state: shell spine plus first setup/chat routing.** The window renders,
Electron spawns and supervises the Python backend, the renderer authenticates
over the socket, slash commands mutate local config, and normal chat messages
route to the active agent/provider when setup has been completed.

## Requirements

- **Node 24** and npm
- **Python 3.11**, managed by [`uv`](https://docs.astral.sh/uv/)

## Setup

```bash
git clone <this repo> citrine
cd citrine

npm install

cd backend
uv venv --python 3.11
uv sync --extra dev
cd ..
```

## Run

```bash
npm run dev
```

Electron builds the main, preload, and renderer bundles, starts the Vite dev
server, then spawns the Python sidecar. Backend logs appear in the terminal
prefixed with `[backend]`.

### Shortcuts

Two convenience launchers wrap `npm run dev`:

- **`citrine`** — type it in any terminal. `bin/citrine.cmd` is on the user
  PATH, so it works from any folder; it holds the terminal and streams logs,
  Ctrl+C to stop. (A terminal opened *before* the PATH entry was added won't
  see it — open a fresh one.)
- **Desktop shortcut** — double-click *Citrine* on the desktop.
  `bin/citrine-launch.vbs` starts the app with no visible terminal. Because
  there is no console to read, its output is redirected to
  `%LOCALAPPDATA%\Citrine\launch.log` so a failed launch is still diagnosable.
  Stop it by closing the app window.

Both still run the dev toolchain under the hood — conveniences, not a packaged
build. A real double-clickable installer with no Node/Python dependency comes
with the packaging work in a later slice.

The launcher scripts and `build/icon.ico` live in the repo; the PATH entry and
the desktop `.lnk` are machine-local, created once, not version controlled.
Recreate them from the repo root with:

```powershell
# citrine on PATH (User scope; appends only if absent)
$bin = "$PWD\bin"
$p = [Environment]::GetEnvironmentVariable('PATH','User')
if (($p -split ';') -notcontains $bin) {
  [Environment]::SetEnvironmentVariable('PATH', $p.TrimEnd(';') + ';' + $bin, 'User')
}

# desktop shortcut
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Citrine.lnk'))
$sc.TargetPath = 'wscript.exe'
$sc.Arguments = "`"$PWD\bin\citrine-launch.vbs`""
$sc.WorkingDirectory = "$PWD"
$sc.IconLocation = "$PWD\build\icon.ico"
$sc.Save()
```

## Terminal Setup

Run the terminal setup wizard with:

```powershell
citrine setup
```

The wizard walks through:

1. Username and password creation. On Windows, press `Tab` while typing the
   password to toggle visibility.
2. One or more model providers, including OpenRouter, Opencode, Kilo, LiteLLM,
   Google Gemini, OpenAI, Anthropic, and custom OpenAI-compatible providers.
3. One search provider, such as Firecrawl, DuckDuckGo, Parallel, Parallel Free,
   Brave, Google Search, Perplexity, Gemini Search, or custom search.
4. Optional audio/music plugins, including ElevenLabs, Deepgram, SUNO, Spotify,
   and custom MCP audio plugins.

Config is saved to Citrine's local config path. API keys are stored through the
OS keyring when available; otherwise Citrine warns and uses a local fallback.
The setup picker opens the available options immediately. Scroll, click, or use
the arrow keys; multi-select steps use checkboxes and single-select steps use a
focused list. The active option is cyan. If the terminal cannot run the rich
picker, Citrine falls back to typed selections. Nothing is written until the
final review screen is confirmed.

## Slash Commands

The shell currently supports 66 commands. The important active ones are:

- `/theme` — list six dark themes: `citrine`, `midnight`, `ember`, `matrix`,
  `violet`, and `mono`; use `/theme matrix` to switch.
- `/model` — show or switch the active agent model.
- `/session` — show or switch sessions.
- `/new` — create and switch to a new session.
- `/provider` — show or switch configured model providers.
- `/agent` — switch to an agent or create one using the current provider/model.

Normal chat messages now route through the configured agent provider. If the
provider reports quota, credit, billing, auth, or rate-limit problems, Citrine
shows that provider error instead of pretending the message succeeded.
The prompt footer shows the active provider, active model, and an estimated
remaining/total context-token meter. Typing `/provider`, `/model`, `/session`,
or `/agent` opens a clickable popup list instead of dumping choices into the
response area.

## Test

```bash
npm test          # renderer + electron unit tests (Vitest)
npm run typecheck # tsc --noEmit
npm run test:e2e  # builds, then drives the real app end to end (Playwright)

cd backend && uv run pytest   # backend tests
```

`npm run test:e2e` is the one that proves the whole spine: it launches Electron,
waits for a live backend connection, and round-trips a message through Python.

## How the pieces fit

Three processes:

- **Electron main** (`electron/main.ts`) owns windows and the sidecar. It
  generates a 32-byte token per launch, spawns Python with `--port 0`, and
  learns the real port from a single JSON handshake line on the child's stdout.
  If the backend dies it restarts with exponential backoff, five attempts.
- **Preload** (`electron/preload.ts`) exposes exactly one thing over the context
  bridge: `window.citrine.getBackendInfo()`. `contextIsolation` on,
  `nodeIntegration` off, `sandbox` on.
- **Python sidecar** (`backend/citrine/server.py`) is FastAPI + uvicorn bound to
  `127.0.0.1` only. A client's first frame must be a valid `auth` request or the
  socket closes with 4401; a bad `Origin` closes with 4403.

Every message uses one envelope — `{id, type, method, params}` — so streaming is
just a request that yields many events sharing its id. The protocol is
hand-maintained in `backend/citrine/protocol.py` and `src/lib/protocol.ts`, and
`tests/fixtures/protocol/` is validated from both sides to catch drift.

## Design notes

- **Every colour is a CSS custom property** in `src/styles/tokens.css`. A theme
  is that block redefined, so switching is one `data-theme` attribute swap and
  no component re-renders. Primary accent is cyan; gold is secondary only.
- **The nebula is procedural** — layered gradients plus a generated starfield
  tile, not a photograph. It recolours with the theme and costs kilobytes.
- **The wordmark is extracted from the logo art**; see `scripts/README.md` for
  how, and why the glow is rebuilt in CSS rather than baked in.

## Not here yet

Still pending: full in-app setup/onboarding, model-list fetching, real streaming
token output, the `/` command palette, Plan/Build execution semantics, agent
windows, desktop control, and live Spotify/ElevenLabs/SUNO/Deepgram workflows.
OpenAI-compatible chat calls are wired first; Anthropic/Gemini-native adapters
still need dedicated implementations.

Specification and implementation plan live in `docs/superpowers/`.
