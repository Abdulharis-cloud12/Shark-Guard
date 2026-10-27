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
- **RAG Firewall integration** — test a whole RAG system (retrieval + generation +
  3-stage hallucination firewall) and compare its risk labels with SharkGuard's verdicts
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
│   ├── rag_firewall_qa.json      16 in-corpus questions for the RAG Firewall (see below)
│   ├── rag_firewall_scope.json   12 out-of-corpus questions the RAG Firewall should refuse
│   └── image_gen_prompts.json    image-gen test set format (see below)
├── scripts/
│   ├── model_client.py           single/multi-turn model calls, demo mode
│   ├── scoring.py                TF-IDF-based faithfulness scoring
│   ├── run_eval.py                hallucination eval logic
│   ├── injection_test.py         injection resistance logic (2 modes)
│   ├── multi_turn_test.py        multi-turn conversation logic
│   ├── bias_test.py              bias detection logic (LLM-as-judge only)
│   ├── rag_firewall_adapter.py   runs the RAG Firewall as a subprocess (stdlib only)
│   ├── rag_firewall_worker.py    runs INSIDE the firewall's environment, not SharkGuard's
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

```
streamlit run app.py
```

Pick **Demo (no setup needed)** in the sidebar for an instant, honest
mixed-result run with no configuration at all.

## Running with Docker

One image runs both modes. It holds no secrets and no volumes, runs as a
non-root user, and the compose file mounts the root filesystem read-only.

```
docker compose up --build                  # dashboard at http://localhost:8501
docker compose --profile ci run --rm ci    # the CI-style gate, demo mode
```

The `ci` service runs the hallucination, injection and multi-turn checks, then
prints the summary, and its exit code is the gate (non-zero = build blocked),
same as the GitHub Actions job. To test a real model, export
`SHARKGUARD_API_KEY`, `SHARKGUARD_API_BASE`, `SHARKGUARD_MODEL` and
`SHARKGUARD_DEMO_MODE=false` in your shell (or a git-ignored `.env`) first;
compose passes them through and nothing is baked into the image.

Or without compose:
```
docker build -t sharkguard .
docker run --rm -p 8501:8501 sharkguard
docker run --rm -e SHARKGUARD_DEMO_MODE=true sharkguard python scripts/run_eval.py
```

### Publish to Docker Hub

Replace `YOUR_DOCKERHUB_USERNAME` with your Docker Hub username. Create the repository
`sharkguard` on Docker Hub first, then run these commands from the project root:

```powershell
# Sign in interactively; Docker prompts for credentials/token.
docker login

# Build and tag the image.
docker build -t YOUR_DOCKERHUB_USERNAME/sharkguard:1.0.0 .
docker tag YOUR_DOCKERHUB_USERNAME/sharkguard:1.0.0 YOUR_DOCKERHUB_USERNAME/sharkguard:latest

# Push both tags.
docker push YOUR_DOCKERHUB_USERNAME/sharkguard:1.0.0
docker push YOUR_DOCKERHUB_USERNAME/sharkguard:latest

# Pull and run the published image.
docker pull YOUR_DOCKERHUB_USERNAME/sharkguard:latest
docker run --rm -p 8501:8501 YOUR_DOCKERHUB_USERNAME/sharkguard:latest
```

Open `http://localhost:8501`. Do not put API keys in the image or commit `.env`; pass
secrets at runtime with `--env-file .env` or environment variables. Use a real model
configuration for meaningful quality/security evaluation. Demo mode deliberately returns
some failures so it demonstrates that the gate catches unsafe or incorrect behavior.

Notes:
- **Ollama** runs on your machine, not in the container. The image reaches it at
  `host.docker.internal:11434` (Docker Desktop on Windows/Mac; compose also maps
  the name on Linux). Override with `OLLAMA_HOST`. On Linux Ollama must listen
  on more than localhost (`OLLAMA_HOST=0.0.0.0`) for the container to reach it.
- **Opt-in score history** is written to the container's `/tmp`, so it disappears
  when the container stops. That is deliberate and keeps the stateless promise.
- **RAG Firewall mode is not supported in this image.** It needs the firewall's
  own environment (torch, FAISS, LangChain) and index; run that mode directly on
  your machine as described above.
- Docker image builds must be run on a machine with Docker Engine/Desktop installed.
  This repository's CI checks Python syntax and summary logic; run the Docker commands above
  locally before publishing an image.

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

## Testing a RAG system: the RAG Firewall integration

