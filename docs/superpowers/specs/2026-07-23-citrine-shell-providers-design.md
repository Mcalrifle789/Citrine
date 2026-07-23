# Citrine — Slice 1+2: Shell & Providers

**Date:** 2026-07-23
**Status:** Approved
**Scope:** Desktop shell, Python sidecar, transport, visual system, onboarding, secrets, multi-provider streaming chat

---

## 1. Context

Citrine is a local-first personal AI agent desktop application with a terminal aesthetic. The
full product vision spans roughly ten independent subsystems. This spec covers only the first
two slices of a six-slice decomposition.

### 1.1 Full decomposition (agreed)

| Slice | Name | Contents |
|-------|------|----------|
| **1** | **Shell & Spine** | Desktop app, Python sidecar, transport, visual system, config, secrets |
| **2** | **Provider Layer** | Onboarding wizard, key management, multi-provider streaming chat, model switching |
| 3 | Command System | `/` palette, command registry, Plan/Build toggle, `/theme` selector |
| 4 | Tools & Automation | Desktop control, file system, screenshots, confirmation gate |
| 5 | Agents | `/agent` create/switch/manage, dedicated agent windows |
| 6 | Media Integrations | Spotify Connect, ElevenLabs, SUNO, Deepgram |

Slices 1 and 2 are specced and built together because slice 1 alone produces a window that
cannot do anything. Together they produce an application that is genuinely usable: a terminal
you can hold a real streaming conversation in.

Each later slice gets its own spec → plan → implementation cycle.

### 1.2 Reference material

Two images at `C:\Users\hextu\OneDrive\Documents\Terminal GUIs\Citrine`:

- `Citrine logo.png` — wordmark on a nebula field. Source for the app icon, splash screen,
  and (after background extraction) the empty-state wordmark.
- `Citrine.png` — the GUI mockup. **The authoritative visual reference.** Layout, palette,
  and component treatment in this spec are read directly off it.

---

## 2. Decisions

Each decision below was made explicitly, with alternatives considered and rejected.

### 2.1 Electron over Tauri

**Decision:** Electron.

All heavy lifting — AI orchestration, tool use, desktop control — is Python by design. Tauri
would introduce Rust as a third language reduced to window management and an IPC pipe: a full
toolchain, build story, and debugging surface for near-zero payoff.

Supporting reasons: the mockup depends on layered glow, transparency, and blend modes, and
Electron's bundled Chromium renders these identically on every platform, where Tauri's OS
webview degrades badly under WebKitGTK on Linux. Multi-window agent spawning (slice 5) is
well-trodden in Electron, and bundling a Python sidecar alongside is simpler.

**Accepted cost:** ~150–200 MB installed and higher idle RAM than Tauri's ~10 MB. Acceptable
for a personal desktop application.

### 2.2 Styled DOM over terminal emulator

**Decision:** Styled DOM (React components), not xterm.js.

Citrine is not a shell; it is an AI agent with a terminal's visual language. The required
feature set — searchable command palette, clickable mode indicator, theme dropdown, playlist
browsing, audio scrubbers — are GUI widgets. Against a canvas-based emulator built to drive a
PTY, each becomes a fight with the medium, and the mockup's visual effects become a rendering
project instead of CSS.

Styled DOM provides text selection, clickable links, accessibility, CSS effects, and mouse plus
keyboard support for free. The terminal feel comes from monospace type, box-drawing borders, a
blinking caret, and palette discipline.

**Escape hatch:** when Build Mode runs real shell commands and requires true ANSI handling,
xterm.js is embedded in *that pane only*. Not built now.

### 2.3 Own Provider interface, LiteLLM behind it

**Decision:** A narrow in-house `Provider` interface implemented once, backed by the LiteLLM
Python SDK.

The brief names 23 providers plus a Custom option — 24 registry entries in total (§3.5).
LiteLLM (BerriAI, MIT, actively maintained) natively covers **18 of those 24** with uniform
streaming via `stream=True`. The remaining six are not gaps: Kilo, Opencode, CostRouter, a
LiteLLM proxy, and Custom Provider are all OpenAI-compatible endpoints served by `custom_openai`
with a `base_url`; SUNO is music generation rather than chat, requires a specialized client, and
belongs to slice 6.

