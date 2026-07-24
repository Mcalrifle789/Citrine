# Citrine

A local-first personal AI terminal agent. Electron + React renderer over a
supervised Python sidecar, talking on an authenticated loopback WebSocket.

**Current state: slice 1 of 6 — the shell and the spine.** The window renders,
Electron spawns and supervises the Python backend, the renderer authenticates
over the socket, and messages round-trip. There is no AI provider wired up yet;
the prompt currently echoes through the backend to prove the path works.

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

Slice 1 deliberately excludes: API keys and the OS keychain, the provider layer
and its 24-entry registry, onboarding, real chat streaming, the `/` command
palette, Plan/Build mode switching, the `/theme` selector (the engine ships, one
theme), agents and agent windows, desktop control, and the Spotify/ElevenLabs/
SUNO/Deepgram integrations.

`.env.example` arrives with the secrets work in slice 2, since there are no keys
to document until the provider layer exists.

Specification and implementation plan live in `docs/superpowers/`.
