"""Model list resolution.

The LiteLLM proxy is the source of truth for which models exist; a user-edited
config/models.json allow-list curates which subset the picker offers. The
hardcoded FALLBACK_MODELS list lives here and nowhere else, used only when the
proxy is unreachable and no allow-list is configured.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List

import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Single source for the hardcoded fallback (proxy unreachable + no allow-list).
FALLBACK_MODELS: List[str] = ["gpt-4o", "gpt-4o-mini", "gpt-5-mini"]

# config/models.json lives at the repo root: src/evaluator/models.py -> ../../config
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "models.json"


def _read_allowed_models() -> List[str]:
    """Read the curated allow-list from config/models.json (empty if missing)."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        allowed = data.get("allowed_models", [])
        return [m.strip() for m in allowed if isinstance(m, str) and m.strip()]
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", _CONFIG_PATH, exc)
        return []


def _fetch_proxy_models() -> List[str]:
    """GET {LITELLM_API_BASE}/models and return the model ids in proxy order.

    Raises on any network/parse error so the caller can fall back.
    """
    base = (os.getenv("LITELLM_API_BASE") or "").rstrip("/")
    key = os.getenv("LITELLM_API_KEY") or ""
    if not base:
        raise RuntimeError("LITELLM_API_BASE is not set")

    req = urllib.request.Request(
        f"{base}/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    # OpenAI-compatible: { "data": [ { "id": "..." }, ... ] }
    data = payload.get("data", payload if isinstance(payload, list) else [])
    ids: List[str] = []
    for entry in data:
        if isinstance(entry, dict) and entry.get("id"):
            ids.append(entry["id"])
        elif isinstance(entry, str):
            ids.append(entry)
    return ids


def list_all_proxy_models() -> List[str]:
    """Full proxy /models list (NOT filtered by the picker allow-list).

    Used to resolve the judge council — judges need not appear in the picker.
    Returns [] on any error rather than raising (the caller falls back).
    """
    try:
        return _fetch_proxy_models()
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("Proxy /models unreachable for council resolution: %s", exc)
        return []


def list_models() -> Dict[str, object]:
    """Resolve the model list for the picker.

    Returns { "models": [...], "source": "config" | "proxy"
              | "config-unverified" | "fallback" }.
    """
    allowed = _read_allowed_models()

    try:
        proxy_models = _fetch_proxy_models()
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("Proxy /models unreachable: %s", exc)
        if allowed:
            return {"models": allowed, "source": "config-unverified"}
        return {"models": list(FALLBACK_MODELS), "source": "fallback"}

    if allowed:
        # Match case-insensitively against the proxy and return the proxy's
        # canonical casing (so e.g. "GPT-5.2" in config resolves to "gpt-5.2").
        # Preserve allow-list order; drop ids the proxy doesn't actually serve.
        proxy_by_lower = {m.lower(): m for m in proxy_models}
        filtered: List[str] = []
        missing: List[str] = []
        for m in allowed:
            canonical = proxy_by_lower.get(m.lower())
            if canonical is not None:
                filtered.append(canonical)
            else:
                missing.append(m)
        if missing:
            logger.warning(
                "config/models.json lists models the proxy does not serve "
                "(dropped): %s. Available: %s",
                ", ".join(missing),
                ", ".join(proxy_models) or "(none)",
            )
        return {"models": filtered, "source": "config"}

    return {"models": proxy_models, "source": "proxy"}
