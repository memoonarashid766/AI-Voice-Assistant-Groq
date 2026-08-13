"""
api/index.py
-------------
THE single Vercel Python entrypoint for this project.

Why this file exists: Vercel's current Python runtime loads exactly
ONE application per project, auto-detected from a default location —
app.py, index.py, server.py, main.py, wsgi.py, or asgi.py, at the
project root or inside src/, app/, or api/ (see
https://vercel.com/docs/functions/runtimes/python). Once a project
has a recognized Python entrypoint like this, Vercel treats it as a
full framework app and routes ALL paths through it by default — not
just /api/*. That's why "/" was returning Flask's own 404 page instead
of index.html: nothing here previously answered GET "/", so Flask
correctly reported "not found" for a route that genuinely didn't
exist on the Flask app, even though index.html was sitting right next
to it in the repo.

The fix below is exactly that: THIS app now also serves index.html,
script.js, and style.css directly for GET "/", "/script.js", and
"/style.css", reading them from disk with paths computed from this
file's own location (`PROJECT_ROOT`, the parent of api/) — never from
the current working directory, which Vercel doesn't guarantee.

/api/chat and /api/speak (POST + OPTIONS) are unchanged from before.

chat.py, speak.py, and _common.py are untouched — they keep exposing
plain functions that this file calls; none of their Groq/gTTS logic
changed.

See vercel.json (project root) for the `includeFiles` setting that
makes sure index.html/style.css/script.js are actually bundled into
this function's deployment — without it, Vercel's Python builder may
only include files reachable via Python imports, which these three
static files aren't.
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
