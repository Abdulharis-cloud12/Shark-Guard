"""
SharkGuard - RAG Hallucination Firewall worker

This file is NOT run inside SharkGuard's own Python environment. The adapter
(rag_firewall_adapter.py) launches it as a subprocess using the Python
interpreter of the RAG-Hallucination-Firewall project, because that project
needs heavy dependencies (torch, FAISS, LangChain, transformers) that
SharkGuard deliberately does not install.

Protocol (one JSON object per line):
  worker -> adapter, on startup:  {"ready": true}  or  {"ready": false, "error": "..."}
  adapter -> worker:              {"question": "..."}
  worker -> adapter:              {"ok": true, "answer": ..., "risk_label": ..., ...}
                               or {"ok": false, "error": "..."}

Every protocol line starts with PROTOCOL_PREFIX. The firewall's own code (and
its dependencies) print progress messages to stdout; stdout is redirected to
stderr after we grab the real handle, and the prefix lets the adapter ignore
anything that still leaks through.

Config: RAG_FIREWALL_PATH = path to the cloned RAG-Hallucination-Firewall repo.
"""

import json
import os
import sys

PROTOCOL_PREFIX = "@@SHARKGUARD@@ "

# Keep the real stdout for the protocol; send everything else to stderr.
protocol_out = sys.stdout
sys.stdout = sys.stderr


def send(obj: dict) -> None:
    protocol_out.write(PROTOCOL_PREFIX + json.dumps(obj) + "\n")
    protocol_out.flush()


def main() -> None:
    repo = os.environ.get("RAG_FIREWALL_PATH")
    if not repo or not os.path.isdir(repo):
        send({"ready": False, "error": f"RAG_FIREWALL_PATH is not a directory: {repo!r}"})
        return
    repo = os.path.abspath(repo)

    # sys.path[0] is SharkGuard's scripts/ dir. The firewall repo has its own
    # `scripts` package, so drop ours or the two collide.
    if sys.path and os.path.abspath(sys.path[0]) == os.path.dirname(os.path.abspath(__file__)):
        sys.path.pop(0)
    sys.path.insert(0, repo)
    os.chdir(repo)  # the firewall resolves its config, .env and FAISS index relative to the repo

    try:
        from src.retrieval.retriever import load_index, retrieve
        from src.hallucination.firewall import run_firewall
        vectorstore = load_index()
    except Exception as e:  # noqa: BLE001 - report anything, the adapter shows it to the user
        send({"ready": False, "error": f"{type(e).__name__}: {e}"})
        return

    send({"ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            question = json.loads(line)["question"]
            chunks, retrieval_ms = retrieve(question, vectorstore)
            result = run_firewall(question, chunks)
            send({
                "ok": True,
                "answer": result["answer"],
                "risk_label": result["risk_label"],
                "composite_risk_score": result["composite_risk_score"],
                "stages_flagged": result["stages_flagged"],
                "stage_flags": {
                    "entropy": bool(result["stage1_entropy"].get("flagged")),
                    "jsd": bool(result["stage2_jsd"].get("flagged")),
                    "nli": bool(result["stage3_nli"].get("flagged")),
                },
                "latency": result.get("latency", {}),
                "retrieval_ms": retrieval_ms,
            })
        except Exception as e:  # noqa: BLE001
            send({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
