"""
ai/diagnosis.py
===============
AI-powered diagnosis engine for NetSage AI.
Uses Google Gemini API (configurable via .env).
"""

from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ─── Prompt loader ────────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    """Load the diagnose_prompt.md system prompt."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "diagnose_prompt.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "You are NetSage AI, a Cisco network troubleshooting assistant. "
        "Analyze the provided case and return ONLY valid JSON with fields: "
        "root_cause, confidence, osi_layer, evidence, next_command, fix_steps, "
        "verification_steps, reasoning_summary."
    )


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_user_prompt(case_data: dict, rule_results: list[dict]) -> str:
    """Build the user-turn prompt from case data + rule checker results."""
    from checker.checker import format_results_for_prompt

    sections = [
        "=== CASE INFORMATION ===",
        f"Case ID      : {case_data.get('case_id', 'N/A')}",
        f"Category     : {case_data.get('category', 'N/A')}",
        f"Title        : {case_data.get('title', 'N/A')}",
        f"Severity     : {case_data.get('severity', 'N/A')}",
        "",
        "=== SYMPTOM ===",
        case_data.get("symptom", "Not provided"),
        "",
        "=== TOPOLOGY ===",
        case_data.get("topology", "Not provided"),
        "",
        "=== DEVICE CONTEXT ===",
        case_data.get("device_context", "Not provided"),
        "",
        "=== SHOW COMMANDS USED ===",
        case_data.get("show_commands", "Not provided"),
        "",
        "=== SHOW COMMAND OUTPUT (Evidence) ===",
        case_data.get("show_output", "Not provided"),
        "",
        format_results_for_prompt(rule_results),
        "",
        "=== TASK ===",
        "Analyze the above evidence and return ONLY a valid JSON object matching the required schema. "
        "Do not include markdown, code fences, or explanatory text outside the JSON.",
    ]
    return "\n".join(sections)


# ─── JSON extraction ─────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Safely extract a JSON object from AI response text.
    Handles cases where the model wraps JSON in markdown code fences.
    """
    if not text or not text.strip():
        raise ValueError("AI returned empty response")

    # Strip markdown code fences
    clean = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    clean = re.sub(r"```", "", clean)
    clean = clean.strip()

    # Try direct parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try to find first {...} block
    brace_match = re.search(r'\{[\s\S]*\}', clean)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from AI response: {text[:200]!r}")


# ─── Response validator ───────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    "root_cause", "confidence", "osi_layer", "evidence",
    "next_command", "fix_steps", "verification_steps", "reasoning_summary"
]


def _validate_and_normalise(data: dict) -> dict:
    """Ensure all required fields exist and have sensible types."""
    # Fill missing fields with safe defaults
    defaults = {
        "root_cause": "Unable to determine root cause",
        "confidence": 0.0,
        "osi_layer": "Unknown",
        "evidence": [],
        "next_command": "Review show outputs manually",
        "fix_steps": [],
        "verification_steps": [],
        "reasoning_summary": "AI did not provide a reasoning summary.",
    }
    for field, default in defaults.items():
        if field not in data:
            data[field] = default

    # Clamp confidence to [0, 1]
    try:
        conf = float(data["confidence"])
        data["confidence"] = round(max(0.0, min(1.0, conf)), 3)
    except (TypeError, ValueError):
        data["confidence"] = 0.0

    # Ensure list fields are lists
    for list_field in ("evidence", "fix_steps", "verification_steps"):
        if isinstance(data[list_field], str):
            data[list_field] = [data[list_field]]
        elif not isinstance(data[list_field], list):
            data[list_field] = []

    return data


# ─── Error dict factory ───────────────────────────────────────────────────────

def _error_response(message: str, error_detail: str = "") -> dict:
    return {
        "root_cause": message,
        "confidence": 0.0,
        "osi_layer": "Unknown",
        "evidence": [],
        "next_command": "Check error details and retry",
        "fix_steps": [],
        "verification_steps": [],
        "reasoning_summary": f"Diagnosis unavailable: {message}",
        "error": error_detail or message,
    }


# ─── Main diagnosis function ─────────────────────────────────────────────────

def diagnose_case(case_data: dict[str, Any], rule_results: list[dict]) -> dict:
    """
    Run AI diagnosis on a single case.

    Args:
        case_data   : Case dict from cases.csv (all columns as keys).
        rule_results: List of dicts from checker.run_all_checks().

    Returns:
        Structured diagnosis dict with all required fields.
        Always returns a dict — never raises to the caller.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _error_response(
            "GEMINI_API_KEY not configured",
            "Set GEMINI_API_KEY in your .env file to enable AI diagnosis."
        )

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(case_data, rule_results)

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
        )

        response = model.generate_content(
            user_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )

        raw_text = response.text if hasattr(response, "text") else str(response)

    except ImportError:
        return _error_response(
            "google-generativeai package not installed",
            "Run: pip install google-generativeai"
        )
    except Exception as e:
        err_str = str(e)
        return _error_response(f"Gemini API error: {err_str}", err_str)

    # Parse and validate the JSON response
    try:
        parsed = _extract_json(raw_text)
    except ValueError as e:
        return _error_response(
            "AI returned malformed response",
            f"JSON parse error: {e}\nRaw response: {raw_text[:300]}"
        )

    return _validate_and_normalise(parsed)


# ─── Demo / standalone test ──────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick smoke test without real API key
    dummy_case = {
        "case_id": "CASE-017",
        "category": "Routing",
        "title": "Missing Static Route",
        "symptom": "PC cannot reach 192.168.30.0/24",
        "topology": "PC → R1 → R2 → Server",
        "device_context": "R1 missing route to 192.168.30.0/24",
        "show_commands": "show ip route",
        "show_output": (
            "C    10.0.0.0/24 is directly connected, Fa0/1\n"
            "C    192.168.10.0/24 is directly connected, Fa0/0\n"
            "Gateway of last resort is not set"
        ),
        "severity": "high",
    }
    dummy_rules = [
        {"check": "missing_route", "detected": True, "severity": "high",
         "evidence": "192.168.30.0/24 absent", "message": "Route missing"}
    ]
    result = diagnose_case(dummy_case, dummy_rules)
    print(json.dumps(result, indent=2))
