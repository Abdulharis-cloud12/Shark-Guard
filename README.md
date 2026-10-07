<<<<<<< HEAD
# 🦈 SharkGuard

### AI Reliability & Security Testing — Stateless, CI/CD-First

> **SharkGuard hunts hallucinations and prompt injections before they ship.**

SharkGuard is an academic semester project developed by a team of four students. It is a stateless testing framework for evaluating the **reliability and security of LLM-powered applications** before deployment.

## 🎯 Core Focus

- AI hallucination and reliability evaluation
- Prompt injection and adversarial testing
- Automated security scanning
- CI/CD-based quality and security gates
- Multi-model comparison
- Stateless API key handling

## 🏗️ Architecture

```text
                  Developer / AI Application
                           │
                           ▼
                    ┌─────────────┐
                    │ GitHub      │
                    │ Actions     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ SharkGuard  │
                    │ Core Engine │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │ Hallucination│  │   Prompt    │  │  Security   │
   │ Evaluation  │  │  Injection  │  │   Scans     │
   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
          │                │                │
          ▼                ▼                ▼
       RAGAS /          Adversarial     Bandit / Trivy
       DeepEval           Tests           / Gitleaks
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                    ┌─────────────┐
                    │   Results   │
                    │  & Scoring  │
                    └──────┬──────┘
                           │
                      ┌────┴────┐
                      ▼         ▼
                    PASS       FAIL
                      │         │
                      ▼         ▼
                  Merge /    Block PR
                  Deploy
```

## 📊 Dashboard

`app.py` is a Streamlit dashboard with two modes, picked in the sidebar:

- **Run live** — configure a model (demo / local Ollama / hosted API) and
  SharkGuard calls it directly from the session. Stateless: any API key
  entered lives only in memory for that run.
- **Load from GitHub Actions** — pulls the exact `hallucination_results.json`
  and `injection_results.json` artifacts the `reliability-eval` CI job
  already produced, instead of spending fresh model calls. Needs a GitHub
  token with `actions:read` (GitHub requires auth to download workflow
  artifacts even on public repos); the token is used only for that fetch
  and is never stored.

Run it with:
=======
# SharkGuard

AI reliability and prompt-injection testing, built as a stateless CI/CD gate.

SharkGuard checks whether an LLM-powered application still gives accurate,
grounded answers and resists prompt injection attacks — automatically, on
every code change, before anything ships.

## Why this exists

A model being "good" (GPT-4, Claude, Gemini) doesn't mean your specific
application — your prompt, your data, your scope — is safe. SharkGuard tests
the application layer, not the model itself.

## Features

- **Hallucination detection** — fixed Q&A set scored with TF-IDF cosine
  similarity (plus an exact-match fast path), not just raw word overlap
- **Prompt injection testing** — two detection modes: fast pattern matching
  (default) or LLM-as-judge for subtler compliance detection
- **Multi-turn conversation testing** — catches consistency breaks and scope
  drift that single-shot tests can't see
- **Multi-model comparison** — run the same test set against two models
  side by side
- **Auto-generated eval questions** — paste reference docs, get a draft
  eval set back (review before trusting it as a CI gate)
- **Custom eval set upload** — bring your own question set via the dashboard
- **Local score history** — opt-in trend chart, stores only aggregate scores
  and timestamps, never keys or prompts
- **CI/CD gate** — GitHub Actions pipeline with a PR comment showing results,
  optional Slack alert on failure, plus Bandit/Trivy/Gitleaks security scans
- **Demo mode** — zero setup, realistic mixed pass/fail results, so you can
  see it work before configuring anything

## Stateless by design

Your API key lives in **your own GitHub Secrets** (CI/CD mode) or your
browser session only (dashboard mode). It never touches SharkGuard's code
beyond that single run, is never logged, and is never sent anywhere outside
your own infrastructure. The one opt-in exception: if you check "Save this
run to local history" in the dashboard, aggregate scores (never keys, never
prompts) are saved locally.

