"""Build a Markdown summary from SharkGuard evaluation result files.

The CI gate fails closed when required evaluation output is missing or invalid.
Bias evaluation is optional because it is intentionally skipped in demo mode and
when testing systems that cannot be meaningfully assessed by the bias judge.
"""

import json
import os
from typing import Any

FILES = {
    "Hallucination": ("hallucination_results.json", "pass_rate", True),
    "Injection resistance": ("injection_results.json", "resistance_rate", True),
    "Multi-turn": ("multi_turn_results.json", "pass_rate", True),
    "Bias detection": ("bias_results.json", "pass_rate", False),
}


def _load_result(filename: str) -> dict[str, Any]:
    with open(filename, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("result must be a JSON object")
    return data


def build_summary() -> str:
    lines = ["## 🦈 SharkGuard Results\n"]
    any_failed = False
    found_any = False
    missing_required = []

    for label, (filename, rate_key, required) in FILES.items():
        if not os.path.exists(filename):
            if required:
                missing_required.append(filename)
            else:
                lines.append(f"- ⚪ **{label}**: skipped (optional result file not present)")
            continue

        found_any = True
        try:
            data = _load_result(filename)
            rate = float(data[rate_key])
            threshold = float(data["threshold"])
            if not 0 <= rate <= 1 or not 0 <= threshold <= 1:
                raise ValueError("rate and threshold must be between 0 and 1")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            any_failed = True
            lines.append(f"- ❌ **{label}**: invalid result file ({exc})")
            continue

        passed = rate >= threshold
        any_failed = any_failed or not passed
        icon = "✅" if passed else "❌"
        lines.append(f"- {icon} **{label}**: {rate:.0%} (threshold {threshold:.0%})")
        agreement = data.get("firewall_agreement")
        if data.get("rag_firewall") and isinstance(agreement, dict) and agreement.get("total"):
            agree = agreement.get("both_ok", 0) + agreement.get("both_bad", 0)
            lines.append(
                f"  - RAG Firewall cross-check: agrees on {agree}/{agreement['total']} answers; "
                f"{agreement.get('sharkguard_only_bad', 0)} failed here but the firewall rated LOW, "
                f"{agreement.get('firewall_only_flagged', 0)} flagged by the firewall only "
                f"(review list, not a verdict)"
            )

    if missing_required:
        any_failed = True
        lines.append("\n- ❌ **Required results missing**: " + ", ".join(missing_required))

    if not found_any and not missing_required:
        any_failed = True
        lines.append("No result files found; refusing to mark the build as passed.")

    lines.append("")
    lines.append("**Overall: BUILD BLOCKED**" if any_failed else "**Overall: BUILD PASSED**")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(build_summary())
