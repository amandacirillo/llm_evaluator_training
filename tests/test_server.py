"""Flask routes: checklist (JSON), grade + generate (SSE), validation, no /api/run."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from demo.server import app as appmod  # noqa: E402


@pytest.fixture
def client():
    return appmod.create_app().test_client()


def test_score_streams_sse(client, monkeypatch):
    captured = {}

    def fake_score(prompt, models, *, title=None):
        captured["prompt"] = prompt
        captured["models"] = models
        captured["title"] = title
        yield ("checklist", {"checklist": [{"id": "r1", "text": "x"}]})
        yield ("outputs", {"outputs": []})
        yield ("scoring", {"status": "scoring"})
        yield ("done", {"mode": "scoring", "models": []})

    monkeypatch.setattr(appmod, "score", fake_score)

    resp = client.post("/api/score", json={"prompt": "p", "title": "T", "models": ["m1", "m2"]})
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    body = resp.get_data(as_text=True)
    assert "event: checklist" in body and "event: done" in body
    assert captured["models"] == ["m1", "m2"]
    # No client-supplied checklist — the server generates it.
    assert captured["prompt"] == "p"


def test_score_validation(client, monkeypatch):
    monkeypatch.setattr(appmod, "score", lambda *a, **k: iter([("done", {})]))
    assert client.post("/api/score", json={"prompt": "p", "models": []}).status_code == 400
    assert client.post(
        "/api/score", json={"prompt": "p", "models": ["a", "b", "c", "d"]}
    ).status_code == 400
    assert client.post("/api/score", json={"prompt": "", "models": ["m1"]}).status_code == 400


def test_old_scoring_routes_removed(client):
    # The two-phase routes were merged into /api/score.
    assert client.post("/api/checklist", json={"prompt": "p"}).status_code in (404, 405)
    assert client.post("/api/grade", json={"prompt": "p", "models": ["m1"], "checklist": [{"id": "r1"}]}).status_code in (404, 405)


def test_generate_streams_sse(client, monkeypatch):
    def fake_generate(prompt, models, *, title=None):
        yield ("outputs", {"outputs": [{"model": m, "output": "o", "error": None} for m in models]})
        yield ("done", {"mode": "output_only", "models": []})

    monkeypatch.setattr(appmod, "generate_outputs", fake_generate)
    resp = client.post("/api/generate", json={"prompt": "p", "models": ["m1"]})
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert "event: done" in resp.get_data(as_text=True)


def test_generate_validation(client):
    assert client.post("/api/generate", json={"prompt": "", "models": ["m1"]}).status_code == 400
    assert client.post("/api/generate", json={"prompt": "p", "models": []}).status_code == 400


def test_old_run_route_removed(client):
    # 404 (no rule) or 405 (SPA catch-all matches GET-only when dist exists);
    # either way the old streaming POST endpoint no longer functions.
    assert client.post("/api/run", json={"prompt": "p", "models": ["m1"]}).status_code in (404, 405)


def test_models_endpoint(client, monkeypatch):
    monkeypatch.setattr(appmod, "list_models", lambda: {"models": ["m1", "m2"], "source": "config"})
    resp = client.get("/api/models")
    assert resp.status_code == 200
    assert resp.get_json() == {"models": ["m1", "m2"], "source": "config"}
