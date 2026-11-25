"""Run a local study script and capture the information needed to reproduce it."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic


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
    started = monotonic()
    with TemporaryDirectory(dir=output.parent) as directory:
        tempdir = Path(directory)
        part = tempdir / "result.json"
        subprocess.run([sys.executable, "-B", str(script), "--input", str(source),
                        "--output", str(part), "--seed", str(args.seed)],
                       check=True, timeout=args.timeout)
        with part.open() as data:
            if not isinstance(json.load(data), dict):
                raise ValueError("study output must be a JSON object")
        metadata = {**inputs, "output_sha256": digest(part), "seed": args.seed,
                    "seconds": round(monotonic() - started, 3),
                    "python": platform.python_version(), "architecture": platform.machine()}
        partial_receipt = tempdir / "run.json"
        partial_receipt.write_text(json.dumps(metadata, indent=2) + "\n")
        part.replace(output)
        partial_receipt.replace(receipt)
    print(f"Result: {output}\nRun receipt: {receipt}")


if __name__ == "__main__":
    main()
