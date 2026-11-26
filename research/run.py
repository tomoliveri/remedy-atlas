"""Run a local study script and capture the information needed to reproduce it.

Uses the research venv (research/env.py setup) when it exists, so studies
get NumPy, SciPy and the other pinned tiers. The receipt records the hashes,
seed, run time, Python, library versions and hardware. The script runs with
a clean environment: no tokens, keys or credentials, one BLAS thread per
physical core.
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

import env as research_env

KEEP = ("PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL", "TZ", "TMPDIR", "TEMP", "TMP",
        "SYSTEMROOT", "CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "PYTORCH_ENABLE_MPS_FALLBACK", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS", "NUMBA_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def digest(path):
    with path.open("rb") as data:
        hash_value = sha256()
        for chunk in iter(lambda: data.read(1024 * 1024), b""):
            hash_value.update(chunk)
    return hash_value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=300, help="maximum run time in seconds")
    parser.add_argument("--python", help="interpreter (default: the research venv, else this Python)")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    output = args.output.resolve()
    receipt = output.with_name(output.name + ".run.json")
    if output.exists() or receipt.exists():
        parser.error("choose unused output and receipt paths")

    script, source = args.script.resolve(strict=True), args.input.resolve(strict=True)
    inputs = {"script_sha256": digest(script), "input_sha256": digest(source)}
    output.parent.mkdir(parents=True, exist_ok=True)
    python = args.python or str(research_env.venv_python() or sys.executable)
    hardware = research_env.hardware()
    _, libraries = research_env.installed(python)
    started = monotonic()
    with TemporaryDirectory(dir=output.parent) as directory:
        tempdir = Path(directory)
        part = tempdir / "result.json"
        child_env = {k: v for k, v in os.environ.items() if k in KEEP}
        for k, v in research_env.thread_env(hardware).items():
            child_env.setdefault(k, v)
        child_env.update(PYTHONHASHSEED="0", MPLCONFIGDIR=directory)
        subprocess.run([python, "-B", str(script), "--input", str(source),
                        "--output", str(part), "--seed", str(args.seed)],
                       check=True, timeout=args.timeout, env=child_env)
        with part.open() as data:
            if not isinstance(json.load(data), dict):
                raise ValueError("study output must be a JSON object")
        version = subprocess.run([python, "-c", "import platform; print(platform.python_version())"],
                                 capture_output=True, text=True).stdout.strip() or platform.python_version()
        metadata = {**inputs, "output_sha256": digest(part), "seed": args.seed,
                    "seconds": round(monotonic() - started, 3),
                    "python": version, "architecture": platform.machine(), "libraries": libraries,
                    "hardware": {"physical_cores": hardware["physical_cores"], "memory_gb": hardware["memory_gb"],
                                 "gpus": [g["name"] for g in hardware["gpus"]]}}
        partial_receipt = tempdir / "run.json"
        partial_receipt.write_text(json.dumps(metadata, indent=2) + "\n")
        part.replace(output)
        partial_receipt.replace(receipt)
    print(f"Result: {output}\nRun receipt: {receipt}")


if __name__ == "__main__":
    main()
