# Task worktrees, publication and cleanup

The self-contained installed skill provides read-only inspection, verified
worktree startup, [recoverable setup](onboarding.md), PR synchronization and
ordered cleanup through `workflow.py`. The onboarding skill coordinates these
operations and adds direct helper instructions for normal project tasks. The existing `install.py`
still installs only the subagent component; it does not install the helper or
policy asset. Run the helper from the complete reviewed package.

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
local work. The helper uses the existing Git transport and authenticated GitHub
CLI; it never logs in, switches accounts or changes credentials. The coordinator
prefers sufficient connected tools when available and can use the same structured
inputs for manual publication. Never merge automatically.

## Synchronize one planned milestone

Use one to four routine checkpoints, or one synchronization per declared phase.
Keep stable milestone IDs and one event UUID per synchronization, including retries.
A blocker event records the cause and resumption condition. Stop writable workers
before taking a snapshot; update the PR before reporting in chat. If publication
fails, report the blocker with “PR update pending” and the concrete manual action.

Inspect explicit publishable files with `inspect WORKTREE --task-id TASK_UUID
--file relative/path` (repeat `--file`). Retain `publication_snapshot.digest` and
collect checks/review evidence for that exact snapshot. Exclude credentials and
private task records. Do not stage unrelated changes. The helper verifies supplied
evidence fingerprints; outcomes and writer/host ownership remain coordinator
reports, not an independent test runner or host attestation.

Pass `sync WORKTREE` JSON through stdin with exactly `task_id` and `event`.
The event contains these required fields:

| Fields | Contract |
| --- | --- |
| `event_id`, `kind`, `milestone` | UUID; `checkpoint`, `blocker`, `ready` or `reopen`; planned ID |
| `schedule` | `{"mode":"phases","ids":["phase-1","phase-2"]}` or `checkpoints` with at most four IDs |
| `publication` | Explicit `host`, `repository` (`owner/repo`), `remote`, `base`, expected GitHub `actor`, and every task-owned `branches` name, including prior branches |
| `usage` | Fresh `{"kind":"git","scope":"exclusive","writers":[]}`; list each owned writer as `{"id":"worker","state":"stopped"}`; use `managed`, `shared` or `pinned` when applicable |
| `files`, `snapshot`, `message`, `title` | Explicit relative file list, inspected digest, commit message, PR title |
| `summary`, `progress`, `remaining`, `blockers` | Human-readable text; blocker text includes its resumption condition; `ready` requires no blockers |
| `validation` | `snapshot` matching the event, `checks` list and one independent `review` entry |

Each validation entry contains exactly `name`, `outcome` (`passed`, `failed` or
`not_run`), `path` (private evidence file), and its SHA-256 `sha256`. A `ready`
event requires at least one check and an independent review, all passed. Keep
request/evidence files outside tracked source; requests are limited to 64 KiB.
The task's schedule and publication identity remain fixed after first use;
changed branches or destinations require explicit reconciliation of the inventory.

The helper commits only the named files, pushes normally without force, verifies
the remote commit and looks up every matching PR before creation. New PRs start
draft with `[BLOCKED]`. One marked body section contains summary, progress,
validation, remaining work and blockers. Human title suffixes and text outside
that section survive updates. Edited, missing, malformed or foreign managed
sections require reconciliation.

A PR may leave draft while still `[BLOCKED]` to receive reviews. `[READY]` requires
current local evidence, confirmed non-draft status and observed passing checks,
reviews and mergeability for the exact head. Unknown remote facts remain pending.
Before further edits to a ready PR, send `reopen` and verify `[BLOCKED]`; failure
pauses that PR's implementation. Other publication failures can leave verified
local work available without claiming synchronized delivery. A no-diff task
creates neither an empty commit nor a PR. Attach a published PR to the native
chat when that capability is available.

## Resume publication or manual actions

Resume from an existing checkout, preferably the source outside the task worktree:

```sh
python3 -B /path/to/vibe-setup/workflow.py resume /absolute/source < resume.json
```

For lifecycle events, provide `{"operation_id":"EVENT_UUID","usage":...}` with
a fresh ownership/writer report. Setup-only resume retains its Phase 2 interface. For an already delivered event,
resume performs merge/cleanup reconciliation without requiring old build/review
logs. If PRs remain open it reports cleanup pending. Use the original `sync`
request when publication itself needs verification again.
The helper looks up remote state before repeating mutations. An uncertain create
with no observed PR requires human lookup; it never creates another PR blindly.
An interrupted commit/push/update reuses the existing event and observed outcome.
Do not delete recovery records to bypass a conflict.

