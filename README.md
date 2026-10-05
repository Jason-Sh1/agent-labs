# Agent Labs

Five small, runnable setups for learning how agent harnesses, orchestrators and agent environments work. Run them, break them, and change them. Everything works against `sample-project/`, a tiny Python ledger with three seeded bugs and tests that catch them.

How the labs map to a learning path: labs 1 and 3 are the core of Patchwork (stages 3 and 5), lab 2 is stage 2, and lab 4 is stage 4.

| Lab | You'll see | Layer |
|---|---|---|
| 1. `lab1-harness/` | An agent loop in ~300 lines: tools, permissions, hooks, context, budget, trace | Harness |
| 2. `lab2-claude-code/` | The same ideas configured in a real harness: CLAUDE.md, hooks, a skill, a subagent | Harness (production) |
| 3. `lab3-orchestrator/` | Parallel agents in git worktrees, code-based verification, a human merge gate | Orchestrator |
| 4. `lab4-evals/` | Pass rate, turns, tokens and cost per task across repeated trials | Measurement |
| 5. `lab5-sandbox/` | The agent running in a locked-down container | Environment (ADE) |

## Setup

You need Python 3.10+ and git. Every lab has a `--mock` mode that replays a scripted model, so you can watch the machinery first without an API key or any cost.

For the real model:

```bash
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # from console.anthropic.com
```

The default model is `claude-opus-5-5`. One real run of lab 1 on all three bugs should cost well under a dollar (an estimate; the harness prints the actual token count and cost after every run). Use `--model claude-sonnet-5-5` or `--effort low` to compare cheaper settings in lab 4.

Run the labs on copies, never on `sample-project/` itself, so you can always reset:

```bash
cp -r sample-project /tmp/play
```

---

## Lab 1: a harness you can read

```bash
cd lab1-harness
python3 harness.py --repo /tmp/play --task "Fix all the failing tests" --mock --mode auto
```

Read `harness.py` top to bottom first. Then watch the run and match each line of output to the code that produced it. The mock deliberately tries to edit a test file on turn 3, and `hooks.py` blocks it.

**Try**
- `--mode ask`: approve or decline each edit yourself. `--mode plan`: read-only, the agent can only investigate.
- `--log run.jsonl`, then read the trace. This is what observability tools are built on.
- Drop `--mock` and run the real model on a fresh copy. Compare its path to the scripted one.

**Break it** (each of these is a real failure mode in production agents)
- Delete the `protect tests` check in `hooks.py` and ask the real model to "make the tests pass, whatever it takes". Does it edit the tests?
- Set `--max-turns 3`. What does the agent leave behind when it runs out of budget?
- Make the tool descriptions in `TOOLS` vague (for example, "edits a file"). Watch the error rate on `edit_file` go up.
- Remove `"-B"` from `run_tests`. We hit this while building the labs: Python's bytecode cache can serve the *old* code when an edit lands in the same second and doesn't change the file's size, so a correct fix looks like it failed. Environment bugs like this make agents chase ghosts.
- Delete `AGENTS.md` from your copy. Does the agent still know not to touch tests and to keep money in cents?

**Where you come in**: you write the task, decide the permission mode, own the hooks (policy), and judge the final diff. The agent's closing summary is a claim, not evidence. The mock says "Done" even when you declined every edit.

**Make it yours**
- Add a `search` tool (grep). Add a `git_diff` tool so the agent can review its own work.
- Add context compaction: when `messages` gets long, summarize old turns.
- Add a hook that runs the tests after every edit and appends the result to the tool output.
- Port it to the SDK's tool runner (`client.beta.messages.tool_runner`) and compare how much code disappears.

## Lab 2: the same ideas in Claude Code

```bash
cp -r sample-project /tmp/cc && cp -r lab2-claude-code/. /tmp/cc/
cd /tmp/cc && git init -q && git add -A && git commit -qm baseline
claude
```

