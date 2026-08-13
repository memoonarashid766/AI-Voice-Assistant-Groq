"""
api/index.py
-------------
THE single Vercel Python entrypoint for this project.

Routing: this file needs no routing configuration in vercel.json at
all. Vercel's current Python runtime auto-detects a Python entrypoint
from a fixed set of recognized filenames — app.py, index.py, server.py,
main.py, wsgi.py, or asgi.py — found at the project root or inside
src/, app/, or api/ (see https://vercel.com/docs/functions/runtimes/python).
"index.py" inside "api/" matches both the recognized name and the
recognized location, and this file defines a top-level `app` (a Flask/
WSGI application), which is exactly what Vercel looks for. Once
detected this way, Vercel treats the project as a full framework app
and sends every incoming path to this one function automatically —
"/", "/script.js", "/style.css", "/api/chat", "/api/speak" all included
— so this app's own @app.route decorators below see the real,
original request path with no rewrite/route config needed to get
there, and no separate config to maintain or get wrong.

/api/chat and /api/speak (POST + OPTIONS) are unchanged from before.

chat.py, speak.py, and _common.py are untouched — they keep exposing
plain functions that this file calls; none of their Groq/gTTS logic
changed.

See vercel.json (project root) for the `includeFiles` setting, which
is the ONE thing that's still needed: it makes sure index.html,
style.css, and script.js are bundled into this function's deployment.
That's unrelated to routing — it's needed because those three files
are read at runtime via send_file(), not via a Python import, and
Vercel's Python builder only auto-includes files reachable through
imports.
"""

import os
import sys

# Make sibling modules in this same api/ directory importable
# (chat.py, speak.py, _common.py) regardless of how Vercel's runtime
# invokes this file.
API_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, API_DIR)

# Absolute path to the project root (parent of api/), where
# index.html / style.css / script.js live — computed from this file's
# own location so it's correct no matter what Vercel's working
# directory happens to be at request time.
PROJECT_ROOT = os.path.dirname(API_DIR)

from flask import Flask, Response, jsonify, request, send_file

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


# ----------------------------------------------------------------------
# Static frontend — served directly by this app (see module docstring
# for why Vercel routes these paths here instead of serving them as
# plain static files once a Python entrypoint like this exists).
# ----------------------------------------------------------------------
@app.route("/", methods=["GET"])
def serve_index():
    return send_file(os.path.join(PROJECT_ROOT, "index.html"), mimetype="text/html")


@app.route("/script.js", methods=["GET"])
def serve_script():
    return send_file(os.path.join(PROJECT_ROOT, "script.js"), mimetype="application/javascript")


@app.route("/style.css", methods=["GET"])
def serve_style():
    return send_file(os.path.join(PROJECT_ROOT, "style.css"), mimetype="text/css")


# ----------------------------------------------------------------------
# API routes — unchanged.
# ----------------------------------------------------------------------
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
