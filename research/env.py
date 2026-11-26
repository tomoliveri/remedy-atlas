"""The research environment on a volunteer's machine: hardware, and the sandbox studies run in.

    python3 research/env.py doctor     # cores, memory, GPUs, and which sandbox backends are ready
    python3 research/env.py setup      # fetch Pyodide (hash-checked) and build the project's container image

Studies never run directly on this machine (see tools/ws/workstead/sandbox.py
and docs/sandbox.md):

- **WebAssembly** (Pyodide in Deno, offline, no network or file access) runs
  studies that need only the standard library, NumPy, SciPy, pandas,
  scikit-learn or statsmodels. `setup` fetches those packages, each checked
  against the sha256 in Pyodide's lock file.
- **A rootless container** with no network runs the rest (RDKit, Numba,
  libRoadRunner, PyMC, PyTorch) and the project's checks. Its image is built
  from research/env/Dockerfile, which installs the hash-locked tiers in
  research/env/requirements-*.txt (`--require-hashes`).

GPUs: containers get NVIDIA GPUs on Linux with Docker when `sandbox.gpus` is
true. Apple GPUs can't be reached from a sandbox, so large GPU sweeps belong
on Linux machines; everything else runs on the CPU.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENV = HERE / "env"
ROOT = HERE.parent


def _sandbox():
    sys.path.insert(0, str(ROOT / "tools" / "ws"))
    from workstead import config as C, sandbox as SB
    return C.load(ROOT), SB


def tiers():
    out = {}
    for f in sorted(ENV.glob("*.in")):
        first = f.read_text().splitlines()[0] if f.read_text() else ""
        out[f.stem] = first.lstrip("# ").strip()
    return out


def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def memory_gb():
    try:
        if sys.platform == "darwin":
            return round(int(_run(["sysctl", "-n", "hw.memsize"]) or 0) / 2 ** 30, 1) or None
        if sys.platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 2 ** 20, 1)
        if os.name == "nt":
            out = _run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])
            return round(int(out) / 2 ** 30, 1) if out.isdigit() else None
    except (OSError, ValueError):
        return None
    return None


def physical_cores():
    if sys.platform == "darwin":
        n = _run(["sysctl", "-n", "hw.perflevel0.physicalcpu"]) or _run(["sysctl", "-n", "hw.physicalcpu"])
        if n.isdigit():
            return int(n)
    return os.cpu_count() or 1


def gpus():
    found = []
    if shutil.which("nvidia-smi"):
        for line in _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]).splitlines():
            name, _, mem = line.partition(",")
            found.append({"kind": "cuda", "name": name.strip(), "memory": mem.strip()})
    if shutil.which("rocm-smi"):
        names = [x for x in _run(["rocm-smi", "--showproductname"]).splitlines() if "Card series" in x]
        found += [{"kind": "rocm", "name": n.split(":")[-1].strip(), "memory": ""} for n in names] or \
            [{"kind": "rocm", "name": "AMD GPU", "memory": ""}]
    if sys.platform == "darwin" and platform.machine() == "arm64":
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple silicon"
        found.append({"kind": "metal", "name": chip, "memory": "shared with the CPU"})
    return found


def hardware():
    return {"os": platform.system(), "machine": platform.machine(), "cpus": os.cpu_count() or 1,
            "physical_cores": physical_cores(), "memory_gb": memory_gb(), "gpus": gpus(),
            "python": platform.python_version()}


def thread_env(hw):
    """BLAS and OpenMP threads: one per physical core, not per hyperthread."""
    n = str(hw["physical_cores"])
    return {k: n for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS",
                           "VECLIB_MAXIMUM_THREADS")}


def doctor(as_json=False):
    hw = hardware()
    cfg, SB = _sandbox()
    b = SB.backends(cfg)
    image = SB.project_image(cfg, ROOT)
    report = {"hardware": hw, "sandbox": b, "image": image[0] if image else None, "threads": thread_env(hw)}
    if as_json:
        print(json.dumps(report, indent=2))
        return 0
    mem = f", {hw['memory_gb']} GB memory" if hw["memory_gb"] else ""
    print(f"Machine: {hw['os']} {hw['machine']}, {hw['physical_cores']} physical cores ({hw['cpus']} threads){mem}")
    for g in hw["gpus"] or [{"kind": "none", "name": "no GPU found", "memory": ""}]:
        print(f"GPU:     {g['name']} ({g['kind']}{', ' + g['memory'] if g['memory'] else ''})")
    print(f"WebAssembly sandbox: {'ready' if b['wasm'] else 'not ready (install Deno 2+, then setup)'}")
    print(f"Container sandbox:   {b['engine'] + ' (' + b['container'] + ')' if b['container'] else 'none (install Podman, Docker Desktop or OrbStack)'}")
    if image:
        print(f"Project image:       {image[0]}")
    print("\nTiers (in the container image unless noted):")
    for name, about in tiers().items():
        where = " [also WebAssembly]" if name == "core" else ""
        print(f"  {name:6} {about}{where}")
    if not b["wasm"] or not b["container"]:
        print("\nNext: python3 research/env.py setup")
    return 0


def setup(quiet=False):
    cfg, SB = _sandbox()
    try:
        SB.setup(cfg["sandbox"]["packages"], quiet=quiet)
        tag = SB.build_image(cfg, ROOT, quiet=quiet)
    except (SB.SandboxError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        sys.exit(f"env.py: {e}")
    b = SB.backends(cfg)
    if not quiet:
        print(f"WebAssembly sandbox: {'ready' if b['wasm'] else 'needs Deno 2+ (https://deno.com)'}")
        print(f"Container image: {tag or 'not built (no rootless container engine)'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--json", action="store_true")
    s = sub.add_parser("setup")
    s.add_argument("--quiet", action="store_true")
    sub.add_parser("threads", help="print BLAS/OpenMP thread settings")
    a = ap.parse_args()
    if a.command == "doctor":
        return doctor(a.json)
    if a.command == "setup":
        return setup(a.quiet)
    for k, v in thread_env(hardware()).items():
        print(f"export {k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
