# Task worktrees, publication and cleanup

The self-contained installed skill provides read-only inspection, verified
worktree startup, [recoverable setup](onboarding.md), PR synchronization and
ordered cleanup through `workflow.py`. The onboarding skill coordinates these
operations and adds direct helper instructions for normal project tasks. The existing `install.py`
still installs only the subagent component; it does not install the helper or
policy asset. Run the helper from the complete reviewed package.

Every task follows [mandatory proportional security validation](security-validation.md)
at three gates: implementation-complete/READY/production candidate, release/deployment,
or an explicit user/project requirement. At each gate, classify impact, check
Trail of Bits updates, review applicable updates before adoption, and reuse valid
private evidence. READY and release require complete passing validation, including
`trailofbits-update-review`. Draft edits and worktree creation do not trigger audits.

For a package update across the installed skill and selected consumers, use the
[update transaction contract](update-contract.md). It adds private scope, recovery
and completion records around these existing lifecycle operations. It does not
replace verified worktree bindings, project publication authority, native trust
controls or cleanup ownership. Native client probes use the separate
[single-attempt qualification contract](qualification.md).

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

`start` never runs cleanup, contacts publication services, or processes other
retirement handoffs. It only revokes retirement for a task whose checkout is being
reused, before allowing writers to resume. Pending deletion is processed on
confirmed merge or recorded supersession, through the closure flow below.

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

Use one to four routine checkpoints, or one routine checkpoint per declared phase.
Keep stable milestone IDs and one event UUID per synchronization, including retries.
Only `checkpoint` events consume that budget. `ready`, `reopen` and `blocker`
are acceptance or recovery transitions within an existing milestone. After a
checkpoint or reopened work, use a fresh `ready` event with current source and
evidence; no unused milestone is required. Reuse the original event for retries
with unchanged inputs, and preserve prior requests and the frozen schedule.
Every READY transition still requires all local, security and remote gates.
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
| `validation` | `snapshot` matching the event, `checks` list, one independent `review` entry, and `security` assessment required for READY |