Wrapping it rather than using it directly costs approximately one file and ensures LiteLLM's
types never leak past that boundary. If it becomes a liability — install bloat, a bug, version
churn — the implementation is swapped for `httpx` adapters without touching UI, session, or
agent code.

**Rejected:** using LiteLLM directly (its types spread through the codebase); hand-rolled
adapters only (leanest bundle, but days of extra work and ongoing maintenance as APIs drift).

**Requirements attached to this decision:**

- The interface must support streaming as a first-class concern, not an afterthought.
- Model lists must auto-populate in the UI; switching provider or model must not require a restart.
- Dependency footprint must stay reasonable — Python is bundled inside Electron.
- Non-chat services (SUNO, ElevenLabs, Deepgram) get separate specialized clients, not this interface.

### 2.4 WebSocket transport on 127.0.0.1

**Decision:** Python runs FastAPI + uvicorn bound to `127.0.0.1` on an ephemeral port. Electron
spawns and supervises it as a child process.

The deciding factor is slice 5. Each agent window is its own `BrowserWindow` needing its own
live conversation with Python; with WebSockets each simply opens its own connection. The
alternative, stdio JSON-RPC, leaves only Electron's main process holding the pipe, so every
token of every stream must be relayed main→renderer for every window — a hand-written message
router that gets subtly wrong under concurrency.

Secondary benefit: the Python backend can be run standalone and driven by any WebSocket client
during development, independent of Electron.

**Accepted cost and required mitigations.** A localhost port is reachable by any local process,
including a malicious `postinstall` script. Since this backend gains full desktop control in
slice 4, the following are **requirements, not recommendations**:

- Bind `127.0.0.1` only. Never `0.0.0.0`.
- Ephemeral port via bind-to-0; the OS selects a free port.
- Per-launch random 32-byte token, required in the first frame.
- `Origin` validated against the application's own origin.
- Connection closed with code `4401` on any auth failure, before processing any other message.

**Requirements attached to this decision:**

- Sidecar spawning must be reliable on Windows, macOS, and Linux.
- The communication layer must have thorough logging in development.

### 2.5 Python `keyring` for secrets

**Decision:** API keys are stored by Python via the `keyring` library into the OS-native
credential store — Windows Credential Manager, macOS Keychain, Secret Service on Linux.

Principle: *the process that uses the keys is the only process that stores them.* Python makes
every API call, so Python owns the secrets. During onboarding a key travels renderer→Python
exactly once over the authenticated socket, is handed to the OS store, and is never readable
back by the UI, which sees only a masked fingerprint (`sk-…4f2a`) and a validation status.
Electron never persists a key. A compromised renderer has nothing to steal.

**Rejected:** Electron `safeStorage` (inverts ownership; keys round-trip through the renderer
every launch). `keytar` is archived and not an option.

**Requirements attached to this decision:**

- Environment variable overrides for development and advanced users: `CITRINE_<PROVIDER>_API_KEY`.
- A clear `.env.example` documenting those overrides — never a store for real keys.
- Fallback for environments without an OS keyring: encrypted file under `~/.citrine/`, keyed to
  machine identity, with an explicit and persistent warning. Never a silent downgrade.
- Onboarding must state clearly, per key, where that key is being stored.

### 2.6 Renderer stack

**Decision:** React + Vite + TypeScript, with Zustand for state.

Low-stakes and reversible, but React has the deepest ecosystem for what later slices need
(xterm.js panes, virtualized scrollback, multi-window state). Zustand over Redux because the
state is small and the boilerplate is not worth it.

### 2.7 Persistence

- **Chat history:** SQLite via Python's stdlib `sqlite3`. No dependency added. JSON files would
  work today and become a regret the first time history needs searching.
- **Configuration:** plain JSON at `~/.citrine/config.json`. Hand-editable by design.
- **Agent files:** `~/Documents/Citrine/Agents/`, resolved cross-platform. (Slice 5.)
- **Logs:** `~/.citrine/logs/`, structured JSON, rotating.

---

## 3. Architecture

### 3.1 Process model

Three processes.

**Electron main** owns window lifecycle and the Python sidecar. On launch it:

