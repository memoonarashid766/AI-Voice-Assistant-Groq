"""
api/speak.py
-------------
Vercel serverless function: POST /api/speak

Takes response text and returns synthesized speech as raw mp3 bytes
(Content-Type: audio/mpeg) — NOT JSON, so the browser can hand the
response body straight to an in-memory Audio object and play it
automatically, with no visible player and no download/play button.

Request body (JSON):
    {"text": "hello there", "speed": 1.0}

Response:
    200, Content-Type: audio/mpeg, raw mp3 bytes
    or
    non-200, Content-Type: application/json, {"error": "..."}
"""

import json
from http.server import BaseHTTPRequestHandler

from _common import synthesize_speech_mp3, TextToSpeechError


class handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_error(self, status: int, message: str):
        body = json.dumps({"error": message}).encode("utf-8")
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
            self._send_error(400, "Invalid JSON body.")
            return

        text = (data.get("text") or "").strip()
        try:
            speed = float(data.get("speed") or 1.0)
        except (TypeError, ValueError):
            speed = 1.0

        if not text:
            self._send_error(400, "Text is empty.")
            return

        try:
            audio_bytes = synthesize_speech_mp3(text, speed=speed)
        except TextToSpeechError as e:
            self._send_error(502, str(e))
            return

        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio_bytes)))
        self.end_headers()
        self.wfile.write(audio_bytes)
