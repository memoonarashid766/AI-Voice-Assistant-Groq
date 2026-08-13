# AI Voice Assistant — Vercel Edition

A voice-first assistant (Groq-powered) that runs entirely as a static
frontend + two small Python serverless functions, deployable on
Vercel. No Streamlit, no server-side microphone, no audio player UI —
the assistant listens and speaks automatically, like ChatGPT Voice
Mode.

## What changed from the Streamlit version, and why

Streamlit itself can't run as a normal Vercel app (it needs a
long-lived Python server process; Vercel runs short-lived, stateless
functions). So the project was split along the line that was already
implicit in the previous version:

| Concern | Old (Streamlit) | New (Vercel) |
|---|---|---|
| UI | Streamlit widgets | Plain `index.html` / `style.css` / `script.js` — same colors, layout, and section labels as before |
| Microphone | `st.audio_input` (browser mic, sent to Python for transcription) | Browser's native **Web Speech API** — transcribes directly in the browser, nothing uploaded for STT |
| Groq calls | `groq_api.py`, called in-process | `api/chat.py` (called from `api/index.py`) — same Groq logic, moved server-side where the key is safe |
| Text-to-speech | `text_to_speech.py` (gTTS), returned to `st.audio()` | `api/speak.py` (called from `api/index.py`), returning raw mp3 bytes — the browser plays them with a plain in-memory `Audio` object, no `<audio>` controls anywhere |
| Playback | `st.audio()` player with visible controls | Automatic, invisible playback via JS — **no Play button** |
| Config | `.env` / `st.secrets` | `.env` (local) / Vercel **Environment Variables** (deployed) |

`config.py`, `groq_api.py`, `speech_to_text.py`, `text_to_speech.py`,
and `main.py` from the Streamlit version are not used by this
structure — their logic was carried over (largely unchanged) into
`api/_common.py`, `api/chat.py`, and `api/speak.py`, and speech-to-text
moved into the browser entirely (see below), which is why there's no
`speech_to_text.py` equivalent on the server anymore.

## File structure

```
ai-voice-assistant-vercel/
├── index.html            # Frontend markup (same sections/labels as before)
├── style.css              # Same color palette/box styles as the old app
├── script.js               # All mic + playback + API-calling logic
├── api/
│   ├── index.py            # THE Vercel entrypoint (Flask app) — routes /api/chat and /api/speak
│   ├── chat.py             # Chat logic, called from index.py -> Groq reply (text)
│   ├── speak.py            # Speech logic, called from index.py -> mp3 audio bytes
│   └── _common.py         # Shared Groq + gTTS logic (not a route itself)
├── requirements.txt       # Python deps for the app above
├── .env.example
├── .gitignore
└── README.md
```

**Why `api/index.py` exists:** Vercel's current Python runtime loads
exactly one application per project, auto-detected from a default
location — `app.py`, `index.py`, `server.py`, `main.py`, `wsgi.py`, or
`asgi.py`, at the project root or inside `src/`, `app/`, or `api/`. It
does not treat every file under `api/` as its own independent
function. `api/index.py` is a Flask app in one of those default
locations, so Vercel auto-detects it with **no `vercel.json` and no
`pyproject.toml`** — `chat.py` and `speak.py` keep their names and
locations, but now expose plain functions that `index.py` calls and
routes to `/api/chat` / `/api/speak`, instead of being their own
entrypoints.

(No `package.json` either — there's no JS build step; the frontend is
plain static files.)

## Every file that's new

All of the above — this is a new project structure, so everything in
it is new relative to the Streamlit version. Nothing from the old repo
is reused as-is; the Groq/gTTS *logic* was carried over into
`api/_common.py`.

## How automatic voice playback works

1. Clicking **Start Listening** (or **Send**) first plays a silent,
   empty `Audio` object synchronously, inside that same click handler.
   Browsers require a user gesture before they'll allow a page to
   autoplay audio with sound later in that page's lifetime — this
   "spends" that gesture immediately, so it's already been granted by
   the time the real response audio is ready a few seconds later.
2. The Web Speech API transcribes your voice locally in the browser
   (`Listening...` → `Recognizing speech...`).
3. The transcript is POSTed to `/api/chat`, which calls Groq
   server-side (the API key never leaves the server) and returns reply
   text (`Processing...`).
4. The reply text is POSTed to `/api/speak`, which returns raw MP3
   bytes (not JSON) using gTTS.
5. The browser wraps those bytes in a `Blob`, creates an in-memory
   `Audio` object from it, and calls `.play()` — no `<audio>` element
   with visible controls is ever added to the page (`Speaking...`).
6. On the `ended` event, status returns to `Ready`.

If a browser still blocks autoplay despite step 1 (can happen with
strict privacy settings), the response text says so plainly and asks
you to click Start Listening once more — it never fails silently.

**Stop** is only enabled while the assistant is speaking, and calls
`audio.pause()` directly on the in-memory `Audio` object — a real,
instant stop, since playback is entirely client-side now (better than
the old Streamlit version's `st.audio()`, which could only remove the
player and wait for a rerun).

**Browser support**: the Web Speech API (used for microphone
recognition) works in Chrome, Edge, and Safari, but not Firefox — the
app detects this and shows a banner + falls back to typed input if
it's unavailable. Text-to-speech playback (`/api/speak` + `Audio`)
works in all modern browsers.

## Run it locally

```bash
npm install -g vercel        # one-time
cd ai-voice-assistant-vercel
cp .env.example .env         # then fill in GROQ_API_KEY
vercel dev
```

Open the printed `http://localhost:3000` — `vercel dev` runs the
static frontend and both Python functions together, matching
production. (A plain Python HTTP server won't run `api/*.py` the way
Vercel does — use `vercel dev` for local testing of this structure.)

## Deploy to Vercel

```bash
cd ai-voice-assistant-vercel
vercel login          # first time only
vercel                # deploy a preview
vercel --prod          # deploy to production
```

Or via the dashboard: push this folder to a GitHub repo, then
**New Project** on vercel.com → import the repo → deploy. Vercel
detects `requirements.txt` and `api/*.py` automatically; no framework
preset or build command is needed.

### Environment variables to set in Vercel

Project → **Settings → Environment Variables**:

| Name | Required | Example |
|---|---|---|
| `GROQ_API_KEY` | Yes | `gsk_...` |
| `GROQ_MODEL` | No (defaults to `openai/gpt-oss-120b`) | `openai/gpt-oss-120b` |
| `GROQ_MAX_TOKENS` | No (defaults to `350`) | `350` |
| `GROQ_TEMPERATURE` | No (defaults to `0.7`) | `0.7` |
| `TTS_LANGUAGE` | No (defaults to `en`) | `en` |

None of these are ever sent to the browser — `api/chat.py` and
`api/speak.py` are the only code that reads them.

## Microphone permissions

The browser will prompt for microphone access the first time you
click **Start Listening** (this requires HTTPS — automatic on your
`*.vercel.app` domain, and on `localhost` during `vercel dev`). Allow
it once per browser/site; there's nothing to configure in the app
itself, since the browser — not the server — owns the microphone.

## Final checklist

- [x] Groq API key only read server-side (`api/_common.py`, via env vars) — never sent to the frontend.
- [x] No `<audio controls>`, no Play/Replay button, anywhere — including conversation history.
- [x] Voice plays automatically after both voice and typed turns.
- [x] Stop button truly pauses playback instantly.
- [x] Microphone accessed only via the browser (Web Speech API); the server never expects one.
- [x] Same visual design/sections/colors as the original app, in a plain static page.
