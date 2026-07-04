"""Generates candidate firewall rules from detected anomalies via the configured LLM provider."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from providers.factory import get_provider

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "knowledge" / "prompts" / "rule_gen.txt"
)

REQUIRED_FIELDS = {
    "syntax",
    "command",
    "description",
    "mitre_technique",
    "confidence",
    "false_positive_risk",
    "reasoning",
}


class RuleGenerationError(Exception):
    """Raised when the LLM provider fails or returns an unparseable rule."""


@dataclass
class AnomalyContext:
    """Summarizes a detected anomaly for the rule generation prompt."""

    traffic_summary: str
    anomaly_score: float
    anomaly_type: str
    first_seen: str
    last_seen: str
    affected_flows: str


def _load_prompt_template() -> str:
    """Read the rule generation prompt template from knowledge/prompts/."""
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _find_json_object(text: str) -> str | None:
    """Locate the first balanced {...} JSON object substring in free-form text.

    Some models narrate around the JSON instead of fencing it — e.g. llama3.1
    returning "Here is the required output:\\n\\n{...}\\n\\nThis rule uses..."
    with no code fence at all. Brace-counting (ignoring braces inside string
    literals) finds the object regardless of what surrounds it.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i, char in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json(raw_response: str) -> dict[str, Any]:
    """Parse the LLM's JSON response, tolerating a markdown code fence or surrounding prose."""
    text = raw_response.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        first_error = e

    json_candidate = _find_json_object(text)
    if json_candidate is not None:
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

    raise RuleGenerationError(f"LLM response was not valid JSON: {first_error}")


def generate_rule(
    anomaly: AnomalyContext, firewall_syntax: str = "iptables"
) -> dict[str, Any]:
    """Generate one candidate firewall rule for the given anomaly."""
    template = _load_prompt_template()
    prompt = template.format(
        traffic_summary=anomaly.traffic_summary,
        anomaly_score=anomaly.anomaly_score,
        anomaly_type=anomaly.anomaly_type,
        first_seen=anomaly.first_seen,
        last_seen=anomaly.last_seen,
        affected_flows=anomaly.affected_flows,
        firewall_syntax=firewall_syntax,
    )

    provider = get_provider()

    try:
        raw_response = provider.generate(prompt)
    except Exception as e:
        # Providers raise different exception types (httpx.HTTPError,
        # anthropic.APIError, openai.APIError). Catching broadly here is the
        # abstraction boundary: rule_gen.py must never import a specific
        # provider's exception type, or it stops being provider-agnostic.
        raise RuleGenerationError(f"LLM provider call failed: {e}") from e

    rule = _extract_json(raw_response)

    missing = REQUIRED_FIELDS - rule.keys()
    if missing:
        raise RuleGenerationError(f"LLM response missing required fields: {missing}")

    return rule