Failure output names the actual worktree, branch, base, commit, PR/event identity
and quoted lookup/push commands. Look for an existing PR first; publish the named
commit, update the managed section, use **Ready for review** if needed, confirm
requirements, then apply `[READY]`. For a readiness withdrawal, restore `[BLOCKED]`
before changing implementation. Rerun the same event after the action.

When remote access remains unavailable, `resume` accepts an additional
`confirmation` object with `actor`, current committed `head`, positive `pr_number`
and `actions: ["publication","metadata","non_draft","readiness"]`. The user
must explicitly confirm those actions. The result says `delivery=user_confirmed`;
it never claims those remote facts were independently observed. Confirmation
cannot override observed draft/failing readiness or publish uncommitted work, and
cannot authorize automatic cleanup without independently observed merges.

If an existing READY claim pauses work and remote access remains unavailable,
the user can instead confirm `actions: ["readiness_withdrawal"]`, naming the
known PR and its current published head after manually restoring `[BLOCKED]`.
This narrowly unpauses local work with `delivery=user_confirmed`; publication
remains unverified and cleanup remains unauthorized without observed merges.
An unresolved READY-update intent also pauses work: a lost response may hide a
successful promotion. Do not continue until withdrawal is observed or confirmed.

Lifecycle records live under `<git common directory>/vibe-setup/lifecycle/`,
outside the removable folder. An advisory lock serializes cooperating helpers.
GitHub metadata writes have no compare-and-swap guarantee: the helper rereads
latest text, preserves human content and verifies exact readback, but a concurrent
edit between read and write remains a race. Reconcile observed conflicts manually.
The helper is cooperative automation, not an interceptor for arbitrary tools.

## Inexpensive cleanup after merge

Cleanup defaults ON. Trigger once when synchronization first observes all merges,
including after the user reports a merge; do not poll or start a recurring task.
Use the [lightweight cleanup worker](delegation-brief.md#lightweight-cleanup-worker)
profile: one simpler compatible native model, three minutes and one attempt,
compact result, no project tests/builds or code review. Python performs the checks.
No fixed model name, new billing/provider path or silent expensive fallback.

Run from outside the target worktree, with a fresh report that all writers stopped
and the task exclusively owns it. Explicitly registered branches plus paginated
PR lookup must establish the complete, nonempty inventory. Every associated PR
must be observed merged and owned by this task; missing/inaccessible/ambiguous
history blocks deletion. Historical worktrees without that inventory need manual
reconciliation and are never enrolled through a broad sweep.

The helper preserves dirty, untracked and ignored files, extra commits, active or
unknown writers, shared/pinned/foreign/primary worktrees, and default/protected/
shared/advanced/recreated branches. Native managed worktrees require the host's
lifecycle action; the helper returns a manual step rather than removing them.
Host ownership is reported by the coordinator; Git facts are checked directly.

For eligible Git worktrees it deletes each remote branch with an expected-head
lease, verifies every branch absent, then uses non-force Git worktree removal.
It retains local branch refs. Remote deletion never follows local removal.
Partial progress is durable outside the removed folder. Resume from the source
with the same event ID and fresh usage; a recreated branch is preserved even when
its commit matches the old one. A completed receipt reports historical completion
without starting another worker merely to recheck unchanged state.

`cleanup=pending` is separate from `delivery=merged`. On failure, preserve remaining
resources, name the exact action and stop. Retry after new evidence or the action.
If manual cleanup is needed, verify the full PR inventory and ownership, remove
only eligible remote branches, confirm absence, then remove the clean worktree
through its owning Git/native host. Never substitute recursive or forced removal.
Local/ref checks reduce races but cannot prevent unrelated processes from writing;
stop writers first and retain ambiguous resources.

## Explicit opt-out

The absence of `.codex/vibe-workflow.toml` means enabled. This packaged asset is
the Phase 2 setup default, not native Codex configuration:

```toml
schema_version = 1

[task_lifecycle]
enabled = true
auto_cleanup = true
```

Set `auto_cleanup=false` to keep remote branches and the worktree after merge.
Both the source and task-worktree preference are checked; either opt-out prevents
deletion. Preserve that choice through setup, upgrades and resume.

Preserve an explicit `enabled=false` in the selected source checkout. Startup
then reports `implementation=disabled` and creates no worktree or task state.
That result does not authorize edits that other project rules prohibit. Never
disable the feature to bypass a failure. Invalid/unknown lifecycle fields stop
startup; unrelated policy tables are left untouched. No model, authentication,
permission or global setting is changed by this helper.
