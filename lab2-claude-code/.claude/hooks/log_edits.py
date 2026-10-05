"""PostToolUse hook: append every edited path to .claude/edits.log (an audit trail
Claude can't skip or forget)."""
import json
import os
import sys
import time

event = json.load(sys.stdin)
path = event.get("tool_input", {}).get("file_path", "?")
log = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), ".claude", "edits.log")
with open(log, "a") as f:
    f.write(f"{time.strftime('%H:%M:%S')} {event.get('tool_name')} {path}\n")