1. Generates a 32-byte cryptographically random token.
2. Spawns Python with the token in the environment and `--port 0`.
3. Reads sidecar stdout until it observes a single JSON handshake line:
   `{"event":"ready","port":54321}`.
4. Retains `{port, token}` and supervises the child.

Binding port 0 lets the OS assign a free port, eliminating the "port already in use" failure
class. If Python dies, main restarts it with exponential backoff and notifies every open window
to display a reconnecting state rather than hanging silently.

**Preload** exposes exactly one API over `contextBridge`: `citrine.getBackendInfo()` returning
`{port, token}`. Hardened settings are mandatory:

```
contextIsolation: true
nodeIntegration:  false
sandbox:          true
```

The renderer has no Node access.

**Python sidecar** is FastAPI + uvicorn. A client's first frame must be
`{"type":"auth","token":"…"}`. Anything else, or a bad token, closes the socket with `4401`
before any other message is processed.

### 3.2 Wire protocol

A single envelope, newline-delimited JSON, so every message is self-describing and the transport
layer demuxes without special cases:

```jsonc
{
  "id": "<uuid>",
  "type": "request" | "response" | "event" | "error",
  "method": "chat.send",
  "params": { }
}
```

Streaming is a `request` that yields many `event` frames sharing the request's `id`:

- `chat.delta` — incremental token content
- `chat.done` — terminal success, carries usage totals
- `chat.error` — terminal failure, carries the taxonomy code and provider message

**Forward compatibility.** The `request` type is bidirectional. In slice 4, tool confirmation
becomes a server→client `request` that the client answers with a `response` — no protocol
migration. The tool-call and confirmation frame shapes are **defined in `protocol.py` /
`protocol.ts` in this slice but not implemented.**

**Methods in this slice:**

| Method | Direction | Purpose |
|--------|-----------|---------|
| `auth` | C→S | First frame. Token validation. |
| `providers.list` | C→S | Registry of available providers and their credential requirements |
| `providers.validate` | C→S | Live credential validation; returns provider's real error on failure |
| `providers.save` | C→S | Persist credentials to the OS credential store |
| `providers.status` | C→S | Configured providers with masked fingerprints |
| `models.list` | C→S | Auto-populated model list for a configured provider |
| `chat.send` | C→S | Start a streaming completion |
| `chat.cancel` | C→S | Abort an in-flight stream by request id |
| `session.list` / `session.load` | C→S | Chat history |

Every frame is logged in development with direction, method, and id.

### 3.3 Repository layout

```
~/citrine/                 repository root
├── electron/
│   ├── main.ts            window lifecycle, app events
│   ├── sidecar.ts         spawn, handshake, supervise, backoff restart
│   ├── windows.ts         window factory (main; agent windows in slice 5)
│   └── preload.ts         contextBridge surface
├── src/                   renderer — React + Vite + TypeScript
│   ├── components/
│   │   ├── terminal/      Panel · Frame · StatusBar · Prompt · Scrollback
│   │   ├── onboarding/    Splash · ProviderPicker · CredentialForm · ModelPicker
│   │   └── chat/          MessageBlock · ErrorBlock · StreamingCaret
│   ├── lib/
│   │   ├── transport.ts   WS client: auth, reconnect, request/event demux, cancel
│   │   ├── protocol.ts    shared types — mirrors backend/citrine/protocol.py
│   │   └── store.ts       Zustand
│   ├── themes/            *.css — custom-property token sets
│   ├── assets/            fonts, logo, extracted wordmark, nebula, lattice
│   └── styles/
├── backend/
│   ├── citrine/
│   │   ├── server.py      FastAPI app, ws endpoint, auth gate
│   │   ├── protocol.py    pydantic models
│   │   ├── providers/
│   │   │   ├── base.py            Provider interface
│   │   │   ├── litellm_provider.py
│   │   │   └── registry.py        provider descriptors
│   │   ├── secrets.py     keyring + encrypted-file fallback
│   │   ├── config.py      settings
│   │   ├── sessions.py    SQLite chat history
│   │   └── logging.py     structured logs, key redaction
│   ├── tests/
│   └── pyproject.toml
├── docs/
├── .env.example
└── package.json
```

Paths above are relative to the repository root — see §10.

### 3.4 Provider interface

