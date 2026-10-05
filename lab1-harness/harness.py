#!/usr/bin/env python3
"""A minimal coding-agent harness you can read in one sitting.

Everything a production harness (Claude Code, Codex CLI, ...) does is here in
miniature: the agent loop, tools, a permission layer, hooks, project context,
a turn budget, and a run log. Read it top to bottom, then change it.

    python3 harness.py --repo ../sample-project --task "Fix the failing tests" --mock
    python3 harness.py --repo ../sample-project --task "Fix the failing tests"   # real model

The --mock flag swaps the model for a scripted one (mock_model.py) so you can
watch the machinery without an API key.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import hooks

HERE = Path(__file__).resolve().parent

# Price per million tokens for the default model, used for the cost estimate.
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-4-5": (1.00, 5.00)}

SYSTEM_PROMPT = """You are a careful software engineer working in a small repository.
Work in small steps: look around, run the tests, read the code that fails, make the
smallest fix, and run the tests again. Stop when the task is done and say what you changed.
"""

# ---------------------------------------------------------------- tools ----
# Tool schemas are prompts: the model only knows what these descriptions say.
TOOLS = [
    {
        "name": "list_files",
        "description": "List files in the repository (recursively) under an optional subdirectory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Subdirectory, default '.'"}},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the repository and return it with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace one exact occurrence of old_text with new_text in a file. "
            "old_text must match the file exactly, including indentation, and be unique."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the test suite (or one test target like tests.test_money) and return the output.",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string", "description": "Optional unittest target"}},
            "required": [],
        },
    },
]

READ_ONLY_TOOLS = {"list_files", "read_file", "run_tests"}


class Workspace:
    """Executes tools, confined to one repository directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"{rel} is outside the repository")
        return p

    def list_files(self, path: str = ".") -> str:
        base = self._path(path)
        files = [
            str(p.relative_to(self.root))
            for p in sorted(base.rglob("*"))
            if p.is_file() and not any(part.startswith((".", "__pycache__")) for part in p.relative_to(self.root).parts)
        ]
        return "\n".join(files) or "(no files)"

    def read_file(self, path: str) -> str:
        lines = self._path(path).read_text().splitlines()
        return "\n".join(f"{i:4d}  {line}" for i, line in enumerate(lines, 1))

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        p = self._path(path)
        text = p.read_text()
        count = text.count(old_text)
        if count != 1:
            raise ValueError(f"old_text matched {count} times in {path}; it must match exactly once")
        p.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"

    def run_tests(self, target: str = "") -> str:
        cmd = [sys.executable, "-B", "-m", "unittest"] + ([target] if target else ["discover", "-s", "tests", "-t", "."])
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=120)
        out = (proc.stdout + proc.stderr).strip()
        return out[-4000:]  # keep tool results small: context is a budget

    def call(self, name: str, args: dict) -> str:
        return getattr(self, name)(**args)


# ---------------------------------------------------------- permissions ----
def permitted(mode: str, name: str, args: dict) -> tuple[bool, str]:
    """The permission layer. Modes mirror real harnesses:
    plan = read-only, ask = confirm each write, auto = no prompts."""
    if name in READ_ONLY_TOOLS:
        return True, ""
    if mode == "plan":
        return False, "Plan mode is read-only. Describe the change instead of making it."
    if mode == "ask":
        print(f"\n  ? allow {name} {json.dumps(args)[:300]}  [y/N] ", end="", flush=True)
        if sys.stdin.readline().strip().lower() not in {"y", "yes"}:
            return False, "The user declined this action."
    return True, ""


# --------------------------------------------------------------- model ----
class RealModel:
    def __init__(self, model: str, effort: str):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def __call__(self, system: str, messages: list) -> object:
        # Server-side fallbacks retry on another model if a safety classifier
        # declines the request, so a long run isn't killed by one false positive.
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            tools=TOOLS,
            messages=messages,
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )


# ---------------------------------------------------------------- loop ----
def load_context(repo: Path) -> str:
    """Project memory: harnesses prepend files like AGENTS.md / CLAUDE.md."""
    parts = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        f = repo / name
        if f.exists():
            parts.append(f"<project_context file=\"{name}\">\n{f.read_text()}\n</project_context>")
    return "\n".join(parts)


