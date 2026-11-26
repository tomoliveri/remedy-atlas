"""Set up and inspect the research environment on a volunteer's machine.

    python3 research/env.py doctor            # hardware, Python, installed tiers, what to install
    python3 research/env.py setup             # create the venv and install the recommended tiers
    python3 research/env.py setup core chem   # or name the tiers
    python3 research/env.py python            # path of the venv's Python (research/run.py uses it)

Tiers live in research/env/: each NAME.in says what it is for, and
requirements-NAME.txt pins every package (and its dependencies) by version
and sha256 for every platform. Installs use pip --require-hashes, so a
tampered or substituted package fails to install. All tiers share
constraints.txt, so any combination installs together.

The venv lives in .ws/research-venv in the main checkout and is shared by
every task worktree. Needs Python 3.12 or newer (NumPy 2.5); Workstead itself
still runs on 3.9.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENV = HERE / "env"
MIN_PYTHON = (3, 12)
# The module each tier must make importable, for the doctor's report.
PROBES = {"core": ["numpy", "scipy", "pandas", "sklearn", "statsmodels"], "fast": ["numba"], "chem": ["rdkit"],
          "qsp": ["roadrunner"], "bayes": ["pymc", "arviz"], "gpu": ["torch", "torchdiffeq"]}
VERSIONS = ["numpy", "scipy", "pandas", "scikit-learn", "statsmodels", "numba", "rdkit", "libroadrunner", "pymc",
            "torch", "torchdiffeq"]


def main_root():
    """The main checkout, even from a task worktree (.ws/work/N)."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=HERE,
                                capture_output=True, text=True, check=True, timeout=20).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.SubprocessError):
        return HERE.parent


def venv_dir():
    return main_root() / ".ws" / "research-venv"


def venv_python():
    d = venv_dir()
    p = d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return p if p.exists() else None


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


def recommended(hw):
    want = ["core"]
    if hw["physical_cores"] >= 4:
        want.append("fast")
    if any(g["kind"] in ("cuda", "metal") for g in hw["gpus"]):
        want.append("gpu")
    return want


def installed(py):
    """Which tiers import cleanly in the venv, and the versions of the main packages."""
    if not py:
        return {}, {}
    code = ("import importlib.util, importlib.metadata as m, json, sys\n"
            f"probes = {PROBES!r}\nnames = {VERSIONS!r}\n"
            "t = {k: all(importlib.util.find_spec(x) for x in v) for k, v in probes.items()}\n"
            "v = {}\n"
            "for n in names:\n"
            "    try: v[n] = m.version(n)\n"
            "    except m.PackageNotFoundError: pass\n"
            "print(json.dumps([t, v]))\n")
    out = _run([str(py), "-c", code], timeout=60)
    try:
        t, v = json.loads(out)
        return t, v
    except ValueError:
        return {}, {}


def accelerators(py):
    """What PyTorch in the venv can actually use."""
    if not py:
        return []
    code = ("import json\ntry:\n    import torch\nexcept ImportError:\n    print('[]'); raise SystemExit\n"
            "d = []\nif torch.cuda.is_available(): d.append('cuda' if not torch.version.hip else 'rocm')\n"
            "if getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available(): d.append('mps')\n"
            "print(json.dumps(d))\n")
    try:
        return json.loads(_run([str(py), "-c", code], timeout=60) or "[]")
    except ValueError:
        return []


def thread_env(hw):
    """BLAS and OpenMP threads: one per physical core, not per hyperthread."""
    n = str(hw["physical_cores"])
    return {k: n for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS",
                           "VECLIB_MAXIMUM_THREADS")}


def find_python():
    if sys.version_info >= MIN_PYTHON:
        return [sys.executable]
    for name in ("python3.14", "python3.13", "python3.12"):
        if shutil.which(name):
            return [shutil.which(name)]
    if shutil.which("uv"):
        return None  # uv venv --python 3.12 fetches one
    raise SystemExit("Python 3.12 or newer is needed for the research tiers. Install it (python.org, your package "
                     "manager, or `uv`), then run this again.")


def lock_digest(name):
    return sha256((ENV / f"requirements-{name}.txt").read_bytes()).hexdigest()


