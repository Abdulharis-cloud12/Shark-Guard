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
```
streamlit run app.py
```

## ⚙️ CI Pipeline

`.github/workflows/ci.yml` runs four jobs on every push or PR to `main`:

| Job | What it does |
|---|---|
| `test` | Runs `pytest` |
| `reliability-eval` | Runs the hallucination eval and injection resistance test against a model (demo mode by default; add `SHARKGUARD_API_KEY`/`SHARKGUARD_API_BASE`/`SHARKGUARD_MODEL` as repo secrets to test a real model), uploads the JSON results as the `sharkguard-results` artifact |
| `security` | Bandit, Gitleaks, Trivy (filesystem + built Docker image) |
| `gate` | Runs only if the three jobs above succeed |