def short(text: str, n: int = 400) -> str:
    text = text.replace("\n", "\n      ")
    return text if len(text) <= n else text[:n] + " ..."


def run(repo: Path, task: str, model, mode: str, max_turns: int, log_path: Path | None, quiet: bool = False) -> dict:
    ws = Workspace(repo)
    system = SYSTEM_PROMPT + "\n" + load_context(repo)
    messages: list = [{"role": "user", "content": task}]
    stats = {"turns": 0, "tool_calls": 0, "blocked": 0, "input_tokens": 0, "output_tokens": 0, "stop": "", "final": ""}
    log = open(log_path, "a") if log_path else None
    say = (lambda *a: None) if quiet else print

    def record(kind: str, **data):
        if log:
            log.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **data}) + "\n")

    record("start", task=task, mode=mode)
    while stats["turns"] < max_turns:
        stats["turns"] += 1
        response = model(system, messages)
        stats["input_tokens"] += response.usage.input_tokens
        stats["output_tokens"] += response.usage.output_tokens
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text" and block.text.strip():
                say(f"\n[turn {stats['turns']}] model: {short(block.text, 800)}")
                record("text", text=block.text)

        if response.stop_reason == "refusal":
            stats["stop"] = "refusal"
            break
        if response.stop_reason == "max_tokens":
            stats["stop"] = "max_tokens"
            break
        if response.stop_reason != "tool_use":
            stats["stop"] = "done"
            stats["final"] = " ".join(b.text for b in response.content if b.type == "text")
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            stats["tool_calls"] += 1
            name, args = block.name, dict(block.input)
            say(f"  -> {name}({short(json.dumps(args), 200)})")

            # Policy hooks run first, so the human is only asked about actions policy allows.
            ok, reason = hooks.pre_tool(name, args, repo)
            if ok:
                ok, reason = permitted(mode, name, args)
            if not ok:
                stats["blocked"] += 1
                say(f"  x  blocked: {reason}")
                record("blocked", tool=name, args=args, reason=reason)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Blocked: {reason}", "is_error": True})
                continue
            try:
                output, is_error = ws.call(name, args), False
            except Exception as e:  # tool errors go back to the model, they don't crash the loop
                output, is_error = f"{type(e).__name__}: {e}", True
            hooks.post_tool(name, args, output, repo)
            say(f"  <- {short(output)}")
            record("tool", tool=name, args=args, output=output[:2000], error=is_error)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error})
        # All results for one assistant turn go back in a single user message.
        messages.append({"role": "user", "content": results})
    else:
        stats["stop"] = "turn_budget"

    record("end", **stats)
    if log:
        log.close()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--task", required=True)
    ap.add_argument("--mock", action="store_true", help="use the scripted model (no API key needed)")
    ap.add_argument("--mode", choices=["plan", "ask", "auto"], default="ask")
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--log", type=Path, help="append a JSONL trace of the run here")
    ap.add_argument("--summary", type=Path, help="write the final stats as JSON here")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.mock:
        from mock_model import MockModel

        model = MockModel(a.task)
    else:
        model = RealModel(a.model, a.effort)

    stats = run(a.repo, a.task, model, a.mode, a.max_turns, a.log, a.quiet)
    in_price, out_price = PRICES.get(a.model, (0, 0))
    stats["est_cost_usd"] = 0.0 if a.mock else round(stats["input_tokens"] / 1e6 * in_price + stats["output_tokens"] / 1e6 * out_price, 4)
    if a.summary:
        a.summary.write_text(json.dumps(stats, indent=2))
    if not a.quiet:
        print(
            f"\n== {stats['stop']} after {stats['turns']} turns, {stats['tool_calls']} tool calls, "
            f"{stats['blocked']} blocked, {stats['input_tokens']:,} in / {stats['output_tokens']:,} out tokens, "
            f"~${stats['est_cost_usd']}"
        )


if __name__ == "__main__":
    main()
