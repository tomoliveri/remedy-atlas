"""Choose the array backend and device for batched simulations, and describe them for run receipts.

NumPy on the CPU is the default: results are bit-for-bit reproducible, which
independent verifiers need. Ask for "auto" to use a GPU (CUDA, ROCm or Apple
Metal through PyTorch) for large parameter sweeps; Metal computes in float32.

    from compute_backend import backend
    be = backend("auto")            # or "cpu", "cuda", "mps"
    x = be.asarray([1.0, 2.0])
    y = be.xp.exp(x)
    be.to_numpy(y)
"""
import os
import platform

import numpy as np


class Backend:
    """A thin shim over NumPy or PyTorch with the operations the shared tools need."""

    def __init__(self, name, device, xp, dtype):
        self.name, self.device, self.xp, self.dtype = name, device, xp, dtype

    def asarray(self, x):
        if self.name == "numpy":
            return np.asarray(x, dtype=self.dtype)
        return self.xp.as_tensor(np.asarray(x), dtype=self.dtype, device=self.device)

    def to_numpy(self, x):
        if self.name == "numpy":
            return np.asarray(x)
        return x.detach().to("cpu").double().numpy()

    def clip(self, x, lo, hi):
        return np.clip(x, lo, hi) if self.name == "numpy" else self.xp.clamp(x, lo, hi)

    def zeros(self, n):
        return np.zeros(n, dtype=self.dtype) if self.name == "numpy" else self.xp.zeros(n, dtype=self.dtype,
                                                                                       device=self.device)

    def describe(self):
        info = {"backend": self.name, "device": self.device, "dtype": str(self.dtype).replace("torch.", ""),
                "machine": platform.machine()}
        if self.name == "torch" and self.device == "cuda":
            info["gpu"] = self.xp.cuda.get_device_name(0)
        return info


def available():
    """Devices this machine can use, best first."""
    found = []
    try:
        import torch
    except ImportError:
        return ["cpu"]
    if torch.cuda.is_available():
        found.append("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        found.append("mps")
    return found + ["cpu"]


def backend(prefer="cpu"):
    """"cpu" (NumPy, float64), "auto" (best GPU, else CPU), or a device name: "cuda", "mps", "torch-cpu"."""
    if prefer == "cpu":
        return Backend("numpy", "cpu", np, np.float64)
    devices = available()
    if prefer == "auto":
        prefer = devices[0]
        if prefer == "cpu":
            return Backend("numpy", "cpu", np, np.float64)
    if prefer not in devices and prefer != "torch-cpu":
        raise ValueError(f"device {prefer} isn't available here (have: {', '.join(devices)})")
    import torch
    dev = "cpu" if prefer == "torch-cpu" else prefer
    return Backend("torch", dev, torch, torch.float32 if dev == "mps" else torch.float64)


def limit_threads(n=None):
    """Use one BLAS/OpenMP thread per physical core (or n). Returns the number used."""
    n = int(n or os.cpu_count() or 1)
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(n)
    except ImportError:
        pass
    try:
        import torch
        torch.set_num_threads(n)
    except ImportError:
        pass
    return n
