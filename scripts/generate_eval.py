"""
SharkGuard - Auto-generate an eval set from reference material

Given a block of reference text (e.g. your app's docs, FAQ, or policy
pages) and how many questions you want, asks the model itself to write
question/ground-truth pairs grounded in that text - saving you from
hand-writing every eval question.

The generated set should still be reviewed by a human before it's
trusted as a CI gate - an LLM-generated eval set can itself contain
mistakes, so treat this as a fast first draft, not a final answer.
"""

import json
import re

try:
    from scripts.model_client import call_model
except ImportError:
    from model_client import call_model


def generate_eval_set(reference_text: str, num_questions: int = 5, provider: str = "demo",
                       api_key=None, api_base=None, model=None, ollama_model="llama3.2") -> list:
    """
    Returns a list of {"id", "question", "ground_truth"} dicts grounded in
    reference_text. Raises ValueError if the model's output can't be parsed
    as the expected JSON list - callers should show that error to the user
    rather than silently falling back to a guess.
    """
    prompt = (
        f"Based only on the following reference text, write exactly {num_questions} "
        "factual question-and-answer pairs that could be used to test whether an AI "
        "assistant answers accurately and stays grounded in this text.\n\n"
        f"REFERENCE TEXT:\n{reference_text}\n\n"
        "Respond with ONLY a JSON array, no other text, in exactly this format:\n"
        '[{"question": "...", "ground_truth": "..."}, ...]'
    )

    raw = call_model(prompt, provider=provider, api_key=api_key, api_base=api_base,
                      model=model, ollama_model=ollama_model)

    # Models sometimes wrap JSON in ```json fences despite instructions - strip those.
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find a JSON array in the model's response: {raw[:300]}")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"Model's response wasn't valid JSON: {e}")

    eval_set = []
    for i, item in enumerate(parsed):
        if "question" not in item or "ground_truth" not in item:
            continue  # skip malformed entries rather than failing the whole batch
        eval_set.append({
            "id": f"gen{i+1}",
            "question": item["question"],
            "ground_truth": item["ground_truth"],
        })

    if not eval_set:
        raise ValueError("Model produced no usable question/answer pairs.")

    return eval_set


if __name__ == "__main__":
    # Quick manual test using demo mode - demo mode won't produce real
    # generated questions (it has no matching canned response), so this
    # is meant to be run with a real provider configured.
    sample_text = "SharkGuard is a stateless CI/CD gate that tests LLM applications for hallucinations and prompt injection resistance. It was built by a four-person team."
    try:
        result = generate_eval_set(sample_text, num_questions=3, provider="demo")
        print(json.dumps(result, indent=2))
    except ValueError as e:
        print(f"Expected in demo mode (no real generation available): {e}")
