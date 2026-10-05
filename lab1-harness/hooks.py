"""Hooks: deterministic code that runs around every tool call.

The model is probabilistic; hooks are not. Anything that must *always* happen
(or must never happen) belongs here rather than in a prompt. Claude Code has the
same idea: PreToolUse / PostToolUse hooks in .claude/settings.json (see lab 2).

pre_tool returns (allowed, reason). A refusal is sent back to the model as an
error tool result, so it can change course instead of crashing.
"""
from __future__ import annotations

from pathlib import Path

PROTECTED_DIRS = ("tests/",)
SECRET_NAMES = (".env", "id_rsa", "credentials")


def pre_tool(name: str, args: dict, repo: Path) -> tuple[bool, str]:
    path = str(args.get("path", ""))
    if name == "edit_file" and path.startswith(PROTECTED_DIRS):
        # The classic agent failure: "make the tests pass" by editing the tests.
        return False, f"{path} is a test file. Fix the code under test, not the test."
    if any(s in path for s in SECRET_NAMES):
        return False, f"{path} looks like a secret and is off limits."
    return True, ""


def post_tool(name: str, args: dict, output: str, repo: Path) -> None:
    # Example: keep an audit trail of every edit, outside the model's control.
    if name == "edit_file" and not output.startswith(("ValueError", "PermissionError")):
        with open(repo / ".agent-edits.log", "a") as f:
            f.write(f"{args['path']}\n")
