"""Shared LLM factory and JSON parsing utilities.

Mirrors the pattern used across our other internal LLM-backed services:
all callers construct a ChatOpenAI through get_llm() so proxy config stays
consistent. Only the proxy secret/endpoint (LITELLM_API_KEY / LITELLM_API_BASE)
come from the environment; model selection and the compared-model temperature
come from config/evaluator.json (see config.py). The proxy key never leaves the
server.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from .config import checklist_model as _checklist_model
from .config import output_temperature as _output_temperature

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def get_llm(
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> "ChatOpenAI":
    """Construct a ChatOpenAI pointed at the LiteLLM proxy.

    Args:
        model: Model id override. Falls back to the configured checklist model
            (config/evaluator.json → checklist_model).
        temperature: Sampling temperature (default 0.2).
        json_mode: If True, request a JSON response_format from the model.
    """
    # Imported lazily so modules that only use the pure helpers (and tests that
    # stub the LLM) don't require langchain-openai to be installed.
    from langchain_openai import ChatOpenAI

    kwargs: Dict[str, Any] = {
        "base_url": os.getenv("LITELLM_API_BASE"),
        "api_key": os.getenv("LITELLM_API_KEY"),
        "model": model or _checklist_model(),
        "temperature": temperature,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(**kwargs)


def judge_model_name() -> str:
    """The model id used for checklist generation (maker + critic passes)."""
    return _checklist_model()


def output_temperature() -> float:
    """Temperature for the compared models' generations.

    Sourced from config/evaluator.json (default 0.0) so the same prompt yields
    outputs as reproducible as the proxy allows. The judge council always runs at
    0.0. (Even at 0.0, proxied LLMs are not perfectly deterministic — hence
    multi-sampling.)
    """
    return _output_temperature()


def call_model(model: str, prompt: str, *, temperature: Optional[float] = None) -> str:
    """Send a single user prompt to a model and return its text output."""
    temp = output_temperature() if temperature is None else temperature
    llm = get_llm(model=model, temperature=temp)
    response = llm.invoke(prompt)
    return response.content if isinstance(response.content, str) else str(response.content)


def parse_json_response(text: str, fallback: Optional[Dict] = None) -> Dict[str, Any]:
    """Parse JSON from an LLM response, tolerating markdown code fences.

    Returns the parsed dict, or `fallback` (default empty dict) on failure.
    """
    if fallback is None:
        fallback = {}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse JSON from LLM response: %s", text[:200])
    return fallback
