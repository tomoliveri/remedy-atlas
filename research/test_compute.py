import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ComputeTests(unittest.TestCase):
    def test_reference_result_and_provenance_reproduce(self):
        self.assert_study_reproduces("cervical", "response.py", "cc50.csv")

    def test_snakebite_svmp_result_and_provenance_reproduce(self):
        self.assert_study_reproduces("snakebite-svmp", "response.py", "ic50.csv")

    def test_ndm_baseline_result_and_provenance_reproduce(self):
        self.assert_study_reproduces("ndm-baseline", "baseline_model.py", "ic50_by_study.csv")

    def assert_study_reproduces(self, name, script, source):
        study = ROOT / "research/studies" / name
        with TemporaryDirectory() as work:
            result = Path(work) / "result.json"
            command = [sys.executable, str(ROOT / "research/run.py"), str(study / script),
                       "--input", str(study / source), "--output", str(result), "--seed", "42"]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.read_text()),
                             json.loads((study / "baseline.json").read_text()))
            receipt = json.loads(result.with_name("result.json.run.json").read_text())
            reference = json.loads((study / "baseline.json.run.json").read_text())
            for field in ("input_sha256", "script_sha256", "output_sha256", "seed"):
                self.assertEqual(receipt[field], reference[field])
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
