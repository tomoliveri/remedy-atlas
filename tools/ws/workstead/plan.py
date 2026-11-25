"""Plans: how a task is broken into a DAG of smaller tasks.

A plan is a JSON document a planner posts with ``/plan``. Each entry becomes a
child issue. Entries depend on each other by key (or on existing issues by
``#N``). An entry with ``array`` fans out into one task per item, like a Slurm
job array; anything that depends on it depends on every element, which gives
map/reduce for free. See docs/planning.md.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .protocol import FEATURE_RE, KEY_RE

MAX_ARRAY = 100


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:24] or "x"


def validate(plan: Any, cfg: Dict[str, Any], depth: int,
             existing_ok=lambda n: True) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Check a plan and expand arrays.

    Returns (tasks in topological order, errors). Tasks carry ``deps`` (keys
    inside the plan) and ``ext_deps`` (existing issue numbers).
    """
    errors: List[str] = []
    pcfg = cfg["plans"]
    parts = cfg["partitions"]
    lim = cfg["limits"]["body_chars"]
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        return [], ['the plan must be a JSON object with a "tasks" list']
    if depth + 1 > pcfg["max_depth"]:
        return [], [f"plans may nest at most {pcfg['max_depth']} levels; this task is already at depth {depth}"]
    raw = plan["tasks"]
    if not raw:
        return [], ["the plan has no tasks"]

    seen: Set[str] = set()
    arrays: Dict[str, List[str]] = {}
    items: List[Dict[str, Any]] = []
    for i, t in enumerate(raw):
        where = f"tasks[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{where} must be an object")
            continue
        key = t.get("key")
        if not isinstance(key, str) or not KEY_RE.match(key):
            errors.append(f"{where}.key must match {KEY_RE.pattern}")
            continue
        if key in seen:
            errors.append(f"duplicate key {key!r}")
            continue
        seen.add(key)
        title = t.get("title")
        if not isinstance(title, str) or not 3 <= len(title.strip()) <= 200:
            errors.append(f"{key}: title must be 3 to 200 characters")
            continue
        body = t.get("body", "")
        if not isinstance(body, str) or len(body) > lim:
            errors.append(f"{key}: body must be a string of at most {lim} characters")
            continue
        acc = t.get("acceptance", [])
        if not isinstance(acc, list) or not all(isinstance(a, str) and len(a) <= 500 for a in acc) or len(acc) > 20:
            errors.append(f"{key}: acceptance must be a list of at most 20 short strings")
            continue
        part = t.get("partition", cfg["default_partition"])
        if part not in parts or parts[part]["deliver"] == "review":
            errors.append(f"{key}: partition {part!r} is not a work partition")
            continue
        est = t.get("est_hours", 1)
        if not isinstance(est, (int, float)) or isinstance(est, bool) or not 0 < est <= 100:
            errors.append(f"{key}: est_hours must be a number in (0, 100]")
            continue
        prio = t.get("priority", 3)
        if not isinstance(prio, int) or isinstance(prio, bool) or not 0 <= prio <= 9:
            errors.append(f"{key}: priority must be an integer 0-9")
            continue
        feats, lics = t.get("features", []), t.get("licenses", [])
        if not isinstance(feats, list) or not all(isinstance(f, str) and FEATURE_RE.match(f) for f in feats):
            errors.append(f"{key}: features must be short lowercase tags")
            continue
        if not isinstance(lics, list) or not all(isinstance(f, str) and FEATURE_RE.match(f) for f in lics):
            errors.append(f"{key}: licenses must be short lowercase tags")
            continue
        deps = t.get("deps", [])
        if not isinstance(deps, list):
            errors.append(f"{key}: deps must be a list")
            continue
        arr = t.get("array")
        if arr is not None:
            if not isinstance(arr, list) or not 1 <= len(arr) <= MAX_ARRAY or \
                    not all(isinstance(a, str) and 0 < len(a) <= 200 for a in arr):
                errors.append(f"{key}: array must list 1 to {MAX_ARRAY} non-empty strings")
                continue
            if len(set(arr)) != len(arr):
                errors.append(f"{key}: array items must be unique")
                continue
        base = {"title": title.strip(), "body": body, "acceptance": acc, "partition": part,
                "est_hours": float(est), "priority": prio, "features": sorted(set(feats)),
                "licenses": sorted(set(lics)), "after": "any" if t.get("after") == "any" else "ok",
                "raw_deps": deps}
        if arr is None:
            items.append(dict(base, key=key, item=None))
        else:
            arrays[key] = []
            for j, item in enumerate(arr):
                k = f"{key}.{j + 1}-{_slug(item)}"[:64]
                arrays[key].append(k)
                sub = {f: (v.replace("{item}", item) if isinstance(v, str) else v) for f, v in base.items()}
                sub["acceptance"] = [a.replace("{item}", item) for a in acc]
                items.append(dict(sub, key=k, item=item, array_of=key))
    if errors:
        return [], errors

    keys = {it["key"] for it in items}
    for it in items:
        deps: List[str] = []
        ext: List[int] = []
        for d in it.pop("raw_deps"):
            if isinstance(d, int) and not isinstance(d, bool) or (isinstance(d, str) and re.fullmatch(r"#?[0-9]{1,9}", d)):
                n = int(str(d).lstrip("#"))
                if not existing_ok(n):
                    errors.append(f"{it['key']}: #{n} is not an open or completed workstead task")
                ext.append(n)
            elif isinstance(d, str) and d in arrays:
                deps.extend(arrays[d])
            elif isinstance(d, str) and d in keys:
                deps.append(d)
            else:
                errors.append(f"{it['key']}: unknown dependency {d!r}")
        if it.get("array_of") and any(x in arrays.get(it["array_of"], []) for x in deps):
            errors.append(f"{it['key']}: an array element cannot depend on its own array")
        it["deps"] = sorted(set(deps) - {it["key"]})
        it["ext_deps"] = sorted(set(ext))
    if len(items) > pcfg["max_children"]:
        errors.append(f"the plan expands to {len(items)} tasks; the limit is {pcfg['max_children']} per plan "
                      "(plan in levels: make some entries plan-partition tasks)")
    if errors:
        return [], errors

    order = topo_order({it["key"]: it["deps"] for it in items})
    if order is None:
        return [], ["the dependencies contain a cycle"]
    by_key = {it["key"]: it for it in items}
    return [by_key[k] for k in order], []


