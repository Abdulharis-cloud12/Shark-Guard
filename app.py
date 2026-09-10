"""
SharkGuard Dashboard

An interactive dashboard for testing an LLM application's reliability
(hallucination) and security (prompt injection resistance).

Two ways to see results:
  1. Run live - configure a model in the sidebar and SharkGuard calls it
     directly from this session. Stateless: API keys live only in memory
     for the duration of the run and are never written to disk or logged.
  2. Load from GitHub Actions - pull the exact hallucination_results.json /
     injection_results.json artifacts your own CI pipeline's
     `reliability-eval` job already produced, instead of paying for a
     fresh set of model calls. Needs a GitHub token with `actions:read`;
     the token is used only for this fetch and is never stored.

Run locally with:
    streamlit run app.py
"""

import io
import json
import os
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from src.sharkguard.model_client import call_model
from src.sharkguard.run_eval import score_answer
from src.sharkguard.injection_test import check_resistance

EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set", "qa_pairs.json")
INJECTION_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set", "injection_prompts.json")

GITHUB_API = "https://api.github.com"

st.set_page_config(page_title="SharkGuard", layout="centered", page_icon="\U0001F988")


@st.cache_data
def load_eval_set():
    with open(EVAL_SET_PATH) as f:
        return json.load(f)


@st.cache_data
def load_injection_set():
    with open(INJECTION_SET_PATH) as f:
        return json.load(f)


def badge(text, kind):
    """kind: 'pass' or 'fail' -> a small colored pill, rendered as HTML."""
    colors = {
        "pass": ("#0f6e56", "#0d3d33"),
        "fail": ("#e35d5d", "#3d1414"),
    }
    fg, bg = colors[kind]
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;"
        f"border-radius:999px;font-size:12px;font-weight:600'>{text}</span>"
    )


def run_model_suite(provider, api_key, api_base, model, threshold, ollama_model="llama3.2", progress_cb=None):
    """Runs both test sets against one model. Returns a results dict.
    progress_cb(fraction, message), if given, is called after each step."""
    qa_pairs = load_eval_set()
    injections = load_injection_set()
    total_steps = len(qa_pairs) + len(injections)
    done = 0

    hallucination_rows = []
    for item in qa_pairs:
        answer = call_model(
            item["question"], provider=provider, api_key=api_key,
            api_base=api_base, model=model, ollama_model=ollama_model,
        )
        score = score_answer(answer, item["ground_truth"])
        hallucination_rows.append({
            "question": item["question"], "score": score,
            "passed": score >= threshold, "answer": answer,
            "ground_truth": item["ground_truth"],
        })
        done += 1
        if progress_cb:
            progress_cb(done / total_steps, f"Hallucination check {done}/{len(qa_pairs)}")

    injection_rows = []
    for item in injections:
        answer = call_model(
            item["prompt"], provider=provider, api_key=api_key,
            api_base=api_base, model=model, ollama_model=ollama_model,
        )
        resisted = check_resistance(answer, item["fail_if_contains"])
        injection_rows.append({
            "type": item["type"], "resisted": resisted, "answer": answer,
            "prompt": item["prompt"],
        })
        done += 1
        if progress_cb:
            idx = done - len(qa_pairs)
            progress_cb(done / total_steps, f"Injection check {idx}/{len(injections)}")

    faithfulness = sum(r["score"] for r in hallucination_rows) / len(hallucination_rows)
    resistance = sum(r["resisted"] for r in injection_rows) / len(injection_rows)

    return {
        "faithfulness": faithfulness,
        "resistance": resistance,
        "hallucination_rows": hallucination_rows,
        "injection_rows": injection_rows,
    }


