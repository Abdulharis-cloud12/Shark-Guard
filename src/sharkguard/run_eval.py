"""
SharkGuard - Hallucination Evaluation

Runs a fixed set of question/answer pairs against a model and checks
whether the model's answer actually contains the correct, ground-truth
fact. Exits with a non-zero code if the pass rate falls below the
threshold, so this can be used as a CI gate.

Three ways to reach a model, checked in this order:
  1. Demo mode - set SHARKGUARD_DEMO_MODE=true to run with zero setup,
     using realistic canned responses. Good for a first demo run or a
     public repo where you don't want to require secrets.
  2. Hosted API (OpenAI-compatible) - set SHARKGUARD_API_KEY and
     SHARKGUARD_API_BASE and SHARKGUARD_MODEL as environment variables.
  3. Local Ollama - used automatically if the above are not set.
     Requires Ollama running locally (`ollama serve`, usually automatic
     after install) with a model already pulled, e.g. `ollama pull llama3.2`.
"""

import json
import os
import sys

try:
    from src.sharkguard.model_client import call_model  # imported as a package, e.g. `python -m src.sharkguard.run_eval` or from app.py
except ImportError:
    from model_client import call_model  # run directly from inside src/sharkguard/, e.g. `python run_eval.py`

# src/sharkguard/run_eval.py -> src/sharkguard -> src -> repo root -> eval_set/
EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "eval_set", "qa_pairs.json")

# Minimum fraction of questions that must pass for the build to succeed.
THRESHOLD = float(os.environ.get("SHARKGUARD_THRESHOLD", "0.8"))

DEMO_MODE = os.environ.get("SHARKGUARD_DEMO_MODE", "false").lower() == "true"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

API_KEY = os.environ.get("SHARKGUARD_API_KEY")
API_BASE = os.environ.get("SHARKGUARD_API_BASE")
API_MODEL = os.environ.get("SHARKGUARD_MODEL")


def call_configured_model(prompt: str) -> str:
    """Send a prompt using whichever model is configured via environment variables."""
    if DEMO_MODE:
        return call_model(prompt, provider="demo")
    if API_KEY and API_BASE and API_MODEL:
        return call_model(prompt, provider="hosted", api_key=API_KEY, api_base=API_BASE, model=API_MODEL)
    return call_model(prompt, provider="ollama", ollama_host=OLLAMA_HOST, ollama_model=OLLAMA_MODEL)


def score_answer(model_answer: str, ground_truth: str) -> float:
    """
    Custom faithfulness score, 0.0 to 1.0.

    Primary check: does the exact ground-truth fact appear in the answer?
    That alone gives a clean pass/fail for short factual questions.
    Fallback: word-overlap ratio, so a partially-correct answer still
    gets partial credit instead of an all-or-nothing score.
    """
    answer_lower = model_answer.lower()
    truth_lower = ground_truth.lower()

    if truth_lower in answer_lower:
        return 1.0

    truth_words = set(truth_lower.split())
    answer_words = set(answer_lower.split())
    if not truth_words:
        return 0.0
    overlap = len(truth_words & answer_words) / len(truth_words)
    return round(overlap, 2)


def run():
    with open(EVAL_SET_PATH) as f:
        eval_set = json.load(f)

    results = []
    print(f"Running hallucination eval - {len(eval_set)} questions\n")

    for item in eval_set:
        answer = call_configured_model(item["question"])
        score = score_answer(answer, item["ground_truth"])
        passed = score >= THRESHOLD
        results.append({**item, "model_answer": answer, "score": score, "passed": passed})

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {item['id']} - score {score:.2f} - {item['question']}")
        if not passed:
            print(f"    expected to contain: {item['ground_truth']}")
            print(f"    model answered:      {answer.strip()[:200]}")

    pass_rate = sum(r["passed"] for r in results) / len(results)
    print(f"\nPass rate: {pass_rate:.0%} (threshold: {THRESHOLD:.0%})")

    with open("hallucination_results.json", "w") as f:
        json.dump({"pass_rate": pass_rate, "threshold": THRESHOLD, "results": results}, f, indent=2)

    if pass_rate < THRESHOLD:
        print("\nSharkGuard: hallucination check FAILED - blocking build.")
        sys.exit(1)

    print("\nSharkGuard: hallucination check passed.")


if __name__ == "__main__":
    run()