Each validation entry contains exactly `name`, `outcome` (`passed`, `failed` or
`not_run`), `path` (private evidence file), and its SHA-256 `sha256`. A `ready`
event requires at least one check and an independent review, all passed. Keep
request/evidence files outside tracked source; requests are limited to 64 KiB.
It also requires the [security evidence contract](security-validation.md#evidence-and-readiness):
matching snapshot, risk/rationale, complete coverage, declared required checks
and passing evidence for each. Old READY requests without this record block.
Checkpoint/blocker/reopen may retain missing or stale security evidence so
progress reporting and withdrawal remain possible; they never assert a pass.
The task's schedule and publication identity remain fixed after first use;
changed branches or destinations require explicit reconciliation of the inventory.

The helper commits only the named files, pushes normally without force, verifies
the remote commit and looks up every matching PR before creation. New PRs start
draft with `[BLOCKED]`. One marked body section contains summary, progress,
validation, remaining work and blockers. Human title suffixes and text outside
that section survive updates. Edited, missing, malformed or foreign managed
sections require reconciliation.

A PR may leave draft while still `[BLOCKED]` to receive reviews. `[READY]` requires
current local and security evidence, confirmed non-draft status and observed passing checks,
reviews and mergeability for the exact head. Unknown remote facts remain pending.
Before further edits to a ready PR, send `reopen` and verify `[BLOCKED]`; failure
pauses that PR's implementation. Other publication failures can leave verified
local work available without claiming synchronized delivery. A no-diff task
creates neither an empty commit nor a PR. Attach a published PR to the native
chat when that capability is available.

## Cross-repository completion

Before claiming overall completion for work with required companion PRs, run
`check-completion` with every required existing Vibe task. Keep this explicit
manifest in the existing private task plan or evidence directory; no group registry
or new lifecycle records are created. The root argument supplies command context;
it does not implicitly add that repository or discover siblings.

```sh
python3 -B /path/to/vibe-setup/workflow.py check-completion /absolute/source < companions.json
```

```json
{
  "members": [
    {"source": "/absolute/backend", "task_id": "0652f3d5-16e3-4a59-a1b3-f398149914f3"},
    {"source": "/absolute/documentation", "task_id": "d7bd47d4-dcbf-4cbe-bcbf-cab1f3f5db34"}
  ]
}
```

Supply 1–32 unique members using canonical repository roots and task UUIDs.
Each member reuses its verified task binding and publication record. Fresh GitHub
reads use the existing host, transport and actor checks. The command validates
recorded PR identities, heads, target branches and task markers; existing task
worktrees must still match the published head and have no unpublished changes.
Removed worktrees remain inspectable through the source repository's retained
records. Any retained task branch must still match the published head. A moved or
missing-but-registered worktree blocks completion until its binding is reconciled.
Changing records during inspection blocks the observation.

The output contains per-member `completion` and `reason`, plus overall
`completion`: `complete` only when every listed task's associated PRs are observed
merged; `pending` for unpublished tasks or open PRs; `blocked` for closed-unmerged
PRs, missing/inconsistent state or unavailable remote facts. Blocked takes
precedence over pending. Exit codes are 0, 2 and 3 respectively. A task with no
publication does not count as complete, including no-diff tasks; include only
companions that require PR delivery. Invalid manifests are rejected before remote
reads. Reconcile missing records or publication changes through existing per-task
operations, then rerun with the same complete member list.

This is a read-only observation, not an atomic cross-repository transaction or
continuous monitor. The coordinator owns manifest completeness and must rerun
before a later completion claim. It does not publish, merge, update PR metadata,
schedule work, change per-repository READY gates or trigger cleanup. Per-task
startup, synchronization, recovery, supersession and cleanup remain unchanged.
A closed or superseded PR is not a merged deliverable; explicitly reconcile the
required task list if accepted scope changes. Installation alone does not ensure
that every client invokes this check.

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
It cannot override missing, stale, incomplete or failing security evidence.

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

## Supersede a predecessor

Use `supersede` from the source checkout, outside the predecessor worktree. The
command records a replacement, replaces `[READY]`/`[BLOCKED]` with `[SUPERSEDED]`,
and closes every owned predecessor PR. It preserves human title text and body
content outside the managed section. The replacement remains untouched.

```sh
python3 -B /path/to/vibe-setup/workflow.py supersede /absolute/source < supersede.json
```

```json
{
  "task_id": "PREDECESSOR_TASK_UUID",
  "successor": "https://github.com/OWNER/REPOSITORY/pull/123",
  "usage": {"kind": "managed", "scope": "exclusive", "writers": []}
}
```

`successor` is either a same-repository active/merged PR URL or the UUID of a
separate verified task with an existing worktree in the same repository. A task
cannot replace itself; an already superseded or closed-unmerged replacement is
rejected. Supersede each predecessor task separately: ownership bindings remain
immutable, and this command never enrolls arbitrary historical branches.

For a verified task that has never published through this helper, also provide
`publication` with the same fields as `sync`, naming exactly its owned branch.
The helper verifies that no PR exists before recording an unpublished
supersession. It does not create an empty PR. A remote branch without a closed PR
is retained; the superseded worktree is eligible for removal. The local branch
must still retain its exact recorded head, including unpublished commits.

The intent is saved before changing GitHub. Retry the same request after an
interruption; the replacement cannot silently change. `cleanup` also resumes an
existing intent. A completed supersession that was subsequently reopened or
edited requires reconciliation; the helper never closes it again automatically.
An externally edited title alone is not a recorded supersession and does not
permit worktree removal. Missing replacement or ownership evidence stays pending.

## Inexpensive terminal-task cleanup

Both cleanup options default ON. On confirming all associated PRs merged or a recorded supersession,
run reconciliation once, including after a user reports that transition. Do not
poll or create a recurring task. `sync` and `resume` reconcile terminal PRs;
`cleanup` needs only the task identity and fresh usage, without old build/review
logs or a delivered publication event:

```sh
python3 -B /path/to/vibe-setup/workflow.py cleanup /absolute/source < cleanup.json
```

```json
{
  "task_id": "TASK_UUID",
  "usage": {"kind": "git", "scope": "exclusive", "writers": []}
}
```

| Observed task state | Remote branches | Worktree |
| --- | --- | --- |
| Every associated PR merged | Delete eligible branches | Remove |
| All PRs closed, with some unmerged and no recorded supersession | Preserve | Preserve |
| Recorded supersession, predecessor PRs closed | Delete eligible branches | Remove |
| Recorded unpublished supersession | Retain any remote branch | Remove |
| Any associated PR open, missing or ambiguously owned | Preserve | Preserve |

Each column obeys its own opt-out. Local branch refs are always retained as the
recovery copy, including closed-unmerged and unpublished work. Worktree removal
requires an exact retained head and a clean worktree, including ignored files.
Extra commits, running/unknown writers, shared/pinned/foreign/primary worktrees,
locks and unknown ownership block cleanup. Default, protected, shared, advanced
or recreated remote branches are preserved. Remote protection does not prevent
local removal when remote deletion is explicitly disabled.

Use the [bounded cleanup profile](delegation-brief.md#lightweight-cleanup-worker).
Python verifies facts. Supply fresh ownership/writer information and stop writers.
If both actions are enabled, delete remote branches with expected-head leases and
verify absence before removing the worktree. If remote deletion is opted out,
worktree removal may proceed independently. Never substitute forced or recursive
removal. Historical resources without usable task/PR records require scoped
manual reconciliation; no broad sweep is authorized.

For a native managed worktree, Python performs eligible remote cleanup and
returns `native_action` naming `archive_worktree`, the exact worktree, task and
head, plus a `preflight` document/section reference. The coordinator follows the
[native archive preflight](#native-archive-preflight) in that worktree's owning chat,
uses the native archive tool, then invokes `cleanup` again from the source with
fresh usage. A queued archive remains `cleanup=pending`; only absent filesystem
path AND absent Git registration confirm removal. The helper never invokes a
native client tool or removes a managed checkout through Git. Dirty, primary,
pinned or shared resources must not be archived to bypass a helper rejection.

Pending reasons, native-removal intent and per-resource outcomes are durable in
the Git common directory. Resume on new evidence or after the named action, not
by repeating expensive checks or workers. `cleanup=complete` means the currently
eligible, enabled actions finished; inspect `cleanup_checks` for retained resources.
A closed-unmerged task without recorded supersession cannot trigger cleanup.
A receipt with both resources removed remains historical evidence.
Unexpected external disappearance without recorded removal intent stays pending.
Recreated branches and changed inventories are never silently deleted again.

### Native archive preflight

Completed native subagents can retain inherited worktree attachments. The client
may count those children as other owners, return `queued`, then restore the active
attachment without removing the checkout. A completed report does not release an
attachment. Resolve these owners before requesting archival; repeating the same
request without changed evidence does not resolve retention.

This is a coordinator procedure through supported native tools. Python cannot
observe native child status or attachment ownership, and `native_action` is a
handoff, not permission to skip these checks. Keep the native child IDs and their
task/worktree bindings in the existing private task evidence when dispatching;
do not create a separate registry or infer ownership from names or matching cwd.

1. Confirm the helper's exact task, worktree and retained head, the owning chat's
   attachment, and current cleanup authority. Use dispatch records and fresh native
   agent/thread and attachment observations to identify only this task's children
   that inherited this worktree. Check descendant activity and other ownership
   before changing a child's archive state. Missing or conflicting identity,
   attachment, pinning or ownership evidence leaves cleanup pending.
2. A child is eligible only when its assigned work is complete, its final result
   is collected, and fresh native status confirms no active turn or descendants.
   Idle, waiting, interrupted, failed and unknown states alone do not establish
   completion. Preserve running children, unfinished work, pinned/shared chats,
   unrelated tasks and children needed by another active task. Never stop, cancel,
   interrupt or change settings to make a child eligible. If any owner is unsafe
   or unresolved, leave all child archive states unchanged and report the blocker.
3. With the full inventory eligible, recheck each child immediately before using
   `set_thread_archived` with its exact `threadId` and `archived=true`. Archive only
   those completed task children, preserving their histories; leave the owning
   chat open. Already archived children need no mutation. If status changes or a
   tool fails, stop dependent archival, preserve completed actions and reconcile
   the remaining owners. Native observations are not an atomic lock; do not resume
   or reassign these retired children during cleanup.
4. Refresh ownership/status evidence and rerun `cleanup` from the source with
   fresh usage. Only a renewed `native_action` permits one `archive_worktree` call
   for that exact attachment. If the path survives, inspect the archive outcome
   and attachment owners; keep the result pending rather than looping or claiming
   success. Run `cleanup` after removal to verify both filesystem and Git absence.

If the client cannot expose sufficient ownership/status evidence or archive a
completed child, retain the checkout and name the missing native action. Do not
edit client databases, use private IPC, detach arbitrary attachments, archive the
parent chat, or substitute Git/forced removal. This procedure does not expand a
new task's authority over another chat's managed worktree. Unit tests cover the
helper handoff; instruction scenarios and actual-client archival are separate
evidence, not guarantees for every client/version.

### Queued cleanup on task closure

After terminal-state, ownership, stopped-writer, clean-tree, head and policy checks
pass, cleanup records `cleanup.deferred = {"kind": "git"|"managed", "state": "ready"}`
before attempting the enabled removals. This existing retirement handoff is the
`ready-to-be-deleted` marker. It relinquishes exclusive use until explicitly reused;
it is not a cached claim that writers are currently idle. Do not restart writers
in a retired checkout without running `start` again. Starting that task, using its
worktree as the new task's source, or synchronizing it cancels the handoff before
further work. A new explicit cleanup with fresh ownership and stopped writers can
renew it. Running/unknown writers or shared/pinned scope cancel it. Revocation
also applies to completed cleanup that retained a worktree under an opt-out.
Failure to cancel retirement durably blocks reuse before authorizing writers.

`cleanup`, terminal `sync`, delivered-event `resume`, and `supersede` use the same
closure path. After fresh confirmation of all associated PRs merged or completed
recorded supersession, that path visits all other pending records in the same Git
common directory once. Outcomes appear under `pending_cleanup.tasks`, separately
from the triggering task's own cleanup result. A complete triggering task does not
mean the whole queue is complete. A stale completion receipt, ordinary PR closure,
`[SUPERSEDED]` title alone, startup, resume without confirmed closure, and compaction
do not authorize a queue pass. User reports prompt remote reconciliation rather
than substituting for it. No hook, timer, polling or extra model run is added.

The lifecycle lock serializes cooperating calls without waiting in a loop. Each
eligible ready handoff rechecks current opt-outs, terminal PR ownership, retained
heads, remote absence, clean files and locks. The triggering task, its source and
the current working directory are excluded. There is no one-worktree limit or
fixed candidate cap. A malformed record or blocked candidate leaves a concrete
pending outcome without stopping other candidates. Blocked resources remain for
a later confirmed closure or a scoped retry after the named action/new evidence.
Neither the queue nor its marker grants authority over another Git repository.

The pass reads no old build/review logs and runs no security review. Unmarked
historical records cannot authorize Git removal: run `cleanup` with fresh usage
to establish a handoff. Legacy native `archive_requested` records can be reconciled
only after the owner has removed both the directory and Git registration.

Managed ownership survives later callers and cannot be relabeled as Git. Another
chat cannot archive the owning chat's App-managed worktree through the current
archive interface. Existing managed folders remain pending for their native owner,
which must follow the [native archive preflight](#native-archive-preflight).
There is no private IPC or Git-removal fallback. A later closure can verify a
completed native archive. Installation and helper tests do not prove native event
delivery. If no later closure occurs, pending cleanup does not run by itself.

Local/ref checks reduce races but cannot prevent unrelated processes from writing.
GitHub metadata has no compare-and-swap guarantee. Preserve ambiguous outcomes,
keep the next action concrete, and separate delivery from cleanup in reports.

## Explicit opt-out

The absence of `.codex/vibe-workflow.toml` means enabled. This packaged asset is
the Phase 2 setup default, not native Codex configuration:

```toml
schema_version = 1

[task_lifecycle]
enabled = true
auto_cleanup = true
delete_remote_branches = true
delete_worktrees = true
```

`delete_remote_branches=false` retains remote branches after confirmed merge or recorded supersession.
`delete_worktrees=false` retains worktrees after merge or recorded supersession.
These options are independent. Missing options mean true; values must be booleans.

Existing `auto_cleanup=false` remains a master opt-out for both actions, even if
individual options are true. `enabled=false` disables the entire lifecycle,
including supersession. Superseding still closes predecessor PRs when only
cleanup is disabled. Both source and task-worktree policies are checked: either
opt-out wins for that resource. The worktree policy is saved before removal so
its opt-outs survive absence. Preserve choices through setup, upgrades and resume.

Preserve an explicit `enabled=false` in the selected source checkout. Startup
then reports `implementation=disabled` and creates no worktree or task state.
That result does not authorize edits that other project rules prohibit. Never
disable the feature to bypass a failure. Invalid/unknown lifecycle fields stop
startup; unrelated policy tables are left untouched. No model, authentication,
permission or global setting is changed by this helper.

With lifecycle disabled, do not call task-bound setup, synchronization or cleanup:
there is no verified task record. Independent onboarding/upgrades use the existing
component installer's check/install/check flow in the checkout permitted by project
rules, preserving the opt-out. Ordinary authorized project delivery remains
available outside this lifecycle helper.

Security validation remains mandatory with either opt-out. Before release, run
the read-only [release preflight](security-validation.md#release-preflight-including-lifecycle-opt-out)
using `inspect ROOT --file ...` and `check-security ROOT`, without a task ID.
Require exit 0 for the exact release revision in addition to project release
checks; this helper does not intercept separate deployment tools.
