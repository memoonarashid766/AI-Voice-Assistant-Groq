"""
api/chat.py
------------
Vercel serverless function: POST /api/chat

Takes the user's message (typed, or already transcribed in the
browser from speech — see script.js) and returns the Groq assistant's
reply as text. This is the ONLY place the Groq API key is used; it
never reaches the browser.

Request body (JSON):
    {
        "message": "hello",
        "history": [{"role": "user"|"assistant", "content": "..."}, ...]
    }

Response body (JSON):
    {"reply": "...", "is_exit": false}
    or
    {"error": "..."}   (with a non-200 status)
"""

import json
from http.server import BaseHTTPRequestHandler

from _common import get_groq_reply, is_exit_command, GroqAPIError


class handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        # Same-origin in production (frontend and /api are one Vercel
        # deployment), but harmless and convenient to allow generally —
        # e.g. testing the frontend from a different local port.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
        except Exception:
            self._send_json(400, {"error": "Invalid JSON body."})
            return

        user_text = (data.get("message") or "").strip()
        history = data.get("history") or []

        if not user_text:
            self._send_json(400, {"error": "Message is empty."})
            return

        if is_exit_command(user_text):
            self._send_json(200, {"reply": "Goodbye!", "is_exit": True})
            return

        try:
            reply = get_groq_reply(user_text, history=history)
        except GroqAPIError as e:
            self._send_json(502, {"error": str(e)})
            return

        self._send_json(200, {"reply": reply, "is_exit": False})