## Project structure

```
sharkguard/
├── .github/workflows/ci.yml      GitHub Actions pipeline
├── .streamlit/config.toml        Dashboard dark theme
├── eval_set/
│   ├── qa_pairs.json             hallucination test questions + ground truth
│   ├── injection_prompts.json    prompt injection sample set (5 items)
│   ├── injection_redteam_set.json  red-team injection set (23 items, see below)
│   ├── multi_turn_set.json       multi-turn conversation test set
│   ├── bias_prompts.json         bias detection test set (6 items)
│   └── image_gen_prompts.json    image-gen test set format (see below)
├── scripts/
│   ├── model_client.py           single/multi-turn model calls, demo mode
│   ├── scoring.py                TF-IDF-based faithfulness scoring
│   ├── run_eval.py                hallucination eval logic
│   ├── injection_test.py         injection resistance logic (2 modes)
│   ├── multi_turn_test.py        multi-turn conversation logic
│   ├── bias_test.py              bias detection logic (LLM-as-judge only)
│   ├── hallucination_patterns.py suggested-fix pattern library
│   ├── generate_eval.py          auto-generate eval questions from text
│   ├── history.py                local, opt-in score history
│   ├── build_summary.py          Markdown summary for PR comments
│   └── image_gen_stub.py         image-gen test structure (NOT wired to a real API)
├── app.py                        Streamlit dashboard
├── requirements.txt
└── README.md
```

## Separate judge model

By default, LLM-as-judge mode (used by `injection_test.py` and always used
by `bias_test.py`) has the **same model under test judge its own
responses**. That works, but it's methodologically weak: a model judging
its own compliance is circular, and if the model is actually compromised
or biased, its verdict on its own compromise or bias can't be fully
trusted.

Set a separate judge model via environment variables (CLI/CI) or the
dashboard's "Use a separate judge model" option:

```
set SHARKGUARD_JUDGE_API_KEY=your-judge-key
set SHARKGUARD_JUDGE_API_BASE=https://api.openai.com/v1
set SHARKGUARD_JUDGE_MODEL=gpt-4o-mini
```

Or for a local Ollama judge: `set SHARKGUARD_JUDGE_OLLAMA_MODEL=llama3.2`.

If none of these are set, judging silently falls back to the same model
under test — nothing breaks, you just don't get the independence benefit.
In CI, add `SHARKGUARD_JUDGE_API_KEY`, `SHARKGUARD_JUDGE_API_BASE`,
`SHARKGUARD_JUDGE_MODEL` as repo secrets to enable it there too.

## Industry starter packs (shift-left AI testing)

In DevSecOps, "shift-left" means catching a problem at the PR stage instead
of after it ships — a bug caught in review costs minutes, the same bug in
production costs an incident. SharkGuard applies the same idea to AI risk,
and these packs give a developer building an industry-specific AI app a
starting eval set that already reflects where that industry's AI mistakes
actually tend to happen — instead of starting from zero and discovering
the risk after a user does.

Five packs, in `eval_set/industry_packs/`, each with domain-specific
hallucination questions and/or compliance tests:

| Industry | Hallucination set | Compliance/injection set |
|---|---|---|
| Healthcare | `healthcare_qa.json` | `healthcare_injection.json` — PHI leakage, unsafe diagnosis/prescribing |
| Legal | `legal_qa.json` | `legal_injection.json` — unauthorized practice, citation fabrication, privilege bypass |
| Financial | `financial_qa.json` | `financial_injection.json` — unlicensed advice, guaranteed-return claims, insider info |
| HR | `hr_qa.json` | `hr_bias.json` — reuses the bias-detection judge, not pattern matching |
| Sales | *(none — no natural "ground truth" trivia for sales)* | `sales_injection.json` — overclaiming, competitor disparagement |

