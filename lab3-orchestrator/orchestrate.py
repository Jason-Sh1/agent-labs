#!/usr/bin/env python3
"""Fan out one agent per task, verify each result, and let a human decide what merges.

    python3 orchestrate.py --mock                 # scripted model, no API key
    python3 orchestrate.py                        # real model, asks before merging
    python3 orchestrate.py --auto-approve         # no human gate (watch what that costs you)

What it does, in order:
  1. Copies sample-project into runs/<timestamp>/main as a fresh git repo.
  2. Creates one git worktree + branch per task in ../tasks.json, so parallel
     agents never touch the same files on disk.
  3. Runs lab1's harness in each worktree at the same time (auto permission
     mode, because nobody is there to answer prompts).
  4. Verifies each branch independently: does the task's own check pass, does
     the whole suite still pass, and how big is the diff.
  5. Shows you the scoreboard and diffs, and merges only what you approve.
  6. Runs the full suite on the merged result.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
HARNESS = LABS / "lab1-harness" / "harness.py"


def sh(*cmd: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def git(*args: str, cwd: Path, check: bool = True) -> str:
    return sh("git", *args, cwd=cwd, check=check).stdout.strip()


def tests_pass(repo: Path, target: str = "") -> bool:
    cmd = [sys.executable, "-B", "-m", "unittest"] + ([target] if target else ["discover", "-s", "tests", "-t", "."])
    return subprocess.run(cmd, cwd=repo, capture_output=True).returncode == 0


def setup(run_dir: Path) -> Path:
    main = run_dir / "main"
    shutil.copytree(LABS / "sample-project", main, ignore=shutil.ignore_patterns("__pycache__", ".agent-edits.log"))
    (main / ".gitignore").write_text("__pycache__/\n.agent-edits.log\n")
    git("init", "-q", "-b", "main", cwd=main)
    git("-c", "user.name=lab", "-c", "user.email=lab@example.com", "add", "-A", cwd=main)
    git("-c", "user.name=lab", "-c", "user.email=lab@example.com", "commit", "-qm", "baseline", cwd=main)
    return main


def run_worker(main: Path, run_dir: Path, task: dict, args) -> dict:
    """One worker = one isolated worktree + one harness process."""
    wt = run_dir / f"wt-{task['id']}"
    git("worktree", "add", "-q", "-b", f"agent/{task['id']}", str(wt), cwd=main)
    cmd = [sys.executable, str(HARNESS), "--repo", str(wt), "--task", task["task"], "--mode", "auto",
           "--max-turns", str(args.max_turns), "--log", str(run_dir / f"{task['id']}.jsonl"),
           "--summary", str(run_dir / f"{task['id']}.summary.json"), "--quiet"]
    if args.mock:
        cmd.append("--mock")
    if args.model:
        cmd += ["--model", args.model]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result = {"id": task["id"], "worktree": wt, "seconds": round(time.time() - started, 1), "error": proc.stderr.strip()[-500:]}
    summary_file = run_dir / f"{task['id']}.summary.json"
    result.update(json.loads(summary_file.read_text()) if summary_file.exists() else {"stop": "crashed"})

    # Verification is done by code, not by asking the worker if it succeeded.
    git("-c", "user.name=agent", "-c", "user.email=agent@example.com", "add", "-A", cwd=wt)
    git("-c", "user.name=agent", "-c", "user.email=agent@example.com", "commit", "-qm", f"agent: {task['id']}", cwd=wt, check=False)
    result["own_check"] = tests_pass(wt, task["check"])
    result["full_suite"] = tests_pass(wt)
    result["diff_stat"] = git("diff", "--shortstat", "main", cwd=wt) or "no changes"
    result["touched_tests"] = any(f.startswith("tests/") for f in git("diff", "--name-only", "main", cwd=wt).splitlines())
    return result


def scoreboard(results: list[dict]) -> None:
    print(f"\n{'task':<18}{'stop':<12}{'own check':<11}{'suite':<8}{'turns':<7}{'blocked':<9}{'secs':<7}diff")
    for r in results:
        flag = "  <- edited tests!" if r.get("touched_tests") else ""
        print(f"{r['id']:<18}{r.get('stop',''):<12}{'pass' if r['own_check'] else 'FAIL':<11}"
              f"{'pass' if r['full_suite'] else 'fail':<8}{r.get('turns',0):<7}{r.get('blocked',0):<9}{r['seconds']:<7}{r['diff_stat']}{flag}")
    print("\n(suite 'fail' is expected per branch: each worker only fixes its own bug.)")


def human_gate(main: Path, results: list[dict], auto: bool) -> list[dict]:
    """The human's job: decide what is good enough to land."""
    approved = []
    for r in results:
        if not r["own_check"] or r["touched_tests"]:
            print(f"\n-- skipping {r['id']}: {'its check fails' if not r['own_check'] else 'it edited tests'}")
            continue
        if auto:
            approved.append(r)
            continue
        print(f"\n===== {r['id']} =====")
        print(git("diff", "main", f"agent/{r['id']}", cwd=main))
        if input(f"Merge {r['id']}? [y/N] ").strip().lower() in {"y", "yes"}:
            approved.append(r)
    return approved


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--model", default="")
    ap.add_argument("--auto-approve", action="store_true", help="skip the human review gate")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--tasks", type=Path, default=LABS / "tasks.json")
    args = ap.parse_args()

    tasks = json.loads(args.tasks.read_text())
    run_dir = Path(__file__).resolve().parent / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    main_repo = setup(run_dir)
    print(f"Run directory: {run_dir}\nDispatching {len(tasks)} workers ({'mock' if args.mock else 'real'} model)...")

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(lambda t: run_worker(main_repo, run_dir, t, args), tasks))
    for r in results:
        if r["error"]:
            print(f"\n[{r['id']}] stderr: {r['error']}")
    scoreboard(results)

    approved = human_gate(main_repo, results, args.auto_approve)
    merged, conflicts = [], []
    for r in approved:
        out = sh("git", "-c", "user.name=lab", "-c", "user.email=lab@example.com", "merge", "--no-edit", "-q",
                 f"agent/{r['id']}", cwd=main_repo, check=False)
        if out.returncode == 0:
            merged.append(r["id"])
        else:
            git("merge", "--abort", cwd=main_repo, check=False)
            conflicts.append(r["id"])

    print(f"\nMerged: {', '.join(merged) or 'nothing'}")
    if conflicts:
        print(f"Merge conflicts (left for you): {', '.join(conflicts)}")
    print(f"Full suite on merged main: {'PASS' if tests_pass(main_repo) else 'FAIL'}")
    print(f"Traces: {run_dir}/*.jsonl")


if __name__ == "__main__":
    main()
