"""
SharkGuard Dashboard

A stateless, interactive dashboard for testing an LLM application's
reliability (hallucination) and security (prompt injection resistance).

Stateless by design: API keys entered here live only in this session's
memory for the duration of a run. Nothing is written to disk, logged,
or sent anywhere except directly to the model provider you choose -
with one opt-in exception: if you check "Save this run to local
history", the aggregate scores (never keys, never prompts) are saved
to sharkguard_history.json so you can see a trend over time.

Run locally with:
    streamlit run app.py
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from scripts.model_client import call_model
from scripts.run_eval import score_answer
from scripts.injection_test import check_resistance, check_resistance_llm_judge
from scripts.generate_eval import generate_eval_set
from scripts.hallucination_patterns import recommend_pattern
from scripts import history

EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set", "qa_pairs.json")
INJECTION_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set", "injection_prompts.json")
INJECTION_REDTEAM_PATH = os.path.join(os.path.dirname(__file__), "eval_set", "injection_redteam_set.json")
INDUSTRY_DIR = os.path.join(os.path.dirname(__file__), "eval_set", "industry_packs")

# industry -> (qa filename or None, injection/compliance filename or None)
INDUSTRY_PACKS = {
    "Healthcare": ("healthcare_qa.json", "healthcare_injection.json"),
    "Legal": ("legal_qa.json", "legal_injection.json"),
    "Financial": ("financial_qa.json", "financial_injection.json"),
    "HR": ("hr_qa.json", "hr_bias.json"),
    "Sales": (None, "sales_injection.json"),
}

st.set_page_config(page_title="SharkGuard", layout="centered", page_icon="\U0001F988")


@st.cache_data
def load_builtin_eval_set():
    with open(EVAL_SET_PATH) as f:
        return json.load(f)


@st.cache_data
def load_builtin_injection_set():
    with open(INJECTION_SET_PATH) as f:
        return json.load(f)


@st.cache_data
def load_redteam_injection_set():
    with open(INJECTION_REDTEAM_PATH) as f:
        return json.load(f)


@st.cache_data
def load_industry_file(filename):
    with open(os.path.join(INDUSTRY_DIR, filename)) as f:
        return json.load(f)


def badge(text, kind):
    """kind: 'pass' or 'fail' -> a small colored pill, rendered as HTML."""
    colors = {"pass": ("#0f6e56", "#0d3d33"), "fail": ("#e35d5d", "#3d1414")}
    fg, bg = colors[kind]
    return (f"<span style='background:{bg};color:{fg};padding:2px 10px;"
            f"border-radius:999px;font-size:12px;font-weight:600'>{text}</span>")


def run_model_suite(qa_pairs, injections, provider, api_key, api_base, model,
                     threshold, ollama_model="llama3.2", progress_cb=None, use_judge=False,
                     judge_call_fn=None):
    """Runs both test sets against one model. Returns a results dict.
    judge_call_fn: optional callable(prompt)->str for a separate judge model;
    if None and use_judge is True, the model under test judges itself."""
    total_steps = len(qa_pairs) + len(injections)
    done = 0

    hallucination_rows = []
    for item in qa_pairs:
        answer = call_model(item["question"], provider=provider, api_key=api_key,
                             api_base=api_base, model=model, ollama_model=ollama_model)
        score = score_answer(answer, item["ground_truth"])
        passed = score >= threshold
        row = {
            "question": item["question"], "score": score,
            "passed": passed, "answer": answer,
            "ground_truth": item["ground_truth"],
        }
        if not passed:
            row["suggested_pattern"] = recommend_pattern(item["question"], item["ground_truth"])
        hallucination_rows.append(row)
        done += 1
        if progress_cb:
            progress_cb(done / total_steps, f"Hallucination check {done}/{len(qa_pairs)}")

    injection_rows = []
    for item in injections:
        answer = call_model(item["prompt"], provider=provider, api_key=api_key,
                             api_base=api_base, model=model, ollama_model=ollama_model)
        if use_judge and provider != "demo":
            resisted = check_resistance_llm_judge(item["prompt"], answer, item.get("judge_criteria"),
                                                    judge_call_fn=judge_call_fn)
        else:
            resisted = check_resistance(answer, item.get("fail_if_contains", []))
        injection_rows.append({
            "type": item["type"], "resisted": resisted, "answer": answer,
            "prompt": item["prompt"],
        })
        done += 1
        if progress_cb:
            idx = done - len(qa_pairs)
            progress_cb(done / total_steps, f"Injection check {idx}/{len(injections)}")

    faithfulness = sum(r["score"] for r in hallucination_rows) / len(hallucination_rows) if hallucination_rows else 0
    resistance = sum(r["resisted"] for r in injection_rows) / len(injection_rows) if injection_rows else 0

    return {
        "faithfulness": faithfulness, "resistance": resistance,
        "hallucination_rows": hallucination_rows, "injection_rows": injection_rows,
    }


if "custom_eval_set" not in st.session_state:
    st.session_state.custom_eval_set = None
if "custom_injection_set" not in st.session_state:
    st.session_state.custom_injection_set = None

# --- Sidebar: model setup ---
with st.sidebar:
    st.markdown("### 🦈 SharkGuard")
    st.caption("Hunts hallucinations and prompt injections before they ship.")
    st.markdown("<span style='color:#22d3ee;font-size:12px'>&#128274; Stateless — nothing stored by default</span>",
                unsafe_allow_html=True)
    st.divider()

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
        st.caption("Runs realistic canned responses — no API key or Ollama needed.")

    compare = st.checkbox("Compare against a second model")
    api_key_b = api_base_b = model_name_b = None
    if compare:
        st.markdown("**Second model**")
        api_key_b = st.text_input("API key (model B)", type="password")
        api_base_b = st.text_input("API base URL (model B)", placeholder="https://api.openai.com/v1")
        model_name_b = st.text_input("Model name (model B)", placeholder="gpt-4o-mini")

    threshold = st.slider("Faithfulness threshold", 0.5, 0.99, 0.8, 0.01)
    save_to_history = st.checkbox("Save this run to local history", value=False,
                                   help="Stores only the aggregate scores and timestamp locally — "
                                        "never your API key or the actual prompts/answers.")

    st.divider()
    st.markdown("**Eval set**")
    eval_industries = [name for name, (qa, _) in INDUSTRY_PACKS.items() if qa]
    eval_source = st.radio("Question source",
                            ["Built-in sample", "Industry pack", "Upload JSON", "Auto-generate from text"],
                            label_visibility="collapsed")

    if eval_source == "Industry pack":
        eval_industry = st.selectbox("Industry", eval_industries, key="eval_industry")
        qa_file, _ = INDUSTRY_PACKS[eval_industry]
        st.session_state.custom_eval_set = load_industry_file(qa_file)
        st.caption(f"{len(st.session_state.custom_eval_set)} {eval_industry}-specific factual questions "
                   f"— shift-left starter set, catches domain risks at the PR stage.")
    elif eval_source == "Upload JSON":
        uploaded = st.file_uploader("Upload a qa_pairs.json-style file", type="json")
        if uploaded is not None:
            try:
                st.session_state.custom_eval_set = json.load(uploaded)
                st.success(f"Loaded {len(st.session_state.custom_eval_set)} questions.")
            except json.JSONDecodeError:
                st.error("That file isn't valid JSON.")
                st.session_state.custom_eval_set = None
    elif eval_source == "Auto-generate from text":
        ref_text = st.text_area("Paste reference text (docs, FAQ, policy)", height=100)
        num_q = st.number_input("Number of questions", min_value=2, max_value=15, value=5)
        if st.button("Generate questions", use_container_width=True):
            if not ref_text.strip():
                st.error("Paste some reference text first.")
            else:
                gen_provider = "ollama" if provider == "Local (Ollama)" else ("hosted" if provider == "Hosted (API key)" else "demo")
                with st.spinner("Generating questions..."):
                    try:
                        st.session_state.custom_eval_set = generate_eval_set(
                            ref_text, num_questions=int(num_q), provider=gen_provider,
                            api_key=api_key, api_base=api_base, model=model_name, ollama_model=ollama_model,
                        )
                        st.success(f"Generated {len(st.session_state.custom_eval_set)} questions.")
                    except ValueError as e:
                        st.error(f"Could not generate questions: {e}")
    else:
        st.session_state.custom_eval_set = None

    st.markdown("**Injection set**")
    injection_source = st.radio("Injection source",
                                 ["Built-in sample", "Red-team set (23 tests)", "Industry pack", "Upload JSON"],
                                 label_visibility="collapsed")
    if injection_source == "Industry pack":
        inj_industry = st.selectbox("Industry", list(INDUSTRY_PACKS.keys()), key="inj_industry")
        _, inj_file = INDUSTRY_PACKS[inj_industry]
        st.session_state.custom_injection_set = load_industry_file(inj_file)
        label = "bias checks" if inj_industry == "HR" else "compliance/injection tests"
        st.caption(f"{len(st.session_state.custom_injection_set)} {inj_industry}-specific {label}. "
                   f"Most have no fail_if_contains phrases (judgment-heavy) — turn on LLM-as-judge below.")
    elif injection_source == "Upload JSON":
        uploaded_inj = st.file_uploader("Upload an injection_prompts.json-style file", type="json", key="inj_upload")
        if uploaded_inj is not None:
            try:
                st.session_state.custom_injection_set = json.load(uploaded_inj)
                st.success(f"Loaded {len(st.session_state.custom_injection_set)} injection tests.")
            except json.JSONDecodeError:
                st.error("That file isn't valid JSON.")
                st.session_state.custom_injection_set = None
    elif injection_source == "Red-team set (23 tests)":
        st.session_state.custom_injection_set = load_redteam_injection_set()
        st.caption("23 tests from the adversarial defense playbook: direct injection, jailbreak, "
                   "prompt leaking, and scope violation categories.")
    else:
        st.session_state.custom_injection_set = None

    use_judge = st.checkbox("Use LLM-as-judge for injection scoring", value=False,
                             help="More accurate for nuanced cases (like the red-team set), "
                                  "costs one extra model call per attempt. Falls back to pattern "
                                  "matching automatically in Demo mode.")

    judge_provider = judge_api_key = judge_api_base = judge_model_name = None
    judge_ollama_model = "llama3.2"
    use_separate_judge = False
    if use_judge:
        use_separate_judge = st.checkbox("Use a separate judge model", value=False,
                                          help="Recommended: the model under test judging its own "
                                               "compliance is circular — a compromised model's verdict "
                                               "on its own compromise can't be fully trusted. A separate "
                                               "judge avoids that.")
        if use_separate_judge:
            judge_kind = st.selectbox("Judge provider", ["Local (Ollama)", "Hosted (API key)"], key="judge_kind")
            if judge_kind == "Hosted (API key)":
                judge_provider = "hosted"
                judge_api_key = st.text_input("Judge API key", type="password", key="judge_api_key")
                judge_api_base = st.text_input("Judge API base URL", key="judge_api_base",
                                                placeholder="https://api.openai.com/v1")
                judge_model_name = st.text_input("Judge model name", key="judge_model_name",
                                                  placeholder="gpt-4o-mini")
            else:
                judge_provider = "ollama"
                judge_ollama_model = st.text_input("Judge Ollama model", value="llama3.2", key="judge_ollama_model")

    run_clicked = st.button("Run SharkGuard", use_container_width=True, type="primary")

# --- Main area ---
if not run_clicked:
    st.markdown("### Welcome to SharkGuard")
    st.write("Configure a model in the sidebar and click **Run SharkGuard** to test it "
             "for hallucinations and prompt injection resistance.")
    st.info("No setup? Leave the provider as **Demo (no setup needed)** to see a real run "
            "with honest, mixed pass/fail results right away.")

    past = history.load_history()
    if past:
        st.markdown("#### Score history")
        hist_df = pd.DataFrame(past)
        hist_df["timestamp"] = pd.to_datetime(hist_df["timestamp"])
        hist_df = hist_df.set_index("timestamp")[["faithfulness", "resistance"]]
        st.line_chart(hist_df)
        if st.button("Clear local history"):
            history.clear_history()
            st.rerun()

if run_clicked:
    if provider == "Local (Ollama)":
        provider_key = "ollama"
    elif provider == "Hosted (API key)":
        provider_key = "hosted"
    else:
        provider_key = "demo"

    qa_pairs = st.session_state.custom_eval_set if st.session_state.custom_eval_set else load_builtin_eval_set()
    injections = st.session_state.custom_injection_set if st.session_state.custom_injection_set else load_builtin_injection_set()

    judge_fn = None
    if use_separate_judge:
        def judge_fn(prompt):
            return call_model(prompt, provider=judge_provider, api_key=judge_api_key,
                               api_base=judge_api_base, model=judge_model_name,
                               ollama_model=judge_ollama_model)

    progress_bar = st.progress(0, text="Starting run...")

    def update_progress(fraction, message):
        progress_bar.progress(fraction, text=message)

    try:
        results_a = run_model_suite(qa_pairs, injections, provider_key, api_key, api_base,
                                     model_name, threshold, ollama_model, progress_cb=update_progress,
                                     use_judge=use_judge, judge_call_fn=judge_fn)
    except Exception as e:
        progress_bar.empty()
        st.error(f"Could not complete the run: {e}")
        st.stop()

    results_b = None
    if compare:
        try:
            results_b = run_model_suite(qa_pairs, injections, "hosted", api_key_b,
                                         api_base_b, model_name_b, threshold, use_judge=use_judge,
                                         judge_call_fn=judge_fn)
        except Exception as e:
            st.warning(f"Comparison model failed, showing model A only: {e}")

    progress_bar.empty()

    gate_pass = results_a["faithfulness"] >= threshold and results_a["resistance"] >= threshold
    n_hallu_fail = sum(not r["passed"] for r in results_a["hallucination_rows"])
    n_inj_fail = sum(not r["resisted"] for r in results_a["injection_rows"])

    if save_to_history:
        history.save_run(results_a["faithfulness"], results_a["resistance"], threshold, gate_pass)

    if gate_pass:
        st.success("**BUILD PASSED** — no hallucinations or injection failures above threshold.")
    else:
        st.error(f"**BUILD BLOCKED** — {n_hallu_fail} hallucination(s), {n_inj_fail} injection failure(s) detected.")

    if use_judge:
        judge_note = "separate judge model" if use_separate_judge else "same model under test (self-judged)"
        st.caption(f"Injection scoring: LLM-as-judge, using the {judge_note}.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Faithfulness", f"{results_a['faithfulness']:.2f}")
    m2.metric("Injection resistance", f"{results_a['resistance']:.0%}")
    m3.metric("Gate status", "Pass" if gate_pass else "Fail")

    if results_b:
        st.markdown("#### Model comparison")
        chart_df = pd.DataFrame({
            "Model A": [results_a["faithfulness"], results_a["resistance"]],
            "Model B": [results_b["faithfulness"], results_b["resistance"]],
        }, index=["Faithfulness", "Injection resistance"])
        st.bar_chart(chart_df)

    st.markdown("#### Hallucination report")
    for row in results_a["hallucination_rows"]:
        kind = "pass" if row["passed"] else "fail"
        c1, c2, c3 = st.columns([5, 1, 1])
        c1.write(row["question"])
        c2.write(f"{row['score']:.2f}")
        c3.markdown(badge("Pass" if row["passed"] else "Fail", kind), unsafe_allow_html=True)
        if not row["passed"]:
            with st.expander("Why did this fail?"):
                st.write(f"**Expected to contain:** {row['ground_truth']}")
                st.write(f"**Model answered:** {row['answer']}")
                pattern = row.get("suggested_pattern")
                if pattern:
                    st.markdown(f"**Suggested fix:** {pattern['name']} ({pattern['effectiveness']}/5)")
                    st.caption(pattern["when_to_use"])
                    st.code(pattern["template"], language="text")

    st.markdown("#### Injection report")
    for row in results_a["injection_rows"]:
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
        "faithfulness": results_a["faithfulness"],
        "injection_resistance": results_a["resistance"],
        "threshold": threshold,
        "hallucination_results": results_a["hallucination_rows"],
        "injection_results": results_a["injection_rows"],
    }
    st.download_button("Download report (JSON)", data=json.dumps(report, indent=2),
                        file_name="sharkguard_report.json", mime="application/json",
                        use_container_width=True)

    st.caption("Your API key was used only for this run and has now been discarded.")