def fetch_ci_run(owner, repo, token, workflow_file="ci.yml", branch=None, run_id=None):
    """
    Pulls the result artifacts the `reliability-eval` job in ci.yml already
    produced for a real pipeline run, instead of calling a model from here.

    GitHub requires an authenticated request to download workflow artifacts,
    even on public repos, so a token is always required. A classic PAT with
    the `repo` scope (or a fine-grained token with Actions: Read) is enough.
    The token is used only for these requests and is never written to disk.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if run_id:
        resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}",
                             headers=headers, timeout=30)
        resp.raise_for_status()
        run = resp.json()
    else:
        params = {"status": "completed", "per_page": 1}
        if branch:
            params["branch"] = branch
        resp = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs",
            headers=headers, params=params, timeout=30,
        )
        resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])
        if not runs:
            where = f" on branch '{branch}'" if branch else ""
            raise RuntimeError(f"No completed runs found for workflow '{workflow_file}'{where}.")
        run = runs[0]

    artifacts_resp = requests.get(run["artifacts_url"], headers=headers, timeout=30)
    artifacts_resp.raise_for_status()
    artifacts = artifacts_resp.json().get("artifacts", [])
    if not artifacts:
        raise RuntimeError("This run has no uploaded artifacts. Has the 'reliability-eval' job run yet?")

    hallucination_data = injection_data = None
    for artifact in artifacts:
        if artifact.get("expired"):
            continue
        dl = requests.get(artifact["archive_download_url"], headers=headers, timeout=60)
        dl.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            for name in zf.namelist():
                if name.endswith("hallucination_results.json"):
                    hallucination_data = json.loads(zf.read(name))
                elif name.endswith("injection_results.json"):
                    injection_data = json.loads(zf.read(name))

    if hallucination_data is None or injection_data is None:
        missing = [n for n, v in [("hallucination_results.json", hallucination_data),
                                   ("injection_results.json", injection_data)] if v is None]
        raise RuntimeError(
            "Couldn't find " + " and ".join(missing) + " in this run's artifacts "
            "(they may have expired, or the eval job didn't finish)."
        )

    return {
        "run_number": run["run_number"],
        "run_url": run["html_url"],
        "commit_sha": run["head_sha"][:7],
        "branch": run.get("head_branch"),
        "conclusion": run.get("conclusion") or "in progress",
        "created_at": run.get("created_at"),
        "hallucination": hallucination_data,
        "injection": injection_data,
    }


def normalize_ci_results(ci):
    """Reshapes the CI JSON artifacts into the same row format run_model_suite()
    produces, so render_results() can draw both live and CI-pulled data."""
    hallucination_rows = [
        {
            "question": r["question"], "score": r["score"], "passed": r["passed"],
            "answer": r["model_answer"], "ground_truth": r["ground_truth"],
        }
        for r in ci["hallucination"]["results"]
    ]
    injection_rows = [
        {
            "type": r["type"], "resisted": r["resisted"],
            "answer": r["model_answer"], "prompt": r["prompt"],
        }
        for r in ci["injection"]["results"]
    ]
    faithfulness = sum(r["score"] for r in hallucination_rows) / len(hallucination_rows)
    resistance = sum(r["resisted"] for r in injection_rows) / len(injection_rows)
    return faithfulness, resistance, hallucination_rows, injection_rows


def render_results(faithfulness, resistance, faithfulness_threshold, resistance_threshold,
                    hallucination_rows, injection_rows, comparison_df=None, report_extra=None):
    """Draws the gate banner, metrics, reports, and download button. Shared by
    both the live-run path and the CI-pulled path so they render identically."""
    gate_pass = faithfulness >= faithfulness_threshold and resistance >= resistance_threshold
    n_hallu_fail = sum(not r["passed"] for r in hallucination_rows)
    n_inj_fail = sum(not r["resisted"] for r in injection_rows)

    if gate_pass:
        st.success("**BUILD PASSED** — no hallucinations or injection failures above threshold.")
    else:
        st.error(f"**BUILD BLOCKED** — {n_hallu_fail} hallucination(s), {n_inj_fail} injection failure(s) detected.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Faithfulness", f"{faithfulness:.2f}")
    m2.metric("Injection resistance", f"{resistance:.0%}")
    m3.metric("Gate status", "Pass" if gate_pass else "Fail")

    if comparison_df is not None:
        st.markdown("#### Model comparison")
        st.bar_chart(comparison_df)

    st.markdown("#### Hallucination report")
    for row in hallucination_rows:
        kind = "pass" if row["passed"] else "fail"
        c1, c2, c3 = st.columns([5, 1, 1])
        c1.write(row["question"])
        c2.write(f"{row['score']:.2f}")
        c3.markdown(badge("Pass" if row["passed"] else "Fail", kind), unsafe_allow_html=True)
        if not row["passed"]:
            with st.expander("Why did this fail?"):
                st.write(f"**Expected to contain:** {row['ground_truth']}")
                st.write(f"**Model answered:** {row['answer']}")

    st.markdown("#### Injection report")
    for row in injection_rows:
        kind = "pass" if row["resisted"] else "fail"
        c1, c2 = st.columns([5, 2])
        c1.write(row["type"].replace("_", " ").title())
        c2.markdown(badge("Resisted" if row["resisted"] else "Compromised", kind), unsafe_allow_html=True)
        if not row["resisted"]:
            with st.expander("See the compromised response"):
                st.write(f"**Prompt:** {row['prompt']}")
                st.write(f"**Model answered:** {row['answer']}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_passed": gate_pass,
        "faithfulness": faithfulness,
        "injection_resistance": resistance,
        "hallucination_results": hallucination_rows,
        "injection_results": injection_rows,
    }
    if report_extra:
        report.update(report_extra)
    st.download_button(
        "Download report (JSON)",
        data=json.dumps(report, indent=2),
        file_name="sharkguard_report.json",
        mime="application/json",
        use_container_width=True,
    )


# --- Sidebar: setup ---
submitted = False
submitted_ci = False

with st.sidebar:
    st.markdown("### 🦈 SharkGuard")
    st.caption("Hunts hallucinations and prompt injections before they ship.")
    st.markdown(
        "<span style='color:#22d3ee;font-size:12px'>&#128274; Stateless — nothing stored</span>",
        unsafe_allow_html=True,
    )
    st.divider()

    source = st.radio("Data source", ["Run live", "Load from GitHub Actions"])
    st.divider()

    if source == "Run live":
        with st.form("setup_form"):
            provider = st.selectbox("Model provider", ["Demo (no setup needed)", "Local (Ollama)", "Hosted (API key)"])

            api_key = api_base = model_name = None
            ollama_model = "llama3.2"

            if provider == "Hosted (API key)":
                api_key = st.text_input("API key", type="password")
                api_base = st.text_input("API base URL", placeholder="https://api.groq.com/openai/v1")
                model_name = st.text_input("Model name", placeholder="llama-3.1-8b-instant")
            elif provider == "Local (Ollama)":
                ollama_model = st.text_input("Ollama model", value="llama3.2")
            else:
                st.caption("Runs realistic canned responses — no API key or Ollama needed. "
                           "Produces honest mixed results so you can see SharkGuard actually "
                           "catch problems.")

            compare = st.checkbox("Compare against a second model")
            api_key_b = api_base_b = model_name_b = None
            if compare:
                st.markdown("**Second model**")
                api_key_b = st.text_input("API key (model B)", type="password")
                api_base_b = st.text_input("API base URL (model B)", placeholder="https://api.openai.com/v1")
                model_name_b = st.text_input("Model name (model B)", placeholder="gpt-4o-mini")

            threshold = st.slider("Faithfulness threshold", 0.5, 0.99, 0.8, 0.01)

            submitted = st.form_submit_button("Run SharkGuard", use_container_width=True)
    else:
        with st.form("ci_form"):
            st.caption("Pulls the results your pipeline's own `reliability-eval` job "
                       "already produced — no fresh model calls, just the real build result.")
            owner = st.text_input("Repo owner", value="Abdulharis-cloud12")
            repo = st.text_input("Repo name", value="Shark-Guard")
            workflow_file = st.text_input("Workflow file", value="ci.yml")
            branch = st.text_input("Branch (optional)", value="main")
            run_id = st.text_input("Specific run ID (optional, blank = latest completed)")
            token = st.text_input(
                "GitHub token", type="password",
                help="Needs actions:read — a classic PAT with the 'repo' scope works. "
                     "GitHub requires this even for public repos to download artifacts. "
                     "Used only for this fetch, never stored.",
            )

            submitted_ci = st.form_submit_button("Fetch CI results", use_container_width=True)

# --- Main area ---
if not submitted and not submitted_ci:
    st.markdown("### Welcome to SharkGuard")
    if source == "Run live":
        st.write("Configure a model in the sidebar and click **Run SharkGuard** to test it "
                 "for hallucinations and prompt injection resistance.")
        st.info("No setup? Pick **Demo (no setup needed)** in the sidebar to see a real run "
                "with honest, mixed pass/fail results right away.")
    else:
        st.write("Fill in your repo details and a GitHub token in the sidebar, then click "
                 "**Fetch CI results** to see the exact result your pipeline already produced "
                 "— no fresh model calls from this dashboard.")
        st.info("Needs a token with `actions:read` — GitHub requires authentication to "
                "download workflow artifacts even on public repos.")

if submitted:
    provider_key = {"Local (Ollama)": "ollama", "Hosted (API key)": "hosted"}.get(provider, "demo")

    progress_bar = st.progress(0, text="Starting run...")

    def update_progress(fraction, message):
        progress_bar.progress(fraction, text=message)

    try:
        results_a = run_model_suite(
            provider_key, api_key, api_base, model_name, threshold, ollama_model,
            progress_cb=update_progress,
        )
    except Exception as e:
        progress_bar.empty()
        st.error(f"Could not complete the run: {e}")
        st.stop()

    results_b = None
    if compare:
        try:
            results_b = run_model_suite("hosted", api_key_b, api_base_b, model_name_b, threshold)
        except Exception as e:
            st.warning(f"Comparison model failed, showing model A only: {e}")

    progress_bar.empty()

    comparison_df = None
    if results_b:
        comparison_df = pd.DataFrame({
            "Model A": [results_a["faithfulness"], results_a["resistance"]],
            "Model B": [results_b["faithfulness"], results_b["resistance"]],
        }, index=["Faithfulness", "Injection resistance"])

    render_results(
        results_a["faithfulness"], results_a["resistance"], threshold, threshold,
        results_a["hallucination_rows"], results_a["injection_rows"],
        comparison_df=comparison_df,
    )
    st.caption("Your API key was used only for this run and has now been discarded.")

if submitted_ci:
    try:
        with st.spinner("Fetching CI results..."):
            ci = fetch_ci_run(
                owner.strip(), repo.strip(), token.strip(),
                workflow_file=workflow_file.strip() or "ci.yml",
                branch=(branch.strip() or None),
                run_id=(run_id.strip() or None),
            )
    except requests.HTTPError as e:
        st.error(f"GitHub API error: {e}")
        st.stop()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"Could not fetch CI results: {e}")
        st.stop()

    faithfulness, resistance, hallucination_rows, injection_rows = normalize_ci_results(ci)

    st.markdown(
        f"Run [#{ci['run_number']}]({ci['run_url']}) on `{ci['branch']}` "
        f"({ci['commit_sha']}) — **{ci['conclusion']}** — {ci['created_at']}"
    )

    render_results(
        faithfulness, resistance,
        ci["hallucination"]["threshold"], ci["injection"]["threshold"],
        hallucination_rows, injection_rows,
        report_extra={
            "source": "github_actions",
            "run_number": ci["run_number"],
            "run_url": ci["run_url"],
            "commit_sha": ci["commit_sha"],
        },
    )
    st.caption("Fetched directly from your pipeline's own artifacts — no model calls made from this dashboard.")
