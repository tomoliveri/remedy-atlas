# Local compute budgets

A volunteer decides the machine, time, thread count and device before a run. Start with the CPU, one thread, and a small input that fits a five-minute run. On a known battery, the runner asks you to plug in or explicitly allow CPU work on battery.

## Pick the implementation

- Start with the simplest reproducible baseline. Python is a good way to express a model and may already call compiled numerical libraries.
- Profile a representative input once and record the wall time, input, environment, hardware class and numerical tolerance. Try a native Rust or C/C++ kernel only when a measured bottleneck warrants one. Pin the compiler and dependency versions and give reviewers the build command.
- Use a GPU for supported parallel workloads that are large enough to amortize setup and transfers. Make one small comparison against the CPU result with a preset accuracy and runtime target. Cache that decision in the task or the run notes. If the backend is absent, the result disagrees, or the speedup falls short, use the CPU version or return a GPU-only task. This keeps agents from repeatedly probing, installing packages or spending tokens on the same hardware questions. [CUDA performance guidance](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)

## Opt in to GPU work

A GPU-specific Workstead task requires both its backend feature and `compute:gpu-opt-in`. A detected GPU only establishes capability. For example, after confirming CUDA is available and the volunteer agrees:

```sh
./ws join --confirmed --features gpu:cuda,compute:gpu-opt-in
```

Use `gpu:rocm` for ROCm or `gpu:metal` for Metal. A GPU study must already provide the chosen backend. `research/run.py --device` communicates that choice to the program through `REMEDY_ATLAS_DEVICE`. Use `REMEDY_ATLAS_THREADS` in native programs and custom thread pools. The runner also sets common library thread-limit variables.

Run a Python study or a locally compiled executable with the same input, output and seed interface:

```sh
python3 research/run.py study.py --input fixture.csv --output result.json --seed 42
python3 research/run.py ./study --native --input fixture.csv --output result-native.json --seed 42
python3 research/run.py study.py --device cuda --threads 2 --timeout 180 --input fixture.csv --output result-cuda.json --seed 42
```

The default timeout is 300 seconds and the default library thread budget is one. GPU use requires detectable external power. The runner checks power before launch and during the run and stops the job if external power disappears. Use `--mains-only` to apply the same requirement to CPU work. Unknown power status allows short default CPU work. For a machine on battery, `--allow-battery` is an explicit CPU-only override. A larger run requires another agreement on the budget.

A run stopped for power or time publishes no completed receipt. Resume with a fresh output path once the volunteer is ready. Shard long runs into short jobs that can be repeated independently. The runner is a launcher for reviewed code. Programs must honour the selected device and thread limit, stay within their assigned worktree and avoid detaching background processes.
