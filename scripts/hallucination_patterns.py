"""
SharkGuard - Anti-hallucination pattern recommendations

A curated subset of prompt patterns (adapted from a course library of 25
anti-hallucination techniques) used to suggest a concrete fix whenever a
hallucination test fails. Not a scoring mechanism - purely advisory,
shown alongside a failed result so a reviewer has somewhere to start
instead of just a red X.

Each pattern includes the template text as-is, since that's the whole
point of a prompt pattern - it's meant to be copied and adapted directly
into the system prompt of the application under test.
"""

PATTERNS = {
    "source_only": {
        "name": "Source-Only Response",
        "effectiveness": 5,
        "when_to_use": "Summarization, document Q&A, report generation from source materials.",
        "template": (
            'Based ONLY on the following source material, answer the question below.\n\n'
            'RULES:\n- Use ONLY information from the provided text\n'
            '- If the answer is not in the text, say "Not found in provided materials"\n'
            '- Do not supplement with outside knowledge\n'
            '- Quote relevant passages using quotation marks\n\n'
            'SOURCE MATERIAL:\n"""\n{your_source_text}\n"""\n\nQUESTION: {your_question}'
        ),
    },
    "data_grounded": {
        "name": "Data-Grounded Analysis",
        "effectiveness": 4,
        "when_to_use": "Financial analysis, data reporting, statistical summaries, numeric facts.",
        "template": (
            "Analyze the following data. Your analysis must:\n"
            "1. Reference ONLY the numbers provided below\n"
            "2. Show calculations for any derived metrics\n"
            "3. Not introduce external benchmarks or comparisons\n"
            "4. Flag any data gaps that limit the analysis\n\n"
            "DATA:\n{your_data}\n\nANALYSIS REQUESTED: {what_you_want_analyzed}\n\n"
            "If you need additional data to complete the analysis, list what is "
            "missing rather than estimating."
        ),
    },
    "permission_unknown": {
        "name": 'Permission to Say "I Don\'t Know"',
        "effectiveness": 4,
        "when_to_use": "Any factual query, especially about niche or recent topics.",
        "template": (
            "Answer the following question honestly. It is completely acceptable "
            'and preferred to say:\n- "I don\'t know"\n- "I\'m not certain about this specific detail"\n'
            '- "This may have changed since my training data"\n- "I cannot verify this claim"\n\n'
            "An honest expression of uncertainty is ALWAYS better than a confident "
            "guess. You will not be penalized for admitting the limits of your "
            "knowledge.\n\nQUESTION: {your_question}"
        ),
    },
    "extraction_only": {
        "name": "Extraction-Only Mode",
        "effectiveness": 5,
        "when_to_use": "Document summarization, data extraction, content analysis, precise facts (dates, symbols, IDs).",
        "template": (
            "You are in EXTRACTION-ONLY MODE. Your only job is to extract "
            "information from the provided text.\n\nYOU MAY:\n- Quote directly from the text\n"
            "- Paraphrase content from the text\n- Organize information from the text\n\n"
            "YOU MAY NOT:\n- Add information not in the text\n- Make inferences beyond what "
            "is explicitly stated\n- Fill gaps with outside knowledge\n- Speculate about what "
            'the text might mean\n\nIf the requested information is not in the text, respond '
            'with "Not present in the provided text."\n\nTEXT:\n"""\n{your_text}\n"""\n\n'
            "EXTRACTION REQUEST: {what_to_extract}"
        ),
    },
    "no_fabrication_citation": {
        "name": "No Fabrication Citation Rule",
        "effectiveness": 4,
        "when_to_use": "Any task requiring citations, sources, named studies, or attributed statistics.",
        "template": (
            "For any claims in your response that would benefit from a citation:\n\n"
            "1. If you can provide a REAL, specific citation you are confident exists, provide it\n"
            '2. If you cannot provide a specific citation, write: "[Source needed — verify independently]"\n'
            "3. NEVER fabricate a citation. A missing citation is infinitely better than a fake one\n\n"
            "Apply this rule to ALL of the following:\n- Academic papers\n- Books\n- URLs/websites\n"
            "- Statistics and data\n- Named studies or reports\n- Quotes attributed to specific "
            "people\n\nQUESTION: {your_question}"
        ),
    },
    "quote_verification": {
        "name": "Quote Verification",
        "effectiveness": 4,
        "when_to_use": "Content that includes quotes, biographical writing, journalism, authorship questions.",
        "template": (
            "If you include any direct quotes in your response:\n\n"
            "1. Provide the attributed speaker/author\n2. Provide the source where the quote appeared\n"
            "3. Rate your confidence that this is the EXACT wording: [Exact] [Approximate] [Paraphrased]\n"
            "4. If you are not confident in the exact wording, use indirect speech instead of "
            "quotation marks\n\nNEVER put words in quotation marks unless you are confident "
            "those are the actual words used.\n\nQUESTION: {your_question}"
        ),
    },
}


def recommend_pattern(question: str, ground_truth: str) -> dict:
    """
    Picks one pattern from PATTERNS that's a reasonable starting point for
    a given failed question, using simple heuristics on the ground truth:
      - a bare number/short symbol -> extraction/data patterns
      - a person's name alongside an authorship-style question -> citation patterns
      - otherwise -> general grounding patterns
    This is a heuristic suggestion, not a guarantee - always sanity-check
    against the actual failure before applying a fix.
    """
    q_lower = question.lower()
    truth = ground_truth.strip()

    is_numeric_or_short_symbol = truth.replace(".", "").replace("-", "").isdigit() or (len(truth) <= 3 and truth.isalpha())
    is_authorship_question = any(w in q_lower for w in ["who wrote", "who said", "quote", "author"])

    if is_authorship_question:
        return PATTERNS["quote_verification"]
    if is_numeric_or_short_symbol:
        return PATTERNS["extraction_only"]
    if "cite" in q_lower or "source" in q_lower or "study" in q_lower:
        return PATTERNS["no_fabrication_citation"]
    return PATTERNS["source_only"]
