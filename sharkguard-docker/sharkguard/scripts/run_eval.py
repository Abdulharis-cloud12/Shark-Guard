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
    from scripts.model_client import call_model  # imported as a package, e.g. from app.py
    from scripts.scoring import score_answer
    from scripts.hallucination_patterns import recommend_pattern
    from scripts.rag_firewall_adapter import firewall_metadata, summarize_agreement, format_agreement
except ImportError:
    from model_client import call_model  # run directly, e.g. `python run_eval.py`
    from scoring import score_answer
    from hallucination_patterns import recommend_pattern
    from rag_firewall_adapter import firewall_metadata, summarize_agreement, format_agreement

DEFAULT_EVAL_SET = os.path.join(os.path.dirname(__file__), "..", "eval_set", "qa_pairs.json")
EVAL_SET_PATH = os.environ.get("SHARKGUARD_EVAL_SET", DEFAULT_EVAL_SET)

# Minimum fraction of questions that must pass for the build to succeed.
THRESHOLD = float(os.environ.get("SHARKGUARD_THRESHOLD", "0.8"))

DEMO_MODE = os.environ.get("SHARKGUARD_DEMO_MODE", "false").lower() == "true"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

API_KEY = os.environ.get("SHARKGUARD_API_KEY")
API_BASE = os.environ.get("SHARKGUARD_API_BASE")
API_MODEL = os.environ.get("SHARKGUARD_MODEL")

# Optional separate judge model, used by injection_test.py and bias_test.py
# for their LLM-as-judge checks. If unset, judging falls back to the same
# model under test - which works, but has a real weakness: a model judging
# its own compliance/bias is circular, and a compromised model's verdict on
# its own compromise can't be fully trusted. Set these to use a different,
# ideally more capable or more consistent model as the judge instead.
JUDGE_API_KEY = os.environ.get("SHARKGUARD_JUDGE_API_KEY")
JUDGE_API_BASE = os.environ.get("SHARKGUARD_JUDGE_API_BASE")
JUDGE_MODEL = os.environ.get("SHARKGUARD_JUDGE_MODEL")
JUDGE_OLLAMA_MODEL = os.environ.get("SHARKGUARD_JUDGE_OLLAMA_MODEL")

# Optional: test a whole RAG system instead of a bare model. Point this at a
# clone of RAG-Hallucination-Firewall; every question then goes through its
# retrieval + generation + 3-stage firewall, and the firewall's own risk
# label is recorded next to SharkGuard's verdict. See README "RAG Firewall".
RAG_FIREWALL_PATH = os.environ.get("SHARKGUARD_RAG_FIREWALL_PATH")
RAG_FIREWALL_PYTHON = os.environ.get("SHARKGUARD_RAG_FIREWALL_PYTHON")
USING_RAG_FIREWALL = bool(RAG_FIREWALL_PATH) and not DEMO_MODE

USING_SEPARATE_JUDGE = bool((JUDGE_API_KEY and JUDGE_API_BASE and JUDGE_MODEL) or JUDGE_OLLAMA_MODEL)


def call_configured_model(prompt: str) -> str:
    """Send a prompt using whichever model is configured via environment variables."""
    if DEMO_MODE:
        return call_model(prompt, provider="demo")
    if USING_RAG_FIREWALL:
        return call_model(prompt, provider="rag_firewall",
                          rag_firewall_path=RAG_FIREWALL_PATH, rag_firewall_python=RAG_FIREWALL_PYTHON)
    if API_KEY and API_BASE and API_MODEL:
        return call_model(prompt, provider="hosted", api_key=API_KEY, api_base=API_BASE, model=API_MODEL)
    return call_model(prompt, provider="ollama", ollama_host=OLLAMA_HOST, ollama_model=OLLAMA_MODEL)


def call_configured_judge_model(prompt: str) -> str:
    """
    Sends a judging prompt to the separately-configured judge model if one
    is set (SHARKGUARD_JUDGE_* env vars), otherwise falls back to the same
    model under test. Demo mode always uses demo responses regardless of
    judge config, since canned answers can't be meaningfully judged either way.
    """
    if DEMO_MODE:
        return call_model(prompt, provider="demo")
    if JUDGE_API_KEY and JUDGE_API_BASE and JUDGE_MODEL:
        return call_model(prompt, provider="hosted", api_key=JUDGE_API_KEY, api_base=JUDGE_API_BASE, model=JUDGE_MODEL)
    if JUDGE_OLLAMA_MODEL:
        return call_model(prompt, provider="ollama", ollama_host=OLLAMA_HOST, ollama_model=JUDGE_OLLAMA_MODEL)
    if USING_RAG_FIREWALL:
        # Falling back to "the model under test" would mean pushing the judge
        # prompt through retrieval + the firewall - it would answer from the
        # corpus, not judge anything. A judge must be a plain model.
        raise ValueError(
            "LLM-as-judge needs a separate judge model when testing the RAG Firewall. "
            "Set SHARKGUARD_JUDGE_API_KEY / _API_BASE / _MODEL (or SHARKGUARD_JUDGE_OLLAMA_MODEL).")
    return call_configured_model(prompt)  # no separate judge configured - fall back


def run():
    with open(EVAL_SET_PATH) as f:
        eval_set = json.load(f)

    results = []
    print(f"Running hallucination eval - {len(eval_set)} questions\n")

    for item in eval_set:
        answer = call_configured_model(item["question"])
        score = score_answer(answer, item["ground_truth"])
        passed = score >= THRESHOLD
        row = {**item, "model_answer": answer, "score": score, "passed": passed}
        fw = firewall_metadata(item["question"]) if USING_RAG_FIREWALL else None
        if fw:
            row["firewall"] = fw

        status = "PASS" if passed else "FAIL"
        fw_note = f"  [firewall: {fw['risk_label']}]" if fw else ""
        print(f"[{status}] {item['id']} - score {score:.2f} - {item['question']}{fw_note}")
        if not passed:
            suggested = recommend_pattern(item["question"], item["ground_truth"])
            row["suggested_pattern"] = suggested["name"]
            print(f"    expected to contain: {item['ground_truth']}")
            print(f"    model answered:      {answer.strip()[:200]}")
            print(f"    suggested fix:       {suggested['name']} ({suggested['effectiveness']}/5) "
                  f"- {suggested['when_to_use']}")
        results.append(row)

    pass_rate = sum(r["passed"] for r in results) / len(results)
    print(f"\nPass rate: {pass_rate:.0%} (threshold: {THRESHOLD:.0%})")

    payload = {"pass_rate": pass_rate, "threshold": THRESHOLD, "results": results}
    if USING_RAG_FIREWALL:
        agreement = summarize_agreement((r["passed"], (r.get("firewall") or {}).get("risk_label")) for r in results)
        payload["rag_firewall"] = True
        payload["firewall_agreement"] = agreement
        print(format_agreement(agreement))
    with open("hallucination_results.json", "w") as f:
        json.dump(payload, f, indent=2)

    if pass_rate < THRESHOLD:
        print("\nSharkGuard: hallucination check FAILED - blocking build.")
        sys.exit(1)

    print("\nSharkGuard: hallucination check passed.")


if __name__ == "__main__":
    run()