def setup(names, quiet=False):
    unknown = [n for n in names if n not in tiers()]
    if unknown:
        raise SystemExit(f"unknown tiers: {', '.join(unknown)} (have: {', '.join(tiers())})")
    names = ["core"] + [n for n in names if n != "core"]
    d = venv_dir()
    stamp = d / "workstead-tiers.json"
    try:
        done = json.loads(stamp.read_text())
    except (OSError, ValueError):
        done = {}
    have = done.get("locks") if isinstance(done.get("locks"), dict) else {}
    if venv_python() and all(have.get(n) == lock_digest(n) for n in names):
        if not quiet:
            print(f"Up to date: {', '.join(names)} in {d}")
        return 0
    d.parent.mkdir(parents=True, exist_ok=True)
    py = find_python()
    if not venv_python():
        if py is None:
            subprocess.run(["uv", "venv", "--python", "3.12", str(d)], check=True)
        else:
            subprocess.run([*py, "-m", "venv", str(d)], check=True)
    vpy = str(venv_python())
    reqs = [arg for n in names for arg in ("-r", str(ENV / f"requirements-{n}.txt"))]
    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "--python", vpy, "--require-hashes", *reqs]
    else:
        cmd = [vpy, "-m", "pip", "install", "--require-hashes", "--no-input", *reqs]
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    have.update({n: lock_digest(n) for n in names})
    stamp.write_text(json.dumps({"locks": have}, indent=2) + "\n")
    print(f"Installed {', '.join(names)}. research/run.py now uses {vpy}")
    return 0


def doctor(as_json=False):
    hw = hardware()
    py = venv_python()
    have, versions = installed(py)
    acc = accelerators(py)
    want = recommended(hw)
    report = {"hardware": hw, "venv": str(py) if py else None, "tiers": have, "versions": versions,
              "accelerators": acc, "recommended": want, "threads": thread_env(hw)}
    if as_json:
        print(json.dumps(report, indent=2))
        return 0
    mem = f", {hw['memory_gb']} GB memory" if hw["memory_gb"] else ""
    print(f"Machine: {hw['os']} {hw['machine']}, {hw['physical_cores']} physical cores ({hw['cpus']} threads){mem}")
    for g in hw["gpus"] or [{"kind": "none", "name": "no GPU found", "memory": ""}]:
        print(f"GPU:     {g['name']} ({g['kind']}{', ' + g['memory'] if g['memory'] else ''})")
    print(f"Python:  {hw['python']} here; research venv: {py or 'not created yet'}")
    print("\nTiers:")
    for name, about in tiers().items():
        mark = "installed" if have.get(name) else ("recommended" if name in want else "optional")
        print(f"  {name:6} [{mark}] {about}")
    if versions:
        print("\nVersions: " + ", ".join(f"{k} {v}" for k, v in versions.items()))
    if py and have.get("gpu"):
        print(f"PyTorch can use: {', '.join(acc) if acc else 'the CPU only'}")
    missing = [t for t in want if not have.get(t)]
    if missing:
        print(f"\nNext: python3 research/env.py setup {' '.join(missing)}")
    if any(g["kind"] == "rocm" for g in hw["gpus"]):
        print("AMD GPU: the gpu tier installs PyTorch's CUDA build from PyPI. For ROCm, install torch from "
              "https://download.pytorch.org/whl/rocm6.4 into the venv yourself; simulations still default to CPU.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--json", action="store_true")
    s = sub.add_parser("setup")
    s.add_argument("tiers", nargs="*", help="default: the tiers recommended for this machine")
    s.add_argument("--quiet", action="store_true")
    sub.add_parser("python")
    sub.add_parser("threads", help="print shell exports for BLAS/OpenMP threads")
    a = ap.parse_args()
    if a.command == "doctor":
        return doctor(a.json)
    if a.command == "setup":
        return setup(a.tiers or recommended(hardware()), a.quiet)
    if a.command == "python":
        py = venv_python()
        print(py or sys.executable)
        return 0 if py else 1
    for k, v in thread_env(hardware()).items():
        print(f"export {k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
