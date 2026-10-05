"""Stop hook: don't let Claude end its turn while the test suite is red.

Exit code 2 blocks the stop and feeds stderr back to Claude, so it keeps working.
stop_hook_active is true when Claude is already continuing because of this hook;
we let it stop then, so a task it can't solve doesn't loop forever."""
import json
import os
import subprocess
import sys

event = json.load(sys.stdin)
if event.get("stop_hook_active"):
    sys.exit(0)
root = os.environ.get("CLAUDE_PROJECT_DIR", ".")
proc = subprocess.run(
    [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
    cwd=root, capture_output=True, text=True,
)
if proc.returncode != 0:
    tail = (proc.stdout + proc.stderr).strip()[-1500:]
    print(f"Tests are still failing, so you're not done yet:\n{tail}", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
