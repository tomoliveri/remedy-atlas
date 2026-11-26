"""Run a study script in the sandbox and capture what's needed to reproduce it.

Studies never run directly on this machine. The script runs in Workstead's
sandbox (tools/ws/workstead/sandbox.py): WebAssembly (Pyodide in Deno, no
network, no access to your files) when it needs only the standard library,
NumPy, SciPy, pandas, scikit-learn or statsmodels; otherwise a rootless
container with no network, built from research/env/Dockerfile. Either way it
sees its input at /input/<name> and writes its result to /output/result.json,
under hard memory and time limits.

The receipt records the hashes, seed, run time, sandbox backend, limits and
this machine's hardware.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "ws"))

from workstead import config as C, sandbox as SB  # noqa: E402

import env as research_env  # noqa: E402


def digest(path):
    with path.open("rb") as data:
        hash_value = sha256()
        for chunk in iter(lambda: data.read(1024 * 1024), b""):
            hash_value.update(chunk)
    return hash_value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=300, help="maximum run time in seconds")
    parser.add_argument("--memory", type=int, help="memory limit in MB (default: sandbox.memory_mb)")
    parser.add_argument("--backend", default="auto", choices=["auto", "wasm", "container"])
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
    cfg = C.load(ROOT)
    hardware = research_env.hardware()
    with TemporaryDirectory(dir=output.parent) as directory:
        out_dir = Path(directory) / "out"
        try:
            res = SB.run_python(script, [source], out_dir,
                                ["--input", f"/input/{source.name}", "--output", "/output/result.json",
                                 "--seed", str(args.seed)],
                                cfg, backend=args.backend, memory_mb=args.memory, timeout=args.timeout)
        except SB.SandboxError as e:
            sys.exit(f"run.py: {e}")
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        part = out_dir / "result.json"
        if res.code != 0 or not part.is_file():
            why = f" ({res.killed})" if res.killed else ""
            sys.exit(f"run.py: the study failed in the sandbox{why}, exit {res.code}")
        with part.open() as data:
            if not isinstance(json.load(data), dict):
                raise ValueError("study output must be a JSON object")
        metadata = {**inputs, "output_sha256": digest(part), "seed": args.seed,
                    "seconds": round(res.seconds, 3), "sandbox": {**res.describe(), **_runtime(res.backend, cfg)},
                    "architecture": platform.machine(),
                    "hardware": {"physical_cores": hardware["physical_cores"], "memory_gb": hardware["memory_gb"],
                                 "gpus": [g["name"] for g in hardware["gpus"]]}}
        partial_receipt = Path(directory) / "run.json"
        partial_receipt.write_text(json.dumps(metadata, indent=2) + "\n")
        part.replace(output)
        partial_receipt.replace(receipt)
    print(f"Result: {output}\nRun receipt: {receipt}")


def _runtime(backend, cfg):
    """What exactly ran the study: the Pyodide release, or the container image."""
    if backend == "wasm":
        return {"python": "pyodide " + SB.PYODIDE_VERSION}
    if backend.startswith("container"):
        return {"image": SB._image(cfg)}
    return {"python": platform.python_version()}


if __name__ == "__main__":
    main()
