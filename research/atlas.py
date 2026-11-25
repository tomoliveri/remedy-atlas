"""Render the current research scaffold and propose Workstead starter plans."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ws"))

from workstead import config, plan  # noqa: E402

PARTITIONS = ("evidence", "impact", "synthesis")


def read(path, ref):
    if ref:
        return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True)
    return (ROOT / path).read_text()


def exists(path, ref):
    if not ref:
        return (ROOT / path).is_file()
    return subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"], cwd=ROOT, capture_output=True
    ).returncode == 0


def scaffold(track, partition, ref, task=None):
    template = read(f"research/scaffolds/{partition}.md", ref)
    override = f"research/tasks/{task}.md"
    if task and exists(override, ref):
        template += f"\n## Task #{task} update\n\n{read(override, ref)}"
    return f"# {track['name']}\n\n{track['question']}\n\nNext question: {track['next']}\n\n{template}"


def starter(track):
    tasks = []
    for partition, action in zip(PARTITIONS, ("Review evidence", "Assess addressable burden", "Summarise findings")):
        body = (
            f"{track['next']}\n\n"
            f"Refresh and render the current scaffold before starting: "
            f"`python3 research/atlas.py scaffold {track['id']} {partition} --latest --task NUMBER`. "
            "Replace NUMBER with this issue's number. "
            "Record the printed revision in the submission. Follow docs/PROJECT.md."
        )
        tasks.append({
            "key": partition,
            "title": f"{track['name']}: {action}",
            "partition": partition,
            "priority": track["priority"],
            "body": body,
            "deps": ["evidence", "impact"] if partition == "synthesis" else [],
            "acceptance": ["Cite primary sources and state the remaining uncertainty."],
        })
    return {"summary": track["next"], "tasks": tasks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    for command in ("job", "plan", "scaffold"):
        sub = commands.add_parser(command)
        sub.add_argument("track")
        if command == "scaffold":
            sub.add_argument("partition")
            sub.add_argument("--task", type=int, help="issue number for task-specific updates")
            revision = sub.add_mutually_exclusive_group()
            revision.add_argument("--latest", action="store_true")
            revision.add_argument("--ref")
    args = parser.parse_args()
    ref = getattr(args, "ref", None)
    if getattr(args, "latest", False):
        subprocess.run(["git", "fetch", "origin", "main"], cwd=ROOT, check=True)
        ref = subprocess.check_output(["git", "rev-parse", "FETCH_HEAD"], cwd=ROOT, text=True).strip()
    tracks_path = "site/public/tracks.json"
    if ref and not exists(tracks_path, ref):
        tracks_path = "site/tracks.json"
    tracks = json.loads(read(tracks_path, ref))
    if args.command == "check":
        cfg = config.load(ROOT)
        assert len({t["id"] for t in tracks}) == len(tracks)
        for track in tracks:
            _, errors = plan.validate(starter(track), cfg, 0)
            if errors:
                parser.error(f"{track['id']}: {errors}")
            for partition in PARTITIONS:
                scaffold(track, partition, None)
        print(f"Validated {len(tracks)} tracks and their starter plans.")
        return
    track = next((t for t in tracks if t["id"] == args.track), None)
    if not track:
        parser.error(f"unknown track {args.track}")
    if args.command == "plan":
        print(json.dumps(starter(track), indent=2))
    elif args.command == "job":
        print(f"{track['question']}\n\n{track['next']}\n")
        print(f"Starter plan: `python3 research/atlas.py plan {track['id']}`. "
              "Adjust task types, dependencies and priorities to the evidence gap before submission. "
              "This job covers public evidence and impact analysis.\n")
        print(f"<!-- atlas:track {track['id']} -->")
    else:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", args.partition) or (args.task is not None and args.task < 1):
            parser.error("provide a valid partition and positive issue number")
        if not exists(f"research/scaffolds/{args.partition}.md", ref):
            parser.error(f"no scaffold for partition {args.partition}")
        print(f"Scaffold revision: {ref or 'working tree'}\n")
        print(scaffold(track, args.partition, ref, args.task))


if __name__ == "__main__":
    main()
