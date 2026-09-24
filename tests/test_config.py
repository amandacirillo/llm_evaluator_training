"""config.load_evaluator_config: defaults, file overrides, and type coercion."""

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import evaluator.config as config  # noqa: E402


def _reload_with_path(monkeypatch, tmp_path, data):
    """Point config at a temp evaluator.json (or None to simulate absence)."""
    cfg_path = tmp_path / "evaluator.json"
    if data is not None:
        cfg_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(config, "_CONFIG_PATH", cfg_path)
    return config


def test_defaults_when_file_absent(monkeypatch, tmp_path):
    c = _reload_with_path(monkeypatch, tmp_path, None)
    cfg = c.load_evaluator_config()
    assert cfg == {
        "checklist_model": c.DEFAULTS["checklist_model"],
        "council": c.DEFAULTS["council"],
        "backup_judge": c.DEFAULTS["backup_judge"],
        "samples": c.DEFAULTS["samples"],
        "output_temperature": c.DEFAULTS["output_temperature"],
    }
    # accessors reflect defaults
    assert c.sample_count() == c.DEFAULTS["samples"]
    assert c.checklist_model() == c.DEFAULTS["checklist_model"]
    assert c.council_models() == c.DEFAULTS["council"]


def test_file_values_override_defaults(monkeypatch, tmp_path):
    c = _reload_with_path(
        monkeypatch,
        tmp_path,
        {
            "checklist_model": "claude-x",
            "council": ["claude-x", "gpt-y", "claude-z"],
            "backup_judge": "gpt-backup",
            "samples": 3,
            "output_temperature": 0.4,
        },
    )
    cfg = c.load_evaluator_config()
    assert cfg["checklist_model"] == "claude-x"
    assert cfg["council"] == ["claude-x", "gpt-y", "claude-z"]
    assert cfg["backup_judge"] == "gpt-backup"
    assert cfg["samples"] == 3
    assert cfg["output_temperature"] == 0.4


def test_malformed_values_coerced_or_defaulted(monkeypatch, tmp_path):
    c = _reload_with_path(
        monkeypatch,
        tmp_path,
        {
            "checklist_model": "   ",          # blank -> default
            "council": [" a ", 5, "", "b"],    # trims, drops non-strings
            "samples": "not-a-number",         # -> default
            "output_temperature": "0.9",       # numeric string -> float
        },
    )
    cfg = c.load_evaluator_config()
    assert cfg["checklist_model"] == c.DEFAULTS["checklist_model"]
    assert cfg["council"] == ["a", "b"]
    assert cfg["samples"] == c.DEFAULTS["samples"]
    assert cfg["output_temperature"] == 0.9


def test_samples_below_minimum_falls_back(monkeypatch, tmp_path):
    c = _reload_with_path(monkeypatch, tmp_path, {"samples": 0})
    assert c.load_evaluator_config()["samples"] == c.DEFAULTS["samples"]


def test_llm_helpers_read_config_not_env(monkeypatch, tmp_path):
    """llm.judge_model_name/output_temperature come from config, and legacy env
    vars are ignored."""
    c = _reload_with_path(
        monkeypatch, tmp_path, {"checklist_model": "cfg-model", "output_temperature": 0.7}
    )
    # Legacy env vars must NOT influence anything anymore.
    monkeypatch.setenv("LITELLM_MODEL", "env-model")
    monkeypatch.setenv("LITELLM_OUTPUT_TEMPERATURE", "0.1")

    import evaluator.llm as llm
    importlib.reload(llm)  # re-bind its config imports to the patched module

    assert llm.judge_model_name() == "cfg-model"
    assert llm.output_temperature() == 0.7
