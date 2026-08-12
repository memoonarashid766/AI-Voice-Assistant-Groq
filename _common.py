"""
api/_common.py
---------------
Shared backend logic for the Vercel serverless functions in this
folder (chat.py, speak.py). This is the Vercel-adapted equivalent of
the original project's config.py + groq_api.py + text_to_speech.py,
consolidated because Vercel Python functions are independent,
stateless processes per request — there's no long-lived Streamlit
session to hold shared state across files, so the small amount of
shared setup (env vars, the Groq call, the gTTS call) lives here and
each endpoint file imports what it needs.

Not a route itself — files in api/ only become HTTP endpoints when
they define `handler` (BaseHTTPRequestHandler) or `app` (WSGI/ASGI) at
module scope, which this file deliberately doesn't, so Vercel leaves
it alone as a plain shared module.

Configuration:
  Comes from plain environment variables — set in Vercel's
  Settings -> Environment Variables when deployed, or in a local
  ".env" file (loaded via python-dotenv) for `vercel dev` / local
  testing. The GROQ_API_KEY never reaches the browser: only these
  server-side functions ever read it.
"""

import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_MAX_TOKENS = int(os.environ.get("GROQ_MAX_TOKENS", "350"))
GROQ_TEMPERATURE = float(os.environ.get("GROQ_TEMPERATURE", "0.7"))
TTS_LANGUAGE = os.environ.get("TTS_LANGUAGE", "en")

# Kept identical to the original project's exit-word list, and to its
# voice-friendly system prompt (unchanged).
EXIT_COMMANDS = {"exit", "stop", "quit", "goodbye", "bye"}
SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Give clear, concise and "
    "natural answers. Avoid unnecessary long explanations unless the "
    "user asks for detail. Avoid lists, markdown, or special "
    "formatting since your answer will be read aloud."
)

# Keep only the most recent N messages of context the FRONTEND sends
# back with each request (see chat.py) — same reasoning as the
# original MAX_HISTORY_MESSAGES: bounded latency/cost regardless of
# how long the conversation runs.
MAX_HISTORY_MESSAGES = 20


class GroqAPIError(Exception):
    """Raised for any Groq API failure with a human-readable message."""
    pass


class TextToSpeechError(Exception):
    """Raised for any text-to-speech failure with a human-readable message."""
    pass


def is_exit_command(text: str) -> bool:
    """Checks whether the given text matches one of the exit commands."""
    if not text:
        return False
    return text.strip().lower().strip(".!? ") in EXIT_COMMANDS


def get_groq_reply(user_text: str, history=None) -> str:
    """
    Sends user_text (plus recent prior turns) to Groq and returns the
    assistant's reply text.

    Args:
        user_text: the user's message.
        history: list of {"role": "user"|"assistant", "content": str}
            dicts for prior turns. Vercel functions are stateless
            between requests, so — unlike the original GroqAssistant,
            which kept conversation memory on `self.history` for the
            life of a Streamlit session — the FRONTEND now resends
            the recent turns with each request (see script.js) and
            this function just trims/forwards them.

    Raises:
        GroqAPIError: if the key is missing/invalid, the network
        fails, the rate limit is hit, or Groq returns nothing usable.
    """
    if not GROQ_API_KEY:
        raise GroqAPIError("GROQ_API_KEY is not configured on the server.")
    if not user_text or not user_text.strip():
        raise GroqAPIError("Cannot send an empty message to the assistant.")

    from groq import Groq, APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

    client = Groq(api_key=GROQ_API_KEY)

    history = list(history or [])
    if len(history) > MAX_HISTORY_MESSAGES:
        history = history[-MAX_HISTORY_MESSAGES:]

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_text}]
    )

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=GROQ_MAX_TOKENS,
            temperature=GROQ_TEMPERATURE,
        )
    except AuthenticationError as e:
        raise GroqAPIError("Invalid or unauthorized Groq API key.") from e
    except RateLimitError as e:
        raise GroqAPIError(
            "Groq API rate limit reached. Please wait a moment before trying again."
        ) from e
    except APIConnectionError as e:
        raise GroqAPIError("Network error while contacting Groq.") from e
    except APIStatusError as e:
        raise GroqAPIError(f"Groq API returned an error (status {e.status_code}).") from e
    except Exception as e:
        raise GroqAPIError(f"Groq API request failed: {e}") from e

    reply = ""
    if response.choices:
        reply = (response.choices[0].message.content or "").strip()

    if not reply:
        raise GroqAPIError("Groq returned an empty response. Please try again.")

    return reply


def synthesize_speech_mp3(text: str, speed: float = 1.0) -> bytes:
    """
    Converts text to speech using gTTS and returns raw mp3 bytes,
    entirely in memory (no temp files — nothing to clean up, and
    nothing that depends on persistent local disk state).

    Args:
        text: the text to speak.
        speed: gTTS only supports "normal" vs "slow" speech (no
            fine-grained rate control); values below 0.85 use gTTS's
            slow=True mode as the closest available approximation —
            unchanged from the original project's behaviour.

    Raises:
        TextToSpeechError: if synthesis fails (e.g. no internet
        connection from the server to Google's TTS service).
    """
    if not text or not text.strip():
        raise TextToSpeechError("Cannot synthesize empty text.")

    from gtts import gTTS
    import io

    try:
        buffer = io.BytesIO()
        slow = speed < 0.85
        gTTS(text=text, lang=TTS_LANGUAGE, slow=slow).write_to_fp(buffer)
        return buffer.getvalue()
    except Exception as e:
        raise TextToSpeechError(
            "Failed to generate speech. Please check the server's internet connection."
        ) from e