Like the red-team set, most compliance/injection items here ship with an
empty `fail_if_contains` — refusal wording varies too much across these
categories for reliable keyword matching, and a keyword match can even
false-positive on a correct refusal. **Use LLM-as-judge mode for these
packs** — each item carries `judge_criteria` for an accurate call.

Available in the dashboard as "Industry pack" under both the eval set and
injection set sources, or from the CLI:
```
set SHARKGUARD_EVAL_SET=eval_set\industry_packs\healthcare_qa.json
set SHARKGUARD_INJECTION_SET=eval_set\industry_packs\healthcare_injection.json
set SHARKGUARD_INJECTION_JUDGE=llm
python scripts/run_eval.py
python scripts/injection_test.py
```

## Course-material-derived features

Two features adapted from a prompt-engineering course library the team had
access to (most of that library — creative/image/video prompting, career
content, productivity templates — doesn't apply to a testing tool like this
and was left out; see the two entries below for what did apply):

- **Suggested-fix recommendations** (`scripts/hallucination_patterns.py`) —
  when a hallucination test fails, the report suggests one of 6 curated
  prompt patterns (e.g. "Extraction-Only Mode" for a wrong short fact,
  "Quote Verification" for a misattributed quote), with the actual
  template text, adapted from a 25-pattern anti-hallucination library.
  A heuristic match on the question/answer shape, not guaranteed correct —
  a starting point for a fix, not an automatic one.
- **Bias detection** (`scripts/bias_test.py`, `eval_set/bias_prompts.json`) —
  a new test category alongside hallucination/injection, adapted from a
  bias-detection checklist's two most concretely-automatable techniques:
  the **Flip Test** (argue a position two opposite ways, judge whether both
  got comparable rigor) and the **Assumption Audit** (an ambiguous prompt,
  judge whether the response defaults to an unstated gender/culture/age
  norm). Always uses LLM-as-judge — there's no reliable keyword-matching
  equivalent for bias — so it's skipped automatically in demo mode and
  needs a real model configured to produce a result.

## Injection test sets

Two are included:

- **`eval_set/injection_prompts.json`** — 5-item sample, matches the demo mode
  canned responses, good for a quick zero-setup run.
- **`eval_set/injection_redteam_set.json`** — 23 tests adapted from a red-team
  testing checklist (direct injection, jailbreak, prompt leaking, scope
  violation categories). 7 of the original 30 checklist items were template
  placeholders with no concrete prompt text (e.g. "[Gradual topic drift over
  5 messages]") and were left out rather than invented.

  **Important**: demo mode won't produce a meaningful result against this
  set — its canned responses don't match these prompts, so every question
  falls back to a generic non-answer that trivially passes. Point it at a
  real model (Ollama or a hosted API key) to get a real signal.

  Most items in this set ship with an **empty `fail_if_contains`** list —
  refusals for these categories (leaking, scope) vary too much in wording
  for reliable keyword matching, and a keyword match can even false-positive
  on a *correct* refusal (e.g. "I can't share my system prompt" contains the
  words "system prompt"). Use **LLM-as-judge mode** for a meaningful result
  on this set — each item carries a `judge_criteria` field describing what
  counts as resisting, which the judge uses for a more accurate call than
  the generic default.

  To run it from the CLI:
  ```
  set SHARKGUARD_INJECTION_SET=eval_set\injection_redteam_set.json
  set SHARKGUARD_INJECTION_JUDGE=llm
  python scripts/injection_test.py
  ```
  Or in the dashboard: pick **"Red-team set (23 tests)"** as the injection
  source and check **"Use LLM-as-judge for injection scoring"**.

## Local setup

1. Install Python 3.10+ and confirm with `python --version`
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Install [Ollama](https://ollama.com) and pull a free local model (optional
   — demo mode needs none of this):
   ```
   ollama pull llama3.2
   ```

## Running the CI-style scripts locally

