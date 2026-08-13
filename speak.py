"""
api/speak.py
-------------
Text-to-speech logic for POST /api/speak.

NOT a Vercel entrypoint itself anymore — see api/index.py, which is
the single entrypoint the current Vercel Python runtime requires (see
chat.py's docstring for the full explanation). This file keeps its
name/location and all of its actual logic; only the outer shape
changed, from a standalone `class handler(BaseHTTPRequestHandler)` to
a plain function that api/index.py's Flask route calls directly.

Takes response text and returns synthesized speech as raw mp3 bytes —
NOT JSON — so the browser can hand the response body straight to an
in-memory Audio object and play it automatically, with no visible
player and no download/play button.
"""

from _common import synthesize_speech_mp3, TextToSpeechError


def handle_speak(data: dict):
    """
    Args:
        data: parsed JSON body, expected shape {"text": "...", "speed": 1.0}

    Returns:
        (status_code: int, content_type: str, body) where body is raw
        mp3 bytes on success (content_type "audio/mpeg") or a dict on
        failure (content_type "application/json") — api/index.py picks
        the right Flask response type based on content_type.
    """
    text = (data.get("text") or "").strip()
    try:
        speed = float(data.get("speed") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0

    if not text:
        return 400, "application/json", {"error": "Text is empty."}

    try:
        audio_bytes = synthesize_speech_mp3(text, speed=speed)
    except TextToSpeechError as e:
        return 502, "application/json", {"error": str(e)}

    return 200, "audio/mpeg", audio_bytes
