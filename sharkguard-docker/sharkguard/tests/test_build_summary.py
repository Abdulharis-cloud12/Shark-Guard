import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.build_summary import build_summary


class BuildSummaryTests(unittest.TestCase):
    def test_missing_required_results_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                result = build_summary()
            finally:
                os.chdir(old)
        self.assertIn("BUILD BLOCKED", result)
        self.assertIn("hallucination_results.json", result)

    def test_all_required_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                for filename, key in (("hallucination_results.json", "pass_rate"), ("injection_results.json", "resistance_rate"), ("multi_turn_results.json", "pass_rate")):
                    Path(filename).write_text(json.dumps({key: 1.0, "threshold": 0.8}), encoding="utf-8")
                result = build_summary()
            finally:
                os.chdir(old)
        self.assertIn("BUILD PASSED", result)
        self.assertIn("Bias detection", result)

    def test_invalid_result_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                Path("hallucination_results.json").write_text("not json", encoding="utf-8")
                Path("injection_results.json").write_text(json.dumps({"resistance_rate": 1, "threshold": 0.8}), encoding="utf-8")
                Path("multi_turn_results.json").write_text(json.dumps({"pass_rate": 1, "threshold": 0.8}), encoding="utf-8")
                result = build_summary()
            finally:
                os.chdir(old)
        self.assertIn("BUILD BLOCKED", result)
        self.assertIn("invalid result file", result)


if __name__ == "__main__":
    unittest.main()
