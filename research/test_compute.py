import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ComputeTests(unittest.TestCase):
    def test_reference_result_and_provenance_reproduce(self):
        study = ROOT / "research/studies/cervical"
        with TemporaryDirectory() as work:
            result = Path(work) / "result.json"
            command = [sys.executable, str(ROOT / "research/run.py"), str(study / "response.py"),
                       "--input", str(study / "cc50.csv"), "--output", str(result), "--seed", "42"]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.read_text()),
                             json.loads((study / "baseline.json").read_text()))
            receipt = json.loads(result.with_name("result.json.run.json").read_text())
            reference = json.loads((study / "baseline.json.run.json").read_text())
            for field in ("input_sha256", "script_sha256", "output_sha256", "seed"):
                self.assertEqual(receipt[field], reference[field])
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
