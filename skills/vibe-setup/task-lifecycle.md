# Task worktrees: Phase 1

The source package now provides read-only inspection and verified worktree
startup through `workflow.py`. Recoverable installation, PR synchronization and
automatic skill/client wiring remain later phases. The existing `install.py`
still installs only the subagent component; it does not install or activate this
helper or its policy asset yet.

## Inspect first

Run the reviewed package helper from its actual location:

```sh
python3 /path/to/vibe-setup/workflow.py inspect /absolute/project --client app --client vscode
```

Inspection accepts a nested application directory and reports its owning Git
root. A non-Git umbrella returns immediate child repository candidates and asks
for explicit selection; it does not enroll siblings or scan the entire machine.
The result includes dirty/staged paths, instruction locations, settings presence,
configured and effective commit identities, redacted remote transport metadata,
tool availability, and named publication prerequisites. It does not load client
settings, inspect credential stores, sign in, validate PR permissions, or claim
client execution. Read-only inspection never means setup is complete.

The agent still reads applicable instructions, checks skill discovery and project
requirements, chooses the base/remote deliberately, and preserves current model,
reasoning, provider, authentication, permissions and unrelated work. Project
trust must precede hook trust; see [installation and trust](README.md#3-establish-trust-and-actual-execution).

## Start before implementation

Prefer the client's native worktree creation. Creation does not move the chat or
its workers. Verify the returned path and branch with this helper before edits.
If native creation is unavailable or fails, the helper can create the worktree
with Git. Never substitute the primary checkout after either failure.

Use one UUID per task. Pass startup JSON through stdin, with explicit values:

```sh
python3 /path/to/vibe-setup/workflow.py start /absolute/source < task-start.json
```

```json
{
  "task_id": "0652f3d5-16e3-4a59-a1b3-f398149914f3",
  "worktree": "/absolute/task-worktree",
  "branch": "task/feature-name",
  "base": "main",
  "create": true,
  "adopt_existing": false
}
```

Choose the actual reviewed base; `main` above is only an example. A new task
branch must not already exist. The helper never resets, stashes, force-creates,
copies dirty source changes, or changes remotes/identity. Supply canonical
absolute paths, separate from existing checkouts; symlink aliases are refused.
Use the same source checkout and request when resuming a task.

For a worktree already created by the native tool or a human, use `create=false`
and `adopt_existing=true` only after confirming task ownership. Adoption verifies
the exact Git root, registered path, common Git directory, branch, linked-worktree
identity and ancestry from the selected base. Primary, foreign, detached,
unregistered, nested and conflicting task worktrees are refused. Existing task
bindings are checked again on every startup; a stale success record is not proof.

Before writing, require `status=ok` and `implementation=worktree_verified`.
Use the returned `context.command_cwd` for commands and
`context.worker_cwd` in writable worker assignments. Reverify after changing
directories, switching branches, moving the worktree or resuming an interrupted
task. The helper validates its own operations; it cannot intercept arbitrary
native edits or guarantee other tools obey those roots.

## Failure and manual recovery

Outputs keep `implementation` separate from `delivery` and include `changes`,
`pending_user_actions`, `evidence_ref`, and `next_action`. Exit codes are:

- `0`: the requested operation succeeded, including inspection or explicit opt-out.
- `2`: a manual action or decision is needed.
- `3`: invalid or unsafe state blocks dependent work.

When creation fails, preserve progress, report the pending action, and guide the
user through manual creation or repair. Where safe, the helper supplies a quoted
Git command using the inspected source, requested branch/path and resolved base
commit. When the branch/path already exists, it requests inspection instead of
retrying blindly. Rerun the same request after the action; confirm ownership for
newly adopted worktrees. Do not edit until verification passes.

Startup uses ordinary Git, including applicable user-configured Git behavior.
A failed or timed-out command may leave a branch or worktree behind. Reconcile
that state; never remove it automatically. A missing previously verified
worktree requires manual recovery rather than silently starting over.

Recovery records live under `<git common directory>/vibe-setup/tasks/`, outside
tracked files. An advisory startup lock coordinates cooperating helper calls.
Records bind task, source, worktree, branch and the original base commit. They
contain no credentials and are bookkeeping, not a tamper-proof enforcement
boundary. Leave them in place when an operation is interrupted.

Missing Git/PR access is a publication prerequisite. It does not prevent verified
local work. Phase 1 does not push, create PRs or claim delivery readiness. The
coordinator currently handles publication under the approved rules: start PRs
as `[BLOCKED]`, attempt one synchronization per phase, preserve human text, and
promote to `[READY]` only after non-draft status and applicable merge requirements
are established. If automation fails, provide concrete manual actions and state
what remains unverified. Never merge automatically.

## Explicit opt-out

The absence of `.codex/vibe-workflow.toml` means enabled. This packaged asset is
the future installation default, not native Codex configuration:

```toml
schema_version = 1

[task_lifecycle]
enabled = true
```

Preserve an explicit `enabled=false` in the selected source checkout. Startup
then reports `implementation=disabled` and creates no worktree or task state.
That result does not authorize edits that other project rules prohibit. Never
disable the feature to bypass a failure. Invalid/unknown lifecycle fields stop
startup; unrelated policy tables are left untouched. No model, authentication,
permission or global setting is changed by this helper.
