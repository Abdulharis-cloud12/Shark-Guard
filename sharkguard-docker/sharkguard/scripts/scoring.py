"""
SharkGuard - Scoring

Faithfulness scoring used across the CI scripts and dashboard.

Three layers, in order:
  1. Exact containment - if the ground-truth fact appears verbatim in the
     answer, score it 1.0 immediately. The most reliable signal for short
     factual answers, and needs no ML at all.
  2. Key-term recall - what fraction of the ground truth's significant
     words (stopwords like "and"/"the"/"for" removed) appear anywhere in
     the answer. This catches a correct answer that's phrased as a full
     sentence with extra framing around the fact (e.g. "SOAP stands for
     Subjective, Objective, Assessment, and Plan" against a ground truth
     of "Subjective, Objective, Assessment, Plan") - the earlier version
     of this module used only symmetric TF-IDF cosine similarity here,
     which penalizes an answer for containing EXTRA correct words (the
     framing), not just wrong ones, and scored that exact SOAP example
     0.58 - a fail - despite the answer being fully correct.
  3. TF-IDF cosine similarity - a secondary signal for a genuinely
     reworded answer that doesn't share the ground truth's exact tokens.
     The final score is whichever of recall or cosine is higher, since
     either one succeeding is a meaningful signal of a correct answer.

This is still bag-of-words matching, not a deep semantic embedding - it
won't catch a paraphrase with completely different vocabulary (e.g.
"1947" vs "nineteen forty-seven" share no tokens and still score low).
Recall scoring also has its own known trade-off: on a long or rambling
answer, the ground truth's key words could appear scattered for
unrelated reasons and still score as a match - acceptable for
SharkGuard's short factual QA sets, worth knowing if you extend this to
long-form answers. A true embedding-based upgrade (calling an embeddings
API) would catch more of both cases, at the cost of an extra network
call per question - a reasonable next step, not done here to keep
SharkGuard's core scoring free and fully local.
"""

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Minimal English stopword list - just enough to stop common connector
# words from diluting recall matching. Not exhaustive by design; the
# point is filtering "and"/"the"/"for", not full NLP-grade stopword removal.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "as",
    "by", "with", "from",
}


def _key_term_recall(model_answer_lower: str, ground_truth_lower: str) -> float:
    """Fraction of the ground truth's non-stopword tokens found anywhere in the answer."""
    truth_tokens = [t for t in re.findall(r"\w+", ground_truth_lower) if t not in _STOPWORDS]
    if not truth_tokens:
        return 0.0
    answer_tokens = set(re.findall(r"\w+", model_answer_lower))
    matched = sum(1 for t in truth_tokens if t in answer_tokens)
    return matched / len(truth_tokens)


def score_answer(model_answer: str, ground_truth: str) -> float:
    """Faithfulness score, 0.0 to 1.0, between a model answer and ground truth."""
    answer_lower = model_answer.lower().strip()
    truth_lower = ground_truth.lower().strip()

    if not answer_lower or not truth_lower:
        return 0.0

    if truth_lower in answer_lower:
        return 1.0

    recall = _key_term_recall(answer_lower, truth_lower)

    try:
        vectors = TfidfVectorizer().fit_transform([answer_lower, truth_lower])
        similarity = float(cosine_similarity(vectors[0], vectors[1])[0][0])
    except ValueError:
        # Happens if both strings are empty after tokenization (e.g. only
        # punctuation) - treat as no match rather than crashing the eval.
        similarity = 0.0

    return round(max(recall, similarity), 2)
