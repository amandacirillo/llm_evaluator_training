"""Demo Flask server for the LLM Evaluator.

Routes:
    GET  /api/models    — resolve the model picker list (config allow-list + proxy)
    POST /api/score     — scoring mode: auto-generate the checklist and grade it (SSE)
    POST /api/generate  — output-only mode: compare outputs side by side (SSE)

Scoring is a single stateless call: the checklist is generated automatically
(no human review/edit step) and graded in the same request stream.

In production (demo/ui/dist exists) the server also serves the pre-built React
SPA. The LiteLLM key is read from the environment here and is NEVER serialized
into a response. The server holds no business logic; it wires the pipeline to HTTP.

Usage:
    # from the repo root, with .env populated
    python -m demo.server.app
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

# Make src/ importable: demo/server/app.py -> ../../src
ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

load_dotenv(ROOT / ".env")

from evaluator.models import list_models  # noqa: E402
from evaluator.pipeline import generate as generate_outputs  # noqa: E402
from evaluator.pipeline import score  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = ROOT / "demo" / "ui" / "dist"


def create_app() -> Flask:
    # Serve the pre-built React SPA from demo/ui/dist when it exists (production).
    if STATIC_DIR.exists():
        app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    else:
        app = Flask(__name__)

    CORS(app)

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/api/models", methods=["GET"])
    def models():
        return jsonify(list_models())

    def _clean_models(body):
        models_in = body.get("models") or []
        return [m for m in models_in if isinstance(m, str) and m.strip()]

    def _sse(event_iter):
        def stream():
            for event_name, payload in event_iter:
                yield f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"

        return Response(
            stream(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/score", methods=["POST", "OPTIONS"])
    def score_route():
        """Scoring mode — auto-generate the checklist and grade it (SSE)."""
        if request.method == "OPTIONS":
            return ("", 204)
        body = request.get_json(silent=True) or {}
        prompt = (body.get("prompt") or "").strip()
        title = body.get("title") or None
        models_in = _clean_models(body)

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400
        if not (1 <= len(models_in) <= 3):
            return jsonify({"error": "select 1 to 3 models"}), 400

        return _sse(score(prompt, models_in, title=title))

    @app.route("/api/generate", methods=["POST", "OPTIONS"])
    def generate_route():
        """Output-only mode — compare outputs side by side, no scoring (SSE)."""
        if request.method == "OPTIONS":
            return ("", 204)
        body = request.get_json(silent=True) or {}
        prompt = (body.get("prompt") or "").strip()
        title = body.get("title") or None
        models_in = _clean_models(body)

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400
        if not (1 <= len(models_in) <= 3):
            return jsonify({"error": "select 1 to 3 models"}), 400

        return _sse(generate_outputs(prompt, models_in, title=title))

    # SPA catch-all: serve index.html for any non-API route so client-side
    # routing works when the app is refreshed or deep-linked.
    if STATIC_DIR.exists():
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_spa(path: str):
            target = STATIC_DIR / path
            if path and target.exists() and target.is_file():
                return send_from_directory(str(STATIC_DIR), path)
            return send_from_directory(str(STATIC_DIR), "index.html")

    return app


def main() -> None:
    port = int(os.getenv("PORT", "5001"))
    app = create_app()
    # threaded=True so parallel model calls + SSE streaming don't block each other.
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
