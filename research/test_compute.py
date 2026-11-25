import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from power import linux_power
from run import check_power, run_study


ROOT = Path(__file__).resolve().parents[1]


class ComputeTests(unittest.TestCase):
    def test_reference_result_and_provenance_reproduce(self):
        study = ROOT / "research/studies/cervical"
        with TemporaryDirectory() as work:
            result = Path(work) / "result.json"
            command = [sys.executable, str(ROOT / "research/run.py"), str(study / "response.py"),
                       "--input", str(study / "cc50.csv"), "--output", str(result), "--seed", "42",
                       "--allow-battery"]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.read_text()),
                             json.loads((study / "baseline.json").read_text()))
            receipt = json.loads(result.with_name("result.json.run.json").read_text())
            reference = json.loads((study / "baseline.json.run.json").read_text())
            for field in ("input_sha256", "script_sha256", "output_sha256", "seed"):
                self.assertEqual(receipt[field], reference[field])
            self.assertEqual(receipt["device"], "cpu")
            self.assertEqual(receipt["threads"], 1)
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)

    def test_gpu_requires_known_external_power(self):
        for source in ("battery", "unknown"):
            with self.subTest(source=source), patch("run.power_source", return_value=source):
                with self.assertRaisesRegex(RuntimeError, "External power"):
                    check_power("cuda", False, False)

    def test_cpu_on_battery_requires_permission(self):
        with patch("run.power_source", return_value="battery"):
            with self.assertRaises(RuntimeError):
                check_power("cpu", False, False)
            check_power("cpu", False, True)
            with self.assertRaises(RuntimeError):
                check_power("cpu", True, False)

    def test_disconnecting_external_power_kills_a_gpu_job(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired(["study"], 2)
        launcher = MagicMock()
        launcher.__enter__.return_value = process
        with patch("run.power_source", side_effect=["ac", "battery"]), \
             patch("run.subprocess.Popen", return_value=launcher), \
             patch("run.os.killpg", create=True) as kill_group:
            with self.assertRaisesRegex(RuntimeError, "External power"):
                run_study(["study"], {}, 30, "metal", False, False)
            if os.name == "posix":
                kill_group.assert_called_once()
            else:
                process.kill.assert_called_once()

    def test_linux_power_supply_changes(self):
        with TemporaryDirectory() as work:
            root = Path(work)
            battery, charger = root / "BAT0", root / "USB-C"
            battery.mkdir()
            charger.mkdir()
            (battery / "type").write_text("Battery\n")
            (charger / "type").write_text("USB_C\n")
            (charger / "online").write_text("1\n")
            self.assertEqual(linux_power(root), "ac")
            (charger / "online").write_text("0\n")
            self.assertEqual(linux_power(root), "battery")
