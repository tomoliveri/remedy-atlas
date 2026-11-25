"""Run a local study within a time and power budget and record its inputs."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

from power import power_source

DEVICES = ("cpu", "cuda", "rocm", "metal")
THREAD_LIMITS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "RAYON_NUM_THREADS")


def check_power(device, mains_only, allow_battery):
    source = power_source()
    if (device != "cpu" or mains_only) and source != "ac":
        raise RuntimeError("External power is required. Plug in before running this study.")
    if source == "battery" and not allow_battery:
        raise RuntimeError("The computer is on battery. Plug in or explicitly allow a CPU run on battery.")


def run_study(command, environment, timeout, device, mains_only, allow_battery):
    check_power(device, mains_only, allow_battery)
    deadline = monotonic() + timeout
    with subprocess.Popen(command, env=environment, start_new_session=os.name == "posix") as process:
        try:
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    code = process.wait(timeout=min(2, remaining))
                except subprocess.TimeoutExpired:
                    check_power(device, mains_only, allow_battery)
                    continue
                if code:
                    raise subprocess.CalledProcessError(code, command)
                return
        finally:
            if process.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass


def digest(path):
    with path.open("rb") as data:
        hash_value = sha256()
        for chunk in iter(lambda: data.read(1024 * 1024), b""):
            hash_value.update(chunk)
    return hash_value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path, help="local Python script or executable with --native")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=300, help="maximum run time in seconds")
    parser.add_argument("--native", action="store_true", help="run a locally compiled executable")
    parser.add_argument("--device", choices=DEVICES, default="cpu")
    parser.add_argument("--threads", type=int, default=1, help="thread limit for supported numerical libraries")
    power = parser.add_mutually_exclusive_group()
    power.add_argument("--mains-only", action="store_true", help="require detected external power for CPU runs too")
    power.add_argument("--allow-battery", action="store_true", help="allow CPU work while on battery")
    args = parser.parse_args()
    if args.timeout < 1 or args.threads < 1:
        parser.error("--timeout and --threads must be positive")
    if args.device != "cpu" and args.allow_battery:
        parser.error("--allow-battery applies only to CPU runs")
    output = args.output.resolve()
    receipt = output.with_name(output.name + ".run.json")
    if output.exists() or receipt.exists():
        parser.error("choose unused output and receipt paths")

    script, source = args.script.resolve(strict=True), args.input.resolve(strict=True)
    inputs = {"script_sha256": digest(script), "input_sha256": digest(source)}
    output.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    with TemporaryDirectory(dir=output.parent) as directory:
        tempdir = Path(directory)
        part = tempdir / "result.json"
        command = [str(script)] if args.native else [sys.executable, "-B", str(script)]
        command.extend(["--input", str(source), "--output", str(part), "--seed", str(args.seed)])
        environment = {**os.environ, **dict.fromkeys(THREAD_LIMITS, str(args.threads)),
                       "REMEDY_ATLAS_DEVICE": args.device, "REMEDY_ATLAS_THREADS": str(args.threads)}
        if args.device == "cpu":
            environment.update(CUDA_VISIBLE_DEVICES="", HIP_VISIBLE_DEVICES="", ROCR_VISIBLE_DEVICES="")
        try:
            run_study(command, environment, args.timeout, args.device, args.mains_only, args.allow_battery)
        except (RuntimeError, subprocess.SubprocessError) as error:
            parser.exit(1, f"{error}\n")
        with part.open() as data:
            if not isinstance(json.load(data), dict):
                raise ValueError("study output must be a JSON object")
        metadata = {**inputs, "output_sha256": digest(part), "seed": args.seed,
                    "seconds": round(monotonic() - started, 3),
                    "python": platform.python_version(), "architecture": platform.machine(),
                    "device": args.device, "threads": args.threads,
                    "program_type": "native" if args.native else "python"}
        partial_receipt = tempdir / "run.json"
        partial_receipt.write_text(json.dumps(metadata, indent=2) + "\n")
        part.replace(output)
        partial_receipt.replace(receipt)
    print(f"Result: {output}\nRun receipt: {receipt}")


if __name__ == "__main__":
    main()
