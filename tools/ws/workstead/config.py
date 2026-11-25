"""Configuration: workstead.json at the repository root, merged over defaults.

Every tunable lives here so that operators change one file. Unknown keys are
rejected so that a typo fails loudly instead of being silently ignored.
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "project": {"name": "", "charter": "PROJECT.md"},
    # owner/name. Empty means: GITHUB_REPOSITORY in Actions, else the git remote.
    "repo": "",
    "default_branch": "main",
    # Logins with full authority, in addition to anyone with write access.
    "maintainers": [],
    # Logins whose comments are the queue's own (state comments, bot tasks).
    "bots": ["github-actions[bot]"],
    "trust": {
        # auto: open for private repositories, earned for public ones.
        # open: everyone who can comment is trusted (private or team repos).
        # earned: maintainers, writers, the allow list, and anyone with
        #         trusted_after_merged merged workstead pull requests.
        "mode": "auto",
        "trusted_after_merged": 2,
        "allow": [],
        # Logins this project never trusts and never lets claim work.
        "deny": [],
    },
    # The shared safety net (workstead/safety.py): read the upstream list of
    # accounts flagged by independent projects. action: maintainer (listed
    # accounts lose trust; their pull requests need a maintainer) or block
    # (they also can't claim work). upstream "" = the template's upstream.
    "safety": {"shared": True, "upstream": "", "action": "maintainer"},
    # Slurm partitions: classes of work with their own limits and delivery.
    # deliver: pr (a pull request closes it), comment (/done with a result),
    #          plan (/plan splits it into child tasks).
    "partitions": {
        "plan": {"deliver": "plan", "review": False, "max_hours": 2,
                 "about": "Break a job or an oversized task into smaller tasks."},
        "code": {"deliver": "pr", "review": True, "max_hours": 4,
                 "about": "Change code and open a pull request."},
        "test": {"deliver": "pr", "review": True, "max_hours": 4,
                 "about": "Add or fix tests."},
        "docs": {"deliver": "pr", "review": True, "max_hours": 3,
                 "about": "Write or fix documentation."},
        "research": {"deliver": "comment", "review": False, "max_hours": 3,
                     "about": "Investigate and report findings as a comment."},
        "review": {"deliver": "review", "review": False, "max_hours": 2,
                   "about": "Review a submission (pull request, result or plan)."},
        "triage": {"deliver": "review", "review": False, "max_hours": 1,
                   "about": "Admit, reject or de-duplicate a proposed task."},
    },
    "default_partition": "code",
    "leases": {
        # A lease dies without a heartbeat for this long (Slurm: node timeout).
        "heartbeat_minutes": 120,
        # Time limit = clamp(time_factor * est_hours, min_hours, partition max_hours).
        "time_factor": 3,
        "min_hours": 1,
        # Concurrent leases per GitHub account (one person may run many agents).
        "max_per_account": 8,
        # Requeues before a task is held for a human (Slurm: --requeue limit).
        "max_attempts": 3,
    },
    "scheduler": {
        # Multifactor priority, as in Slurm's priority/multifactor plugin.
        "weights": {"priority": 1000, "age": 500, "critical_path": 100,
                    "fairshare": 50, "review": 6000, "rework": 100000,
                    # give-back: upstream tasks on this fleet's own weak spots
                    "affinity": 3000},
        "age_cap_hours": 72,
        "critical_path_cap": 20,
        # Workers pick at random among the best top_k to avoid thundering herds.
        "top_k": 8,
    },
    "plans": {
        "max_children": 60,
        "max_depth": 4,
        "max_tasks_per_job": 600,
        # Tasks estimated above this should be planned (split), not worked.
        "split_above_hours": 4,
    },
    "review": {
        "approvals_required": 1,
        # fleet: the queue merges once approvals and checks pass.
        # maintainer: the queue labels ws:ready-to-merge and a human merges.
        "merge": "fleet",
        "merge_method": "squash",
        "require_checks": True,
        "max_rounds": 5,
        # Pull requests touching these always need a maintainer's approval.
        "protected_paths": [".github/", "tools/ws/", "workstead.json",
                            "JOIN.md", "AGENTS.md", "CLAUDE.md", "SECURITY.md"],
        # Supply-chain guard: changes to dependencies, build images, git hooks
        # and binaries need a maintainer too (fnmatch patterns on file paths).
        "maintainer_patterns": [
            "package.json", "*/package.json", "package-lock.json", "*/package-lock.json", "yarn.lock", "*/yarn.lock",
            "pnpm-lock.yaml", "*/pnpm-lock.yaml", "npm-shrinkwrap.json", ".npmrc", "*/.npmrc",
            "requirements*.txt", "*/requirements*.txt", "pyproject.toml", "*/pyproject.toml", "setup.py", "*/setup.py",
            "setup.cfg", "Pipfile*", "poetry.lock", "*/poetry.lock", "uv.lock", "*/uv.lock",
            "go.mod", "*/go.mod", "go.sum", "*/go.sum", "Cargo.toml", "*/Cargo.toml", "Cargo.lock", "*/Cargo.lock",
            "Gemfile*", "*/Gemfile*", "composer.json", "composer.lock", "pom.xml", "*/pom.xml", "build.gradle*",
            "*/build.gradle*", "gradle/wrapper/*", "*.csproj", "packages.lock.json", "Package.swift", "Package.resolved",
            "Dockerfile*", "*/Dockerfile*", "*.dockerfile", "docker-compose*.yml", "compose*.yaml",
            ".githooks/*", ".husky/*", ".pre-commit-config.yaml", ".devcontainer/*", ".vscode/tasks.json", ".envrc",
            "*.exe", "*.dll", "*.so", "*.dylib", "*.bin", "*.jar", "*.whl", "*.pyc", "*.class", "*.wasm", "*.min.js",
        ],
        # Very large diffs are hard for an agent to review: a maintainer must.
        "maintainer_if_files_over": 60,
        "maintainer_if_lines_over": 4000,
    },
    "dedup": {"similarity": 0.72},
    # One command that proves a change works, run locally by `ws submit` and
    # by the CI workflow. Empty means none.
    "validate": {"command": "", "timeout_minutes": 30},
    # What a worker's machine needs. tools: executables that must be on PATH
    # (named in the join message so the person approves installing them up
    # front). command: project setup run in each new task worktree (npm ci...).
    "setup": {"tools": [], "command": "", "timeout_minutes": 30},
    "drain": {"expiries": 3, "window_hours": 168, "pause_hours": 24},
    # Give back: workers spend `share` of their measured lease time (0.001 =
    # 0.1%) on tasks from the upstream Workstead repository, through the same
    # protocol. Off unless the project owner turns it on; every joiner is told
    # in the consent message and can opt out with `ws join --no-give-back`.
    # upstream "" = the template this repository was created from.
    # learnings: give-back turns also carry this fleet's anonymous aggregate
    # queue statistics upstream (see workstead/learnings.py), so upstream work
    # targets the problems fleets actually have. Only when enabled is true.
    "give_back": {"enabled": False, "share": 0.001, "upstream": "",
                  "min_owed_hours": 0.5, "learnings": True},
    "board": {"title": "Workstead board", "branch": "ws-board"},
    "limits": {"result_chars": 60000, "plan_chars": 120000, "body_chars": 20000},
}

SYSTEM_PARTITIONS = ("plan", "review", "triage")


class ConfigError(ValueError):
    pass


def _merge(base: Dict[str, Any], over: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k.startswith("$") or k == "_comment":
            continue
        where = f"{path}{k}"
        if k not in base:
            # Partitions are user-extensible; everything else is fixed.
            if path == "partitions.":
                out[k] = v
                continue
            raise ConfigError(f"unknown config key: {where}")
        if isinstance(base[k], dict) and isinstance(v, dict) and path != "partitions.":
            out[k] = _merge(base[k], v, where + ".")
        elif isinstance(base[k], dict) and isinstance(v, dict):
            merged = copy.deepcopy(base[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def validate(cfg: Dict[str, Any]) -> None:
    parts = cfg["partitions"]
    for name in SYSTEM_PARTITIONS:
        if name not in parts:
            raise ConfigError(f"partition {name!r} is required")
    for name, p in parts.items():
        if not isinstance(p, dict):
            raise ConfigError(f"partition {name} must be an object")
        if p.get("deliver") not in ("pr", "comment", "plan", "review"):
            raise ConfigError(f"partition {name}: deliver must be pr, comment, plan or review")
        if not isinstance(p.get("max_hours", 1), (int, float)) or p.get("max_hours", 1) <= 0:
            raise ConfigError(f"partition {name}: max_hours must be positive")
    if cfg["default_partition"] not in parts:
        raise ConfigError("default_partition must name a partition")
    if cfg["trust"]["mode"] not in ("auto", "open", "earned"):
        raise ConfigError("trust.mode must be auto, open or earned")
    if cfg["review"]["merge"] not in ("fleet", "maintainer"):
        raise ConfigError("review.merge must be fleet or maintainer")
    if cfg["review"]["merge_method"] not in ("merge", "squash", "rebase"):
        raise ConfigError("review.merge_method must be merge, squash or rebase")
    if int(cfg["review"]["approvals_required"]) < 0:
        raise ConfigError("review.approvals_required must be >= 0")
    if not 0 < float(cfg["dedup"]["similarity"]) <= 1:
        raise ConfigError("dedup.similarity must be in (0, 1]")
    gb = cfg["give_back"]
    if cfg["safety"]["action"] not in ("maintainer", "block"):
        raise ConfigError("safety.action must be maintainer or block")
    if not isinstance(gb["learnings"], bool):
        raise ConfigError("give_back.learnings must be true or false")
    if not isinstance(gb["enabled"], bool) or not 0 <= float(gb["share"]) <= 0.05:
        raise ConfigError("give_back.share must be between 0 and 0.05")
    if gb["upstream"] and not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", gb["upstream"]):
        raise ConfigError("give_back.upstream must be owner/name")
    if int(cfg["leases"]["heartbeat_minutes"]) < 10:
        raise ConfigError("leases.heartbeat_minutes must be at least 10")


def find_root(start: Optional[Path] = None) -> Path:
    """The repository root: the nearest parent holding workstead.json."""
    env = os.environ.get("WS_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        if (d / "workstead.json").is_file():
            return d
    # Fall back to the checkout this tool lives in.
    return Path(__file__).resolve().parents[3]


def load(root: Optional[Path] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if data is None:
        root = root or find_root()
        f = root / "workstead.json"
        data = json.loads(f.read_text()) if f.is_file() else {}
    cfg = _merge(DEFAULTS, data)
    validate(cfg)
    return cfg


def partition(cfg: Dict[str, Any], name: str) -> Dict[str, Any]:
    return cfg["partitions"].get(name) or cfg["partitions"][cfg["default_partition"]]


def work_partitions(cfg: Dict[str, Any]):
    """Partitions that hold claimable work items (not review/triage)."""
    return [n for n, p in cfg["partitions"].items() if p["deliver"] != "review"]
