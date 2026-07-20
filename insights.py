"""
insights.py — turn the stats into plain-English findings.

Calls Claude if a key is available (env var or Streamlit secret), otherwise
returns the bundled cached set so the app always works. Only the aggregates go
to the model, never the raw task rows: the numbers stay authoritative and the
model just writes about them.
"""

import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "insights_cached.json"
DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM = """You are an analyst embedded in a delivery team. You are given \
pre-computed statistics from a task-level time tracking dataset. Your job is to \
write 3-5 insights a team lead can act on in their next planning meeting.

Rules:
- The statistics are authoritative. Never invent, recompute, or contradict a number.
- Every insight must cite at least one specific number from the stats.
- Find the bottleneck, don't just restate the total. Prefer comparisons (this cohort
  vs that one) over standalone facts. "Estimates slipped 48%" is a number; "estimates
  hold under 8h and collapse above 16h" is an insight.
- Be concrete about people only where the data is unambiguous, and describe the
  pattern (an estimation-calibration gap), not the person's competence.
- No hedging, no filler, no restating the question. Plain English, short sentences.

Return ONLY a JSON array, no prose and no markdown fences. Each element:
{
  "headline": "under 60 chars, the finding itself, sentence case",
  "body": "2-3 sentences: what the data shows, why it matters",
  "metric": "the single number that proves it, under 18 chars",
  "metric_label": "what that number is, under 30 chars",
  "severity": "critical" | "warning" | "watch",
  "action": "one sentence, imperative, something doable this sprint"
}
Order by severity, most severe first."""

REQUIRED = {"headline", "body", "metric", "metric_label", "severity", "action"}


def _get_key():
    """Look in the environment first, then Streamlit secrets if available."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def _stats_for_prompt(stats: dict) -> dict:
    """DataFrames -> records; drop the 160-row scatter the model doesn't need."""
    out = {}
    for k, v in stats.items():
        if k == "scatter":
            continue
        out[k] = v.to_dict("records") if isinstance(v, pd.DataFrame) else v
    return out


def _parse(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lower().startswith("json") else text
    a, b = text.find("["), text.rfind("]")
    if a == -1 or b == -1:
        raise ValueError("no JSON array in model response")
    insights = json.loads(text[a:b + 1])
    if not isinstance(insights, list) or not insights:
        raise ValueError("empty insight list")
    for i in insights:
        missing = REQUIRED - set(i)
        if missing:
            raise ValueError(f"insight missing fields: {sorted(missing)}")
    return insights[:5]


def cached():
    return json.loads(CACHE.read_text())


def generate(stats: dict, model: str = DEFAULT_MODEL):
    """
    Returns (insights, source_label). Never raises — on any failure it falls back
    to the cached set so the dashboard keeps rendering.
    """
    key = _get_key()
    if not key:
        return cached(), "cached (no API key set)"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    "Task time tracking statistics for the current period.\n"
                    "Slip percentages are (actual / estimated - 1) * 100. Positive means over estimate.\n"
                    "'on_target' means within +/-10% of estimate.\n\n"
                    f"{json.dumps(_stats_for_prompt(stats), indent=2)}\n\nWrite the insights."
                ),
            }],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return _parse(text), f"live: {model}"
    except Exception as e:
        return cached(), f"cached (live call failed: {type(e).__name__})"
