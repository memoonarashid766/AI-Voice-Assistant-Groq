"""
api/index.py
-------------
THE single Vercel Python entrypoint for this project.

Why this file exists: Vercel's current Python runtime loads exactly
ONE application per project, auto-detected from a default location —
app.py, index.py, server.py, main.py, wsgi.py, or asgi.py, at the
project root or inside src/, app/, or api/ (see
https://vercel.com/docs/functions/runtimes/python). It does NOT run
every api/*.py file as its own independent function the way an older
version of the runtime used to. That's exactly what your deployment
error was reporting: it found a `handler` variable in both chat.py and
speak.py and couldn't tell which one single file should be treated as
"the app", since neither lives in a default location.

Vercel's suggested fix (`[tool.vercel] entrypoint = "chat:handler"`)
would only fix the ambiguity by picking ONE of the two files — that
would make /api/chat work and permanently break /api/speak (or vice
versa). Since this project genuinely needs two routes, the correct
fix is a single small router app, in a default location, that
delegates to both — that's what this file is.

api/index.py itself IS a default location, so Vercel auto-detects
this `app` object with no extra configuration (no pyproject.toml
needed — see the project README for why one wasn't added).

chat.py and speak.py keep their original names, locations, and all of
their real logic — they just expose a plain function now instead of
being their own entrypoint (see their docstrings).
"""

import os
import sys

# Make sibling modules in this same api/ directory importable
# (chat.py, speak.py, _common.py) regardless of how Vercel's runtime
# invokes this file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, Response, jsonify, request

import chat as chat_module
import speak as speak_module

app = Flask(__name__)


def _with_cors(response):
    # Same-origin in production (frontend and /api are one Vercel
    # deployment), but harmless and convenient to allow generally —
    # e.g. testing the frontend from a different local port.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat_route():
    if request.method == "OPTIONS":
        return _with_cors(Response(status=204))

    data = request.get_json(silent=True) or {}
    status, payload = chat_module.handle_chat(data)
    response = jsonify(payload)
    response.status_code = status
    return _with_cors(response)


@app.route("/api/speak", methods=["POST", "OPTIONS"])
def speak_route():
    if request.method == "OPTIONS":
        return _with_cors(Response(status=204))

    data = request.get_json(silent=True) or {}
    status, content_type, body = speak_module.handle_speak(data)

    if content_type == "application/json":
        response = jsonify(body)
        response.status_code = status
    else:
        response = Response(body, status=status, content_type=content_type)

    return _with_cors(response)
