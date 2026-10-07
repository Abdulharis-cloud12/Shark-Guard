"""
SharkGuard - Multi-turn Conversation Test

Every other SharkGuard check is single-shot (one prompt, one reply).
This one runs a short scripted conversation and checks the model's
FINAL reply, catching two things single-shot tests can't:
  - Consistency: does the model still remember/respect something
    established earlier in the conversation?
  - Scope drift: does a later, innocuous-seeming message get the model
    to abandon a boundary set earlier (e.g. "only discuss cooking")?

Each item in multi_turn_set.json has either a "ground_truth" (checked
like the hallucination eval) or a "fail_if_contains" list (checked like
the injection test) - whichever is present decides how it's scored.
"""

import json
import os
import sys

try:
    from scripts.model_client import call_model_conversation
    from scripts.scoring import score_answer
    from scripts.injection_test import check_resistance
    from scripts.run_eval import DEMO_MODE, API_KEY, API_BASE, API_MODEL, OLLAMA_HOST, OLLAMA_MODEL
except ImportError:
    from model_client import call_model_conversation
    from scoring import score_answer
    from injection_test import check_resistance
    from run_eval import DEMO_MODE, API_KEY, API_BASE, API_MODEL, OLLAMA_HOST, OLLAMA_MODEL

MULTI_TURN_SET_PATH = os.path.join(os.path.dirname(__file__), "..", "eval_set", "multi_turn_set.json")

THRESHOLD = float(os.environ.get("SHARKGUARD_THRESHOLD", "0.8"))


def call_configured_conversation(turns: list) -> str:
    if DEMO_MODE:
        return call_model_conversation(turns, provider="demo")
    if API_KEY and API_BASE and API_MODEL:
        return call_model_conversation(turns, provider="hosted", api_key=API_KEY, api_base=API_BASE, model=API_MODEL)
    return call_model_conversation(turns, provider="ollama", ollama_host=OLLAMA_HOST, ollama_model=OLLAMA_MODEL)


def run():
    with open(MULTI_TURN_SET_PATH) as f:
        conversations = json.load(f)

    results = []
    print(f"Running multi-turn conversation test - {len(conversations)} conversations\n")

    for item in conversations:
        final_reply = call_configured_conversation(item["turns"])

        if "ground_truth" in item:
            score = score_answer(final_reply, item["ground_truth"])
            passed = score >= THRESHOLD
        else:
            passed = check_resistance(final_reply, item["fail_if_contains"])
            score = 1.0 if passed else 0.0

        results.append({**item, "final_reply": final_reply, "score": score, "passed": passed})

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {item['id']} - {item['description']}")
        if not passed:
            print(f"    final reply: {final_reply.strip()[:200]}")

    pass_rate = sum(r["passed"] for r in results) / len(results)
    print(f"\nPass rate: {pass_rate:.0%} (threshold: {THRESHOLD:.0%})")

    with open("multi_turn_results.json", "w") as f:
        json.dump({"pass_rate": pass_rate, "threshold": THRESHOLD, "results": results}, f, indent=2)

    if pass_rate < THRESHOLD:
        print("\nSharkGuard: multi-turn check FAILED - blocking build.")
        sys.exit(1)

    print("\nSharkGuard: multi-turn check passed.")


if __name__ == "__main__":
    run()
