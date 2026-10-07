"""
SharkGuard - Build a Markdown summary from the result JSON files

Reads whichever of hallucination_results.json, injection_results.json,
and multi_turn_results.json exist in the current directory and writes
a single Markdown report - used both for the GitHub Actions step
summary and for posting a PR comment.
"""

import json
import os

FILES = {
    "Hallucination": ("hallucination_results.json", "pass_rate"),
    "Injection resistance": ("injection_results.json", "resistance_rate"),
    "Multi-turn": ("multi_turn_results.json", "pass_rate"),
    "Bias detection": ("bias_results.json", "pass_rate"),
}


def build_summary() -> str:
    lines = ["## 🦈 SharkGuard Results\n"]
    any_failed = False
    found_any = False

    for label, (filename, rate_key) in FILES.items():
        if not os.path.exists(filename):
            continue
        found_any = True
        with open(filename) as f:
            data = json.load(f)
        rate = data[rate_key]
        threshold = data["threshold"]
        passed = rate >= threshold
        any_failed = any_failed or not passed
        icon = "✅" if passed else "❌"
        lines.append(f"- {icon} **{label}**: {rate:.0%} (threshold {threshold:.0%})")

    if not found_any:
        return "## 🦈 SharkGuard Results\n\nNo result files found.\n"

    lines.append("")
    lines.append("**Overall: BUILD BLOCKED**" if any_failed else "**Overall: BUILD PASSED**")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(build_summary())
