"""
LLM Response Parser.

Validates the structured JSON output from the LLM against the expected schema.
If validation fails, logs the error and returns None so the orchestrator can
fall back to plain notifications.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"summary", "root_causes", "suggested_fixes", "business_impact", "confidence"}

def parse_and_validate(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Validates the LLM response dict against the expected schema.
    Applies heuristic confidence reductions.
    If parsing fails, returns a fallback dict with parsing_failure=True.
    """
    def _fallback():
        return {
            "summary": "AI enrichment failed to generate a valid structured response.",
            "root_causes": [],
            "suggested_fixes": [],
            "business_impact": "",
            "confidence": "low",
            "parsing_failure": True,
        }

    missing = _REQUIRED_FIELDS - raw.keys()
    if missing:
        logger.warning("LLM response missing required fields: %s", missing)
        return _fallback()

    if not isinstance(raw.get("root_causes"), list) or not isinstance(raw.get("suggested_fixes"), list):
        logger.warning("LLM root_causes or suggested_fixes is not a list")
        return _fallback()

    if not isinstance(raw.get("summary"), str) or not raw["summary"].strip():
        logger.warning("LLM summary is invalid")
        return _fallback()

    raw_conf = str(raw.get("confidence", "low")).strip().lower()
    if raw_conf not in {"high", "medium", "low"}:
        raw_conf = "low"

    # Hybrid confidence scoring (heuristic reductions)
    effective_conf = raw_conf
    
    # Heuristic 1: If it's "high" but very few root causes, reduce to medium
    if effective_conf == "high" and len(raw["root_causes"]) == 0:
        effective_conf = "medium"
        
    # Heuristic 2: If the summary is extremely short, reduce confidence
    if len(raw["summary"]) < 20 and effective_conf in {"high", "medium"}:
        effective_conf = "low"

    return {
        "summary": raw["summary"].strip(),
        "root_causes": [str(c) for c in raw["root_causes"]],
        "suggested_fixes": [str(f) for f in raw["suggested_fixes"]],
        "business_impact": str(raw.get("business_impact", "")).strip(),
        "confidence": effective_conf,
        "parsing_failure": False,
    }
