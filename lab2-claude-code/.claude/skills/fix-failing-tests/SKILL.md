---
name: fix-failing-tests
description: Use when asked to fix failing tests or a bug report in this repo. A step-by-step procedure for finding the root cause and making a minimal fix.
---

# Fixing failing tests in tinyledger

1. Run the suite: `python3 -B -m unittest discover -s tests -t .`
2. Pick one failure. Read the assertion and the traceback; write down, in one
   sentence, what the code does versus what the test expects.
3. Read the function under test. Find the line responsible. Don't guess from
   the name.
4. Make the smallest change that fixes that cause. Money stays in integer cents.
5. Re-run just that test module, then the whole suite.
6. Repeat for the next failure. Never edit files under `tests/`.
7. Finish with a short summary: each bug, its root cause, and the line you changed.
