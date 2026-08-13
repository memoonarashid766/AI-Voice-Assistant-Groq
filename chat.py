"""
api/chat.py
------------
Chat logic for POST /api/chat.

NOT a Vercel entrypoint itself anymore — see api/index.py, which is
the single entrypoint the current Vercel Python runtime requires (it
loads exactly one app per project from a default location like
api/index.py, not one per api/*.py file — see
https://vercel.com/docs/functions/runtimes/python). This file keeps
its name/location and all of its actual logic; only the outer shape
changed, from a standalone `class handler(BaseHTTPRequestHandler)` to
a plain function that api/index.py's Flask route calls directly.

Takes the user's message (typed, or already transcribed in the
browser from speech — see script.js) and returns the Groq assistant's
reply as text. This is one of only two places (with speak.py) that
ever import Groq logic; the API key never reaches the browser.
"""

from _common import get_groq_reply, is_exit_command, GroqAPIError


def handle_chat(data: dict):
    """
    Args:
        data: parsed JSON body, expected shape
            {"message": "hello", "history": [{"role": ..., "content": ...}, ...]}

    Returns:
        (status_code: int, payload: dict) — payload is the JSON body
        api/index.py should send back, e.g. (200, {"reply": "...", "is_exit": False})
        or (400, {"error": "..."}).
    """
    user_text = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_text:
        return 400, {"error": "Message is empty."}

    if is_exit_command(user_text):
        return 200, {"reply": "Goodbye!", "is_exit": True}

    try:
        reply = get_groq_reply(user_text, history=history)
    except GroqAPIError as e:
        return 502, {"error": str(e)}

    return 200, {"reply": reply, "is_exit": False}