def topo_order(graph: Dict[str, List[str]]) -> Optional[List[str]]:
    """Kahn's algorithm, stable by insertion order. None on a cycle."""
    indeg = {k: 0 for k in graph}
    rev: Dict[str, List[str]] = {k: [] for k in graph}
    for k, deps in graph.items():
        for d in deps:
            if d in graph:
                indeg[k] += 1
                rev[d].append(k)
    ready = [k for k in graph if indeg[k] == 0]
    out: List[str] = []
    while ready:
        k = ready.pop(0)
        out.append(k)
        for nxt in rev[k]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
    return out if len(out) == len(graph) else None


def dependents_count(graph: Dict[int, Iterable[int]], cap: int = 1000) -> Dict[int, int]:
    """For each node, how many nodes (transitively) wait on it.

    This is the critical-path factor: finishing a task that unblocks many
    others shortens the whole project the most.
    """
    rev: Dict[int, Set[int]] = {n: set() for n in graph}
    for n, deps in graph.items():
        for d in deps:
            rev.setdefault(d, set()).add(n)
    memo: Dict[int, Set[int]] = {}

    def down(n: int, stack: Set[int]) -> Set[int]:
        if n in memo:
            return memo[n]
        acc: Set[int] = set()
        stack.add(n)
        for m in rev.get(n, ()):
            if m in stack:
                continue  # cycles are rejected elsewhere; never loop here
            acc.add(m)
            if len(acc) < cap:
                acc |= down(m, stack)
        stack.discard(n)
        memo[n] = acc
        return acc

    return {n: min(cap, len(down(n, set()))) for n in graph}
