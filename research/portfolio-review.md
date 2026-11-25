Build and run a small Python benchmark to decide which biological question should enter the compute queue next. Start with the [candidate register](https://github.com/tomoliveri/remedy-atlas/blob/main/docs/candidates.md) and recent literature leads below.

- Pick a treatment or biological response question with public numerical inputs. State how the work can split into independent inputs or model settings and what each worker can compute.
- Write a Python pilot to check coverage and missingness for candidate datasets and, where possible, run one baseline comparison. Record sources, inputs, exact run command, result JSON and receipt. Flag datasets that cannot support a defensible comparison.
- Recommend one candidate and a backup. Give each a measurable output, compute budget, baseline, control and independent replication step.
- Submit the Python pilot and results through `./ws submit NUMBER`. A maintainer reviews candidates before approving them for automatic queue intake.

Use only published or synthetic numerical data and the scope in `docs/PROJECT.md`.