```python
class Provider(Protocol):
    async def stream_chat(
        self,
        messages: list[Message],
        model: str,
        **opts: Any,
    ) -> AsyncIterator[Chunk]: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def validate_key(self) -> ValidationResult: ...
```

`ValidationResult` carries the provider's real error text, not a boolean.

### 3.5 Provider registry

Each of the 24 registry entries is a descriptor declaring its LiteLLM prefix, its capability class, and
**its required credential fields**. Not every provider authenticates with a single API key, and
the onboarding credential screen renders fields from the descriptor rather than assuming one.

| Provider | LiteLLM prefix | Credential fields | Class |
|----------|----------------|-------------------|-------|
| OpenAI | `openai/` | api_key | chat |
| Anthropic | `anthropic/` | api_key | chat |
| Mistral AI | `mistral/` | api_key | chat |
| Deepseek | `deepseek/` | api_key | chat |
| Google AI Studio | `gemini/` | api_key | chat |
| OpenRouter | `openrouter/` | api_key | gateway |
| Groq | `groq/` | api_key | chat |
| Together AI | `together_ai/` | api_key | chat |
| Fireworks AI | `fireworks_ai/` | api_key | chat |
| DeepInfra | `deepinfra/` | api_key | chat |
| Novita | `novita/` | api_key | chat |
| NVIDIA NIM | `nvidia_nim/` | api_key | chat |
| Cerebras | `cerebras/` | api_key | chat |
| Replicate | `replicate/` | api_key | chat |
| Amazon Bedrock | `bedrock/` | access_key_id, secret_access_key, region | cloud |
| Azure OpenAI | `azure/` | api_key, endpoint, deployment, api_version | cloud |
| Kilo | `custom_openai` | api_key, base_url | gateway |
| Opencode | `custom_openai` | api_key, base_url | gateway |
| CostRouter | `custom_openai` | api_key, base_url | gateway |
| LiteLLM (proxy) | `custom_openai` | api_key, base_url | gateway |
| Custom Provider | `custom_openai` | api_key, base_url | gateway |
| ElevenLabs | `elevenlabs/` | api_key | audio |
| Deepgram | `deepgram/` | api_key | audio |
| SUNO | *(specialized client)* | api_key | audio |

**Only `chat`, `gateway`, and `cloud` class providers can be selected as the chat provider.**
Audio-class providers appear in the registry but are inert until slice 6.

---

## 4. Visual system

### 4.1 Palette

Read from the mockup. **The primary accent is cyan, not gold** — despite the name. Gold is
secondary, used for the git branch segment, the tools indicator, and warnings.

```css
--c-bg          #05030F   /* near-black indigo, behind the nebula      */
--c-panel       rgba(10,8,24,0.72)  /* translucent; nebula reads through */
--c-border      #24405E   /* dim slate-cyan, 1px, never thicker        */
--c-accent      #5CE1FF   /* headings, command names, caret, active    */
--c-accent-glow #7DF9FF   /* glow halo only                            */
--c-gold        #E8A33D   /* git branch, tools, warnings               */
--c-text        #C8D6E5   /* body — soft blue-white, never pure #FFF   */
--c-text-dim    #6B7C93   /* descriptions, metadata                    */
--c-ok          #5FD98A   /* status dots, validated keys               */
--c-err         #FF5C8A   /* errors — magenta-red, in the nebula family*/
```

Every value is a CSS custom property. **No component hardcodes a color.** A theme is this token
block redefined in one file; `/theme` (slice 3) becomes a class swap on `<html>` — instant, no
reload, no re-render. The engine ships in this slice with one theme; the selector does not.

### 4.2 Typography and glow

**JetBrains Mono**, bundled as a font file rather than referenced remotely — a webfont failing
to load would collapse the aesthetic to Courier.

The header wordmark is the logo asset, not text; its rounded geometric face is part of the
logo's identity.

Glow is layered `text-shadow` at two radii — a tight 8px and a diffuse 20px, both low alpha.
**Applied only to headings, the wordmark, the caret, and active states.** Never to body text or
scrollback: it harms legibility at small sizes, and text-shadow across thousands of scrolling
nodes is a measurable frame-rate cost.

### 4.3 Layout

CSS Grid, four rows: logo header, body, status bar, prompt. The body splits `320px │ 1fr`.

