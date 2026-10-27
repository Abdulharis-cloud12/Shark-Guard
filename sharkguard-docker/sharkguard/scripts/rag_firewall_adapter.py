"""
SharkGuard - RAG Hallucination Firewall adapter

Lets SharkGuard test a whole RAG system (retrieval + generation + the
3-stage hallucination firewall from RAG-Hallucination-Firewall) instead of
a bare model. Each question is sent through the firewall's real pipeline:

    retrieve(question) -> run_firewall(question, chunks)

SharkGuard then scores the ANSWER exactly as it scores any other model's
answer, and records the firewall's OWN risk label next to it. Comparing the
two (see summarize_agreement) shows where an independent checker and the
firewall agree and where they don't.

Why a subprocess: the firewall needs torch, FAISS, LangChain and a ~1GB NLI
model. Keeping those out of SharkGuard's environment keeps SharkGuard's CI
install fast and its dependency list tiny. The firewall runs in ITS OWN
Python environment (its venv), in a long-lived worker process
(rag_firewall_worker.py) that loads the index and models once and then
answers questions over a JSON-lines pipe. This module uses only the
standard library.

Configuration (environment variables, or pass arguments):
  SHARKGUARD_RAG_FIREWALL_PATH     path to the cloned RAG-Hallucination-Firewall repo
  SHARKGUARD_RAG_FIREWALL_PYTHON   python of the firewall's environment
                                   (default: the repo's .venv/venv if present, else this python)
  SHARKGUARD_RAG_FIREWALL_STARTUP_TIMEOUT   seconds to load index + models (default 300)
  SHARKGUARD_RAG_FIREWALL_TIMEOUT           seconds per question (default 180)
"""

import atexit
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading

PROTOCOL_PREFIX = "@@SHARKGUARD@@ "
WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_firewall_worker.py")

# Firewall risk labels that count as "the firewall flagged this answer".
FLAGGED_LABELS = {"MEDIUM", "HIGH"}


class RagFirewallError(RuntimeError):
    """Raised for any failure talking to the firewall (startup, crash, timeout, pipeline error)."""


def _default_python(repo_path: str) -> str:
    for rel in (os.path.join(".venv", "Scripts", "python.exe"), os.path.join(".venv", "bin", "python"),
                os.path.join("venv", "Scripts", "python.exe"), os.path.join("venv", "bin", "python")):
        candidate = os.path.join(repo_path, rel)
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


class RagFirewallClient:
    def __init__(self, repo_path: str, python: str = None,
                 startup_timeout: float = None, request_timeout: float = None):
        if not repo_path or not os.path.isdir(repo_path):
            raise RagFirewallError(
                "RAG Firewall path is not set or not a directory. Set SHARKGUARD_RAG_FIREWALL_PATH "
                "to your clone of RAG-Hallucination-Firewall.")
        self.repo_path = os.path.abspath(repo_path)
        self.python = python or _default_python(self.repo_path)
        self.startup_timeout = startup_timeout or float(os.environ.get("SHARKGUARD_RAG_FIREWALL_STARTUP_TIMEOUT", "300"))
        self.request_timeout = request_timeout or float(os.environ.get("SHARKGUARD_RAG_FIREWALL_TIMEOUT", "180"))
        self._lock = threading.Lock()
        self._proc = None
        self._queue = None
        self._log_path = None
        self._start()

    # ---- process management -------------------------------------------------

    def _start(self):
        self._queue = queue.Queue()
        fd, self._log_path = tempfile.mkstemp(prefix="sharkguard_rag_", suffix=".log")
        log = os.fdopen(fd, "w")
        env = dict(os.environ, RAG_FIREWALL_PATH=self.repo_path, PYTHONIOENCODING="utf-8")
        try:
            self._proc = subprocess.Popen(
                [self.python, WORKER_PATH], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                text=True, encoding="utf-8", bufsize=1, env=env, cwd=self.repo_path)
        except OSError as e:
            log.close()
            raise RagFirewallError(f"Could not start the firewall's Python ({self.python}): {e}") from e
        finally:
            log.close()  # the child holds its own handle
        threading.Thread(target=self._reader, args=(self._proc, self._queue), daemon=True).start()

        msg = self._wait_for_message(self.startup_timeout, "start up (loading the index and NLI model)")
        if not msg.get("ready"):
            self.close(graceful=False)
            raise RagFirewallError(f"RAG Firewall failed to start: {msg.get('error', 'unknown error')}"
                                   + self._log_tail())

    @staticmethod
    def _reader(proc, q):
        try:
            for line in proc.stdout:
                if line.startswith(PROTOCOL_PREFIX):
                    try:
                        q.put(json.loads(line[len(PROTOCOL_PREFIX):]))
                    except ValueError:
                        pass  # malformed protocol line - ignore, a timeout will surface real trouble
        finally:
            q.put(None)  # EOF marker: the worker is gone

    def _log_tail(self, n_chars: int = 1500) -> str:
        try:
            with open(self._log_path, encoding="utf-8", errors="replace") as f:
                tail = f.read()[-n_chars:].strip()
            return f"\n--- firewall log (tail) ---\n{tail}" if tail else ""
        except OSError:
            return ""

    def _wait_for_message(self, timeout: float, what: str) -> dict:
        try:
            msg = self._queue.get(timeout=timeout)
        except queue.Empty:
            self.close(graceful=False)
            raise RagFirewallError(f"Timed out after {timeout:.0f}s waiting for the firewall to {what}."
                                   + self._log_tail()) from None
        if msg is None:
            raise RagFirewallError(f"The firewall process exited while trying to {what}." + self._log_tail())
        return msg

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self, graceful: bool = True):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if graceful and proc.poll() is None:
                try:
                    proc.stdin.close()  # EOF ends the worker's read loop
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except OSError:
            pass

    # ---- asking questions ---------------------------------------------------

    def ask(self, question: str) -> dict:
        with self._lock:
            if not self._alive():
                self._start()  # worker died earlier (crash or timeout) - bring up a fresh one
            try:
                self._proc.stdin.write(json.dumps({"question": question}) + "\n")
                self._proc.stdin.flush()
            except OSError as e:
                self.close(graceful=False)
                raise RagFirewallError(f"Could not send the question to the firewall: {e}" + self._log_tail()) from e
            msg = self._wait_for_message(self.request_timeout, "answer a question")
            if not msg.get("ok"):
                raise RagFirewallError(f"RAG Firewall pipeline error: {msg.get('error', 'unknown error')}")
            return msg


