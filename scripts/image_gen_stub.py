"""
SharkGuard - Image generation testing (STUB - not wired to a real API)

Honest status: this module defines the *shape* of image-gen testing -
the test set format and where scoring would plug in - but does not
call a real image-generation API, because this environment has no
image-generation model to test against and CLIP-based scoring adds a
heavy dependency (torch + a downloaded model) that shouldn't be forced
on everyone using the text-only parts of SharkGuard.

To make this real, you would:
  1. Implement generate_image(prompt, api_key, ...) to call your actual
     image-gen provider (e.g. OpenAI's images API, Stable Diffusion,
     etc.) and return the image bytes or a URL.
  2. Implement score_image(image, expected_description) - the simplest
     real version uses CLIP (pip install transformers torch) to score
     how well the generated image matches a text description, or a
     content-safety classifier to check for disallowed content.
  3. Wire both into a run() function shaped like run_eval.py's, reading
     eval_set/image_gen_prompts.json.

The test set format below already matches what a real implementation
would consume - see eval_set/image_gen_prompts.json.
"""

import json
import os

IMAGE_SET_PATH = os.path.join(os.path.dirname(__file__), "..", "eval_set", "image_gen_prompts.json")


def generate_image(prompt: str, api_key: str = None, api_base: str = None, model: str = None):
    """
    NOT IMPLEMENTED. Wire this to your actual image-generation provider.
    Should return image bytes or a URL that score_image can evaluate.
    """
    raise NotImplementedError(
        "generate_image() is a stub. Connect it to your image-gen API "
        "(e.g. OpenAI images.generate, Stability AI, etc.) to use this module."
    )


def score_image(image, expected_description: str) -> float:
    """
    NOT IMPLEMENTED. A real version would use a CLIP model to score
    prompt-image alignment, or a content-safety classifier to check
    for disallowed content, depending on the test's "type".
    """
    raise NotImplementedError(
        "score_image() is a stub. A real implementation needs a CLIP model "
        "(prompt-image alignment) or a safety classifier (content checks)."
    )


def load_image_test_set() -> list:
    """This part is real and works today - loading the test set itself."""
    with open(IMAGE_SET_PATH) as f:
        return json.load(f)


if __name__ == "__main__":
    test_set = load_image_test_set()
    print(f"Loaded {len(test_set)} image-gen test cases (structure only - see module docstring).")
    for item in test_set:
        print(f"  [{item['type']}] {item['id']}: {item['prompt'][:60]}")