The application sits inside a 1px cyan frame with the version string inset into its top border.
That inset-title treatment — a positioned label with panel-colored background sitting on the
border line — is the signature motif, reused for every panel in the left rail.

**No rounded corners. No drop shadows. No material elevation.** Depth comes from translucency
over the nebula and from glow.

Background composition: static nebula image, plus a low-opacity quatrefoil lattice SVG overlay,
with panel translucency above. Static assets — nothing animated.

### 4.4 Empty state

The empty state is the mockup's welcome screen and ships in slice 1, because it is the
application's face.

**Wordmark treatment.** The source logo PNG has a nebula baked into it; compositing it over the
app's own nebula would produce a visible seam and two competing starfields. The glowing
"Citrine / AI Project" wordmark is therefore **extracted to a transparent-background PNG** (and
an SVG if the letterforms trace cleanly) and rendered large and centered, with the app's nebula
showing through. The original full-bleed image remains the splash screen and app icon, where its
background is an asset rather than a problem.

**Fallback:** if transparent extraction produces rough edges on the soft glow, the ASCII
block-letter wordmark from the mockup is used instead.

---

## 5. Onboarding

Four screens. Keyboard-first (`↑↓`/`jk` navigate, `/` search, `Enter` select, `Esc` back), with
full mouse support.

1. **Splash** — logo, tagline, `Press any key`.
2. **Provider** — all 24, grouped Chat / Gateway / Cloud / Audio, type-to-filter. Audio-class
   entries are visibly disabled with a "coming in a later release" note.
3. **Credentials** — fields rendered from the registry descriptor (§3.5), masked. Below them,
   stated plainly: *"Stored in Windows Credential Manager. Citrine never writes your key to disk
   in plaintext."* A **Validate** action calls `validate_key()` live, showing a spinner, then a
   green check or **the provider's actual error text**. Distinguishing a 401 from a network
   failure from a disabled account is the difference between a ten-second fix and giving up.
4. **Model** — auto-populated from `list_models()`, searchable, sensible default preselected.

Then directly into the main UI. Adding further providers later reuses screens 2–4.

If the OS keyring is unavailable, a persistent amber banner names the fallback and its weaker
guarantees.

---

## 6. Chat experience

User input echoes into the scrollback as `> text` in the accent color. Assistant output streams
token-by-token with a block caret `▊` riding the end of the text, removed on `chat.done`.

Markdown receives light treatment only: code blocks in a bordered monospace well, inline code
tinted, bold and lists honored. Nothing more ornate.

Behaviors that make it feel terminal-native rather than like a web chat:

- Auto-scroll that **stops** the moment the user scrolls up, and resumes on return to the bottom.
- `↑`/`↓` walk input history.
- `Shift+Enter` inserts a newline.
- `Ctrl+C` cancels an in-flight stream via `chat.cancel`, **aborting the provider request
  server-side**, not merely hiding output.
- The prompt refocuses on any keystroke; clicking into it is never required.
- Slash commands colorize as typed, before the palette exists.

The status bar carries live model, provider, context tokens, connection state, and clock. A
dropped socket becomes visible there immediately rather than presenting as a stream that
mysteriously stopped.

The Plan/Build mode indicator renders showing `PLAN`. **The toggle is deferred to slice 3** —
Build Mode has no meaning until tools exist.

---

## 7. Error handling

Five failure domains, each with defined behavior.

**Sidecar will not start** (missing Python, bad import, bind failure) — Electron presents a
diagnostic window containing captured stderr. Never a blank window; a silent failure here is the
most likely way to waste an hour.

**Sidecar crashes** — automatic restart with exponential backoff, five attempts, then a manual
*Restart backend* action in the status bar.

**Socket drops** — status bar turns red and reads reconnecting; backoff reconnect; queued
requests fail fast rather than hanging; any in-flight stream is marked interrupted in the
scrollback rather than simply stopping mid-sentence.

**Provider errors** map to a fixed taxonomy — `auth`, `rate_limit`, `quota`, `network`,
`model_not_found`, `context_length`, `server` — each rendering as a distinct magenta error block
carrying the provider's real message plus a correlation id matching the log file. Tracebacks go
to logs, never to the UI.

**Keyring unavailable** — amber banner naming the fallback. Never a silent downgrade.