# ---- module-level convenience API used by model_client / run_eval ------------

_clients = {}
_last = {}  # prompt -> last result for that prompt


def get_client(repo_path: str = None, python: str = None) -> RagFirewallClient:
    repo_path = repo_path or os.environ.get("SHARKGUARD_RAG_FIREWALL_PATH")
    python = python or os.environ.get("SHARKGUARD_RAG_FIREWALL_PYTHON")
    key = (os.path.abspath(repo_path) if repo_path else None, python)
    if key not in _clients:
        _clients[key] = RagFirewallClient(repo_path, python)
    return _clients[key]


def call_rag_firewall(prompt: str, repo_path: str = None, python: str = None) -> str:
    """Send a prompt through retrieval + firewall; return the answer text. The firewall's
    verdict for this prompt is kept and available via firewall_metadata(prompt)."""
    result = get_client(repo_path, python).ask(prompt)
    _last[prompt] = result
    return result["answer"]


def get_last_result(prompt: str):
    return _last.get(prompt)


def firewall_metadata(prompt: str):
    """Compact, JSON-safe firewall verdict for a prompt, or None if it wasn't answered by the firewall."""
    r = _last.get(prompt)
    if not r:
        return None
    return {
        "risk_label": r.get("risk_label"),
        "composite_risk_score": r.get("composite_risk_score"),
        "stages_flagged": r.get("stages_flagged"),
        "stage_flags": r.get("stage_flags"),
        "total_ms": (r.get("latency") or {}).get("total_ms"),
    }


def summarize_agreement(pairs) -> dict:
    """
    pairs: iterable of (sharkguard_ok: bool, firewall_label: str | None).
    sharkguard_ok means SharkGuard's own check passed (answer correct / injection resisted).
    Entries with no firewall label are skipped.

      both_ok               SharkGuard passed it, firewall did not flag it
      both_bad              SharkGuard failed it AND the firewall flagged it (firewall caught it)
      sharkguard_only_bad   SharkGuard failed it but the firewall did NOT flag it (firewall missed it)
      firewall_only_flagged firewall flagged it but SharkGuard passed it (false alarm, OR something
                            SharkGuard's checks can't see - review these by hand)
    """
    s = {"both_ok": 0, "both_bad": 0, "sharkguard_only_bad": 0, "firewall_only_flagged": 0, "total": 0}
    for sg_ok, label in pairs:
        if label is None:
            continue
        flagged = label in FLAGGED_LABELS
        s["total"] += 1
        if sg_ok and not flagged:
            s["both_ok"] += 1
        elif not sg_ok and flagged:
            s["both_bad"] += 1
        elif not sg_ok and not flagged:
            s["sharkguard_only_bad"] += 1
        else:
            s["firewall_only_flagged"] += 1
    return s


def format_agreement(s: dict) -> str:
    if not s or not s.get("total"):
        return "No firewall verdicts recorded."
    agree = s["both_ok"] + s["both_bad"]
    return (f"Firewall vs SharkGuard agreement: {agree}/{s['total']} "
            f"(both OK: {s['both_ok']}, both flagged: {s['both_bad']}); "
            f"firewall missed {s['sharkguard_only_bad']}, "
            f"firewall-only flags to review: {s['firewall_only_flagged']}")


@atexit.register
def _close_all():
    for c in list(_clients.values()):
        c.close()
