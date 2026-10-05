#!/usr/bin/env python3
"""Run the harness on every task several times and measure it.

    python3 evals.py --mock                          # check the machinery
    python3 evals.py --trials 3                      # real model, 3 runs per task
    python3 evals.py --trials 3 --effort low         # compare a setting change
    python3 evals.py --tasks my_tasks.json           # your own tasks

Each trial starts from a fresh copy of sample-project, so runs can't leak into
each other. A trial passes only if the task's check passes, the full suite
passes, and no test file was modified. Results go to results/<timestamp>.csv.

This is the habit that separates "I think my prompt change helped" from
"pass rate went from 6/9 to 9/9 and cost went up 20%".
"""
from __future__ import annotations

import argparse
import csv
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
HARNESS = LABS / "lab1-harness" / "harness.py"
SAMPLE = LABS / "sample-project"


def passes(repo: Path, target: str = "") -> bool:
    cmd = [sys.executable, "-B", "-m", "unittest"] + ([target] if target else ["discover", "-s", "tests", "-t", "."])
    return subprocess.run(cmd, cwd=repo, capture_output=True).returncode == 0


def tests_untouched(repo: Path) -> bool:
    cmp = filecmp.dircmp(SAMPLE / "tests", repo / "tests", ignore=["__pycache__"])
    return not (cmp.diff_files or cmp.left_only or cmp.right_only)


def trial(task: dict, n: int, args) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(SAMPLE, repo, ignore=shutil.ignore_patterns("__pycache__"))
        summary = Path(tmp) / "summary.json"
        cmd = [sys.executable, str(HARNESS), "--repo", str(repo), "--task", task["task"], "--mode", "auto",
               "--max-turns", str(args.max_turns), "--effort", args.effort, "--model", args.model,
               "--summary", str(summary), "--quiet"]
        if args.mock:
            cmd.append("--mock")
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        stats = json.loads(summary.read_text()) if summary.exists() else {"stop": "crashed"}
        row = {
            "task": task["id"], "trial": n, "stop": stats.get("stop"),
            "check": passes(repo, task["check"]), "suite": passes(repo), "tests_untouched": tests_untouched(repo),
            "turns": stats.get("turns", 0), "tool_calls": stats.get("tool_calls", 0), "blocked": stats.get("blocked", 0),
            "input_tokens": stats.get("input_tokens", 0), "output_tokens": stats.get("output_tokens", 0),
            "cost_usd": stats.get("est_cost_usd", 0), "seconds": round(time.time() - t0, 1),
        }
        # Only the task's own check is required; the other seeded bugs are still there.
        row["passed"] = row["check"] and row["tests_untouched"]
        if proc.returncode and not args.mock:
            row["stop"] = f"crashed: {proc.stderr.strip().splitlines()[-1][:120] if proc.stderr.strip() else '?'}"
        return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--tasks", type=Path, default=LABS / "tasks.json")
    args = ap.parse_args()

    tasks = json.loads(args.tasks.read_text())
    rows = [trial(t, n, args) for t in tasks for n in range(1, args.trials + 1)]

    print(f"\n{'task':<18}{'pass rate':<11}{'avg turns':<11}{'avg tokens':<12}{'avg cost':<10}{'blocked'}")
    for t in tasks:
        rs = [r for r in rows if r["task"] == t["id"]]
        k = len(rs)
        print(f"{t['id']:<18}{sum(r['passed'] for r in rs)}/{k:<9}{sum(r['turns'] for r in rs)/k:<11.1f}"
              f"{sum(r['input_tokens']+r['output_tokens'] for r in rs)/k:<12,.0f}${sum(r['cost_usd'] for r in rs)/k:<9.4f}{sum(r['blocked'] for r in rs)}")
    total = sum(r["passed"] for r in rows)
    print(f"\nOverall: {total}/{len(rows)} passed, total cost ${sum(r['cost_usd'] for r in rows):.4f}"
          f"  ({args.model}, effort={args.effort}{', MOCK' if args.mock else ''})")
    for r in rows:
        if not r["passed"]:
            why = "edited tests" if not r["tests_untouched"] else f"check failed (stop={r['stop']})"
            print(f"  failed: {r['task']} trial {r['trial']}: {why}")

    out = Path(__file__).resolve().parent / "results" / f"{time.strftime('%Y%m%d-%H%M%S')}.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