```
cd scripts
set SHARKGUARD_DEMO_MODE=true      # Windows. Mac/Linux: export instead
python run_eval.py
python injection_test.py
python multi_turn_test.py
```

Drop `SHARKGUARD_DEMO_MODE` and set `SHARKGUARD_API_KEY`,
`SHARKGUARD_API_BASE`, `SHARKGUARD_MODEL` to test a real model, or run
Ollama locally and leave those unset.

To use LLM-as-judge for injection testing instead of pattern matching:
```
set SHARKGUARD_INJECTION_JUDGE=llm
```

## Running the dashboard

>>>>>>> fb89bd7 (ui finalize with api for testing t)
```
streamlit run app.py
```

<<<<<<< HEAD
## ⚙️ CI Pipeline

`.github/workflows/ci.yml` runs four jobs on every push or PR to `main`:

| Job | What it does |
|---|---|
| `test` | Runs `pytest` |
| `reliability-eval` | Runs the hallucination eval and injection resistance test against a model (demo mode by default; add `SHARKGUARD_API_KEY`/`SHARKGUARD_API_BASE`/`SHARKGUARD_MODEL` as repo secrets to test a real model), uploads the JSON results as the `sharkguard-results` artifact |
| `security` | Bandit, Gitleaks, Trivy (filesystem + built Docker image) |
| `gate` | Runs only if the three jobs above succeed |
=======
Pick **Demo (no setup needed)** in the sidebar for an instant, honest
mixed-result run with no configuration at all.

## Using in your own repo

1. Copy `eval_set/`, `scripts/`, `requirements.txt`, `.streamlit/`,
   `app.py`, and `.github/workflows/ci.yml` into your project.
2. Add your model's API key as a GitHub Secret (Settings → Secrets and
   variables → Actions → New repository secret): `SHARKGUARD_API_KEY`,
   `SHARKGUARD_API_BASE`, `SHARKGUARD_MODEL`.
3. Optional: add `SLACK_WEBHOOK_URL` as a secret to get a Slack alert when
   a build is blocked. Skipped silently if not set.
4. Edit `eval_set/qa_pairs.json` and `eval_set/multi_turn_set.json` with
   questions relevant to your application's scope — or use the dashboard's
   auto-generate feature to draft a starting set from your docs.
5. Push — the pipeline runs automatically on your next PR, and posts a
   results comment directly on it.

## Known gaps (be upfront about these)

- **Image-gen testing** (`scripts/image_gen_stub.py`) defines the test
  format but isn't wired to a real image-generation API or a CLIP-based
  scorer — see the module docstring for exactly what's needed to finish it.
- **Semantic scoring** (`scripts/scoring.py`) uses exact match, then
  key-term recall, then TF-IDF cosine similarity as a fallback — all
  bag-of-words, not deep embeddings. It won't catch a correct answer
  phrased with completely different vocabulary from the ground truth
  (e.g. "1947" vs. "nineteen forty-seven" share no tokens). It also
  won't catch a *negated* wrong answer that reuses the ground truth's
  own words — e.g. "Metformin is NOT typically first-line" against a
  ground truth of "Metformin" scores 1.0, verified by test. This was
  already true of the original exact-match layer before the recall
  layer existed; recall doesn't make it worse, but doesn't fix it
  either. A true embedding-based upgrade would need an extra API call
  per question and would help with both gaps.
  (Previously this used only cosine similarity, which penalized a
  correct answer for containing extra framing words around the fact —
  e.g. a SOAP-note question scored 0.58 and failed despite being fully
  correct. Fixed by adding the key-term recall layer.)
- **LLM-as-judge** for injections and bias detection costs one extra model
  call per attempt and inherits whatever biases the judge model has —
  pattern matching stays the default for injections for that reason. A
  separate judge model (see above) reduces, but doesn't eliminate, this.

## Team

Built by Iadi, with Aditya, Abdul, Rahul, and Karthik.
>>>>>>> fb89bd7 (ui finalize with api for testing t)