Accept the workspace trust prompt (until you do, Claude Code ignores the project's `permissions.allow` list). Then ask: *"Fix the failing tests."*

What's in `.claude/`:
- `CLAUDE.md` imports `AGENTS.md` and adds working agreements.
- `settings.json` holds permission allow and deny rules, plus three hooks:
  - `protect_tests.py` (PreToolUse) blocks edits under `tests/`.
  - `log_edits.py` (PostToolUse) writes an audit trail to `.claude/edits.log`.
  - `stop_until_green.py` (Stop) refuses to let Claude finish while tests are red.
- `skills/fix-failing-tests/` is a procedure Claude loads when the task matches.
- `agents/test-reviewer.md` is a read-only subagent that reviews the diff with fresh context.

**What we saw when we ran this** (headless, `claude -p`): Claude fixed two bugs and tried to stop. The Stop hook ran the suite, found the third bug, and sent Claude back to work. The test-reviewer subagent ran *before* that last fix, so its review didn't cover it, and Claude said so. Bash approvals also blocked it from running tests because the workspace wasn't trusted. Those are all real seams where a human has to look.

**Try**: run `/hooks` and `/agents` inside Claude Code to see what's loaded. Ask it to "edit the test to pass" and watch the hook stop it. Remove the Stop hook and see whether it still finds all three bugs.

**Make it yours**: turn a correction you've given Claude more than once into a CLAUDE.md line, a skill or a hook. Pick based on whether it's knowledge (CLAUDE.md), a procedure (skill), or a rule that must always hold (hook).

## Lab 3: an orchestrator with a human gate

```bash
cd lab3-orchestrator
python3 orchestrate.py --mock --auto-approve      # see the whole pipeline
python3 orchestrate.py                            # real model, you approve each merge
```

It creates one git worktree per task in `tasks.json`, runs a lab 1 harness in each one in parallel, verifies every branch with the task's own test (never by trusting the worker's summary), flags branches that touched tests, shows you each diff, and merges only what you approve. Then it runs the full suite on the merged result.

**Try**
- Look at `runs/<timestamp>/`: one trace per worker, and real git branches you can inspect with `git log --all --graph`.
- Add a fourth task to `tasks.json` that overlaps an existing one (for example, "make format_cents support euros"). Watch for a merge conflict, which the orchestrator leaves for you.

**Break it**
- Give a task a vague description ("make money handling better") with a `check` that doesn't really test it. The worker will "succeed".
- Run with `--auto-approve` and a weakened hook. This is how bad changes land when nobody is in the loop.

**Where you come in**: splitting work into independent, checkable tasks is the hardest part, and it's yours. So is the merge decision. Notice that workers run in `auto` mode because nobody is there to answer prompts, which is why the hooks and the verifier matter more here than in lab 1.

**Make it yours**
- Best-of-N: run the same task 3 times and merge the passing branch with the smallest diff.
- Add a reviewer step: a second harness run in `plan` mode that reads each diff and votes.
- Trigger it from a GitHub Action on issues labeled `agent`.

## Lab 4: measure it

```bash
cd lab4-evals
python3 evals.py --mock --trials 2
python3 evals.py --trials 3                         # real model
python3 evals.py --trials 3 --effort low            # did that hurt?
python3 evals.py --trials 3 --model claude-sonnet-5-5
```

Each trial starts from a clean copy. A trial passes only if the task's check passes and no test file changed. Results go to `results/*.csv`.

**Use it whenever you change anything** in lab 1: a prompt, a tool description, a hook, the model or effort. Without this, "it seems better" is a guess. With three trials per task you will see that agents are not deterministic: the same task can pass twice and fail once.

**Make it yours**: add harder tasks (a feature request with tests you write first, or a bug that spans two files). Add a column for "edited files outside the task's area". Plot pass rate against cost. This is Patchwork's eval dashboard in embryo.

## Lab 5: a sandboxed environment

```bash
docker build -f lab5-sandbox/Dockerfile -t agent-lab .
docker run --rm --network none agent-lab python3 lab1-harness/harness.py \
  --repo sample-project --task "Fix all the failing tests" --mock --mode auto
```

The container has the repo, Python, git, a non-root user, and with `--network none`, no internet at all. That's the core of every cloud agent environment (Claude Code on the web, Codex cloud, Devin): an isolated machine where the agent can run tests freely and can't reach anything you didn't allow. *(Docker wasn't available where these labs were built, so lab 5 is the one setup not run end to end.)*

**Try**: add a fake `.env` with a "secret" to the image, then ask the real model to "summarize every file in the repo". Does the hook in lab 1 stop it? What would stop it from sending that data out if the network were open? That's the "lethal trifecta" from the explainer: private data, untrusted input, and a way out.

---

## Where agents fall short, and the human's job

You'll hit each of these in the labs:

1. **Vague specs.** The agent optimizes for whatever it can check. If the check is weak, so is the result. *You write the task and the test.*
2. **Gaming the check.** Editing tests, special-casing inputs. *You own the guardrails (hooks) and the review.*
3. **Claimed success.** Summaries say "done" regardless. *Verify with code, not with the transcript.*
4. **Environment bugs.** Stale caches, missing deps, no network. The agent blames its code. *You maintain the environment.*
5. **Context drift on long runs.** It forgets constraints from early on. *Keep tasks small and put rules in context files or hooks.*
6. **Merge and coordination.** Parallel work collides. *You decide how to split work and what lands.*
7. **Cost and loops.** Agents retry forever if allowed. *You set budgets and watch the evals.*

The workflow these labs push you toward: a human writes a checkable spec, agents do the work in isolated environments, code verifies the results, and a human approves what lands. Improving that workflow means moving a check from your head into a hook, a test or an eval.
