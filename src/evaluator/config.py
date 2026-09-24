"""Evaluator tunables, loaded from config/evaluator.json.

Everything except the proxy secret/endpoint lives here (committed, non-secret):
the checklist/critic model, the judge council + backup judge, the sample count N,
and the temperature used for the compared models. The environment holds only
LITELLM_API_KEY and LITELLM_API_BASE.

Missing file or missing keys fall back to DEFAULTS, so the app still runs before
the operator hardcodes their real model ids. Malformed values are coerced or
dropped rather than crashing the app.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# config/evaluator.json lives at the repo root: src/evaluator/config.py -> ../../config
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "evaluator.json"

# Placeholder defaults. The operator overrides these in config/evaluator.json with
# the exact ids their LiteLLM proxy serves.
DEFAULTS: Dict[str, Any] = {
    "checklist_model": "claude-sonnet-4-6",
    "council": ["claude-sonnet-4-6", "gpt-5.4", "claude-sonnet-4-5"],
    "backup_judge": "gpt-5.4-mini",
    "samples": 5,
    "output_temperature": 0.0,
}


def _clean_str(value: Any, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _clean_str_list(value: Any, default: List[str]) -> List[str]:
    if not isinstance(value, list):
        return list(default)
    cleaned = [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return cleaned if cleaned else list(default)


def _clean_int(value: Any, default: int, *, minimum: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= minimum else default


def _clean_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_evaluator_config() -> Dict[str, Any]:
    """Return the evaluator config, merging config/evaluator.json over DEFAULTS.

    Read fresh each call (no caching — cheap file read, and the app deliberately
    holds no cross-request state).
    """
    raw: Dict[str, Any] = {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            raw = loaded
        else:
            logger.warning("%s is not a JSON object; using defaults", _CONFIG_PATH)
    except FileNotFoundError:
        logger.info("%s not found; using evaluator defaults", _CONFIG_PATH)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s; using defaults", _CONFIG_PATH, exc)

    return {
        "checklist_model": _clean_str(raw.get("checklist_model"), DEFAULTS["checklist_model"]),
        "council": _clean_str_list(raw.get("council"), DEFAULTS["council"]),
        "backup_judge": _clean_str(raw.get("backup_judge"), DEFAULTS["backup_judge"]),
        "samples": _clean_int(raw.get("samples"), DEFAULTS["samples"]),
        "output_temperature": _clean_float(
            raw.get("output_temperature"), DEFAULTS["output_temperature"]
        ),
    }


def checklist_model() -> str:
    """Model id used for the checklist maker and critic passes."""
    return load_evaluator_config()["checklist_model"]


def council_models() -> List[str]:
    """Configured default judge council (before proxy/self-judging resolution)."""
    return load_evaluator_config()["council"]


def backup_judge() -> str:
    """Backup judge id used by the self-judging safeguard."""
    return load_evaluator_config()["backup_judge"]


def sample_count() -> int:
    """N — how many times each model is called in scoring mode."""
    return load_evaluator_config()["samples"]


def output_temperature() -> float:
    """Temperature for the compared models' generations (judges always run at 0)."""
    return load_evaluator_config()["output_temperature"]
