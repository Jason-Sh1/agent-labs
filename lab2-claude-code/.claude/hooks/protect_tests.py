"""PreToolUse hook: refuse edits to tests/. Exit code 2 blocks the tool call and
sends stderr back to Claude as the reason."""
import json
import sys

event = json.load(sys.stdin)
path = event.get("tool_input", {}).get("file_path", "")
if "/tests/" in path.replace("\\", "/") or path.startswith("tests/"):
    print(f"{path} is a test file. Fix the code under test instead of the test.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
