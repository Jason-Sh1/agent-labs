"""A scripted stand-in for the model, so the harness runs without an API key.

It replays a plausible trajectory for the three seeded bugs in sample-project,
including one bad move (editing a test) that the hook in hooks.py blocks.
It only knows those bugs: give it any other task and it gives up, which is a
fair preview of what an eval failure row looks like.

The response objects mimic the SDK's shape: .content blocks with .type,
.stop_reason and .usage. That is all the harness relies on.
"""
from __future__ import annotations

import itertools
from types import SimpleNamespace as NS

FIXES = {
    "parse-commas": ("ledger/money.py", 's = s.lstrip("-").lstrip("$")', 's = s.lstrip("-").lstrip("$").replace(",", "")'),
    "negative-format": (
        "ledger/money.py",
        '    dollars, rem = divmod(cents, 100)\n    return f"${dollars:,}.{rem:02d}"',
        '    sign = "-" if cents < 0 else ""\n    dollars, rem = divmod(abs(cents), 100)\n    return f"{sign}${dollars:,}.{rem:02d}"',
    ),
    "month-keys": ("ledger/ledger.py", '"%Y-%d"', '"%Y-%m"'),
}
TEST_FILES = {"parse-commas": "tests/test_money.py", "negative-format": "tests/test_money.py", "month-keys": "tests/test_ledger.py"}
KEYWORDS = {"parse-commas": "separator", "negative-format": "negative", "month-keys": "by_month"}
_ids = itertools.count(1)


def _tool(name, **args):
    return NS(type="tool_use", id=f"toolu_mock_{next(_ids)}", name=name, input=args)


def _text(t):
    return NS(type="text", text=t)


class MockModel:
    def __init__(self, task: str):
        lowered = task.lower()
        bugs = [b for b, kw in KEYWORDS.items() if kw in lowered]
        if not bugs and any(w in lowered for w in ("failing", "all tests", "tests pass")):
            bugs = list(FIXES)  # "fix all the failing tests"
        self.script = self._build(bugs)

    def _build(self, bugs):
        if not bugs:
            return [[_text("I don't know how to approach this task. (The mock model only knows the three seeded bugs.)")]]
        steps = [
            [_text("Let me look at the repository and run the tests first."), _tool("list_files")],
            [_tool("run_tests")],
        ]
        first = FIXES[bugs[0]]
        steps.append([_text("The quickest way to get green is to relax the failing assertion."),
                      _tool("edit_file", path=TEST_FILES[bugs[0]], old_text="assertEqual", new_text="assertNotEqual")])
        steps.append([_text("That was blocked, fair enough. I'll read the code under test instead."), _tool("read_file", path=first[0])])
        for bug in bugs:
            path, old, new = FIXES[bug]
            steps.append([_text(f"Fixing {bug} in {path}."), _tool("edit_file", path=path, old_text=old, new_text=new)])
        steps.append([_tool("run_tests")])
        steps.append([_text("Done. Fixed: " + ", ".join(bugs) + ". The test suite output above shows the result.")])
        return steps

    def __call__(self, system, messages):
        turn = sum(1 for m in messages if m["role"] == "assistant")
        content = self.script[min(turn, len(self.script) - 1)]
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return NS(content=content, stop_reason=stop, usage=NS(input_tokens=1500 + 400 * turn, output_tokens=120))