**Cancellation is not an error.** It is a distinct terminal state, so `Ctrl+C` never presents as
a failure.

**Logging.** Structured JSON under `~/.citrine/logs/`, rotating. Every protocol frame logged in
development. **Key material is redacted at the logger**, not at call sites — a rule enforced in
one place cannot be forgotten in fifty.

---

## 8. Testing

Test-first for the three areas where bugs are expensive and hard to reproduce: transport,
provider interface, and secrets.

**Python (pytest).** The `Provider` interface is verified against a `FakeProvider`. The LiteLLM
adapter runs against recorded responses — **CI never touches a live API**. `secrets.py` runs
against a fake keyring backend, including the fallback path.

**Contract tests.** A shared JSON fixture set that both the pydantic models and the TypeScript
types validate against. The protocol is hand-maintained in two languages, and this is the only
mechanism that catches drift before it becomes a runtime mystery.

**Frontend (Vitest).** Logic that is easy to get subtly wrong: reconnect behavior,
response/event demuxing, cancellation, sticky-scroll math.

**E2E (Playwright driving Electron).** One happy path: launch, onboard with a stub provider,
send a message, assert streamed tokens render. One path, not a suite.

---

## 9. Boundaries

### 9.1 Explicitly not in this slice

- The `/` command palette and the 66 skills
- The Plan/Build **toggle** (indicator renders; toggle deferred)
- The `/theme` **selector** (engine ships; one theme)
- Agents and agent windows
- All desktop control and tools
- Spotify Connect, ElevenLabs, SUNO, Deepgram
- Packaging and installers — tracked as the final task of this slice, not a prerequisite

### 9.2 Success criteria

1. Fresh clone → documented commands → application launches on Windows 11.
2. Onboarding accepts a real key, validates it live, stores it in Windows Credential Manager
   (verifiable in the OS UI), and the key appears in **no file on disk**.
3. A message streams tokens into the scrollback.
4. Killing the Python process from Task Manager degrades visibly and self-recovers, without
   restarting Electron.
5. Switching provider or model mid-session works with no restart.
6. `Ctrl+C` mid-stream halts output and preserves the partial response in the scrollback.
7. The UI holds up in side-by-side comparison against `Citrine.png`.

### 9.3 Risks

| Risk | Assessment |
|------|------------|
| PyInstaller packaging | Highest uncertainty. Antivirus false positives on Windows, code signing on macOS. Deliberately deferred; development runs Python from a local venv. |
| LiteLLM dependency weight | May bite at bundle time. The interface boundary (§2.3) is precisely what makes replacement survivable. |
| Protocol drift TS↔Python | Most likely source of silent bugs. Mitigated by contract fixtures (§8). |
| Transparent logo extraction | Soft glow edges may not extract cleanly. ASCII wordmark is the defined fallback (§4.4). |

---

## 10. Resolved items

**Repository location — resolved 2026-07-23.** Citrine lives in its own dedicated repository at
`C:\Users\hextu\citrine` (`~/citrine` on other systems), deliberately *not* inside the OpenClaw
agent workspace. This spec is the repository's initial commit. The project root described in
§3.3 is therefore the repository root itself — paths in that layout are relative to
`~/citrine`, with no nested `citrine/` directory.

**Bedrock and Azure credentials — confirmed 2026-07-23.** The onboarding credential screen
renders fields from the provider descriptor (§3.5) rather than assuming a single API key.
Bedrock requires access key, secret, and region; Azure requires key, endpoint, deployment, and
API version.

---

## 11. Decision log

| # | Decision | Alternatives rejected |
|---|----------|----------------------|
| 1 | Decompose into 6 slices; spec 1+2 together | Single spec for everything; shell-only first |
| 2 | Electron | Tauri |
| 3 | Styled DOM | xterm.js primary; hybrid from day one |
| 4 | Own `Provider` interface, LiteLLM behind it | LiteLLM direct; hand-rolled adapters only |
| 5 | WebSocket on 127.0.0.1, token auth | stdio JSON-RPC; REST + SSE |
| 6 | Python `keyring` → OS credential store | Electron `safeStorage`; encrypted file + master password |
| 7 | React + Vite + Zustand | — |
| 8 | SQLite for history, JSON for config | JSON for both |