[RAG-Hallucination-Firewall](https://github.com/swathi-2406/RAG-Hallucination-Firewall)
is a RAG pipeline (FAISS retrieval + DeepSeek generation) with a 3-stage
hallucination detector (semantic entropy, JSD, NLI). SharkGuard can test that
whole system instead of a bare model: each question goes through the
firewall's real `retrieve -> run_firewall` pipeline, SharkGuard scores the
**answer** the way it scores any model's answer, and the firewall's **own
risk label** is recorded beside it.

Why both: the two checkers fail differently. SharkGuard checks the answer
against ground truth or a refusal expectation; the firewall checks the answer
against the retrieved context. The agreement summary lists where they
disagree, which is a **review list, not a verdict on either tool**:

| Bucket | Meaning |
|---|---|
| both OK / both flagged | the two agree |
| firewall missed | SharkGuard failed the answer, firewall said LOW |
| firewall-only flags | firewall flagged it, SharkGuard passed it: a false alarm, or something keyword/pattern checks can't see |

**Setup (once):** clone the firewall repo, give it its own environment
(`pip install -r requirements.txt` there), put its DeepSeek key in its own
`.env`, and build its index with `python scripts/ingest_docs.py`. SharkGuard
never installs torch, FAISS or LangChain; it launches the firewall's Python as
a separate long-lived process, so the NLI model loads once per run.

```bash
export SHARKGUARD_RAG_FIREWALL_PATH=/path/to/RAG-Hallucination-Firewall
# optional: the firewall's interpreter (default: its .venv or venv if present)
export SHARKGUARD_RAG_FIREWALL_PYTHON=/path/to/RAG-Hallucination-Firewall/.venv/bin/python

SHARKGUARD_EVAL_SET=eval_set/rag_firewall_qa.json python scripts/run_eval.py
SHARKGUARD_INJECTION_SET=eval_set/rag_firewall_scope.json python scripts/injection_test.py
```

Or pick **RAG Firewall (local)** as the provider in the dashboard, enter the
path, and choose **RAG Firewall pack** for both question sets.

Notes and limits:
- **Judge:** with the firewall as the system under test, LLM-as-judge needs a
  *separate* judge model (`SHARKGUARD_JUDGE_*`). Pushing a judge prompt
  through retrieval would just get it answered from the corpus. Without one,
  the scope test falls back to pattern mode and says so; 5 of the 12 scope
  questions have no safe keyword and are only meaningful with a judge.
- `multi_turn_test.py` and `bias_test.py` skip themselves (exit 0) in this
  mode: the firewall is single-turn and corpus-bound.
- Environment variables: `SHARKGUARD_RAG_FIREWALL_STARTUP_TIMEOUT` (default 300 s,
  index + model load) and `SHARKGUARD_RAG_FIREWALL_TIMEOUT` (default 180 s per question).
  A crashed or timed-out worker is restarted on the next question.
- Not wired into `ci.yml` on purpose: a GitHub-hosted runner would need torch,
  the NLI model download, a built index and a DeepSeek secret on every run. Run
  it locally, on a self-hosted runner, or as a workflow in the firewall's own repo.
- The in-corpus questions are the firewall's own evaluation questions, so
  expect them to be the *easy* case for it; the scope questions are the better stress test.
- Tested against a stand-in with the same interface (errors, crashes, timeouts,
  noisy stdout), **not yet against the real firewall**. The first real run is the real test.

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


## Docker Compose with Ollama (local LLM)

The Compose stack runs the SharkGuard dashboard and Ollama in separate containers. The first `docker compose up --build` downloads the model configured by `OLLAMA_MODEL` (default `llama3.2:3b`) into a persistent Docker volume. This download can take several minutes and requires enough disk space and RAM.

```powershell
# Optional: select a different model before startup
$env:OLLAMA_MODEL = "llama3.2:3b"

docker compose up --build -d
docker compose ps
docker compose logs -f dashboard
```

Open <http://localhost:8501>, choose **Local (Ollama)** in the sidebar, and use the same model name configured in `OLLAMA_MODEL`. Ollama's API is also exposed on `http://localhost:11434` for local development. Model weights are persisted in the `ollama_data` volume and are not baked into the SharkGuard Docker image, so publishing the SharkGuard image to Docker Hub does not upload the model weights.

To stop the stack without deleting the downloaded model:

```powershell
docker compose down
```

To remove the downloaded model volume as well (destructive):

```powershell
docker compose down -v
```

The `ci` Compose profile also uses the Ollama service and model initialization. The default demo evaluation mode is separate from real-model testing.
