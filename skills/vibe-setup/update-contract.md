# Scoped update transaction

The update helper joins a released package, the installed shared skill, explicitly
selected project copies, and actual client evidence. It does not discover or enroll
other repositories, start native workers, approve hooks, change client settings,
publish, merge, archive worktrees, or route models. Those actions retain their
existing native tools, lifecycle checks, and authorization requirements.

All commands use `workflow.py OPERATION /absolute/package/source/repository` and
receive one JSON request on standard input. The source repository is distinct from
the selected consumer roots and the active native harness root. Requests and
receipts reject unknown fields. Paths must be absolute, canonical and free of
symlinks. Files must be regular. Python 3.11+, Git and POSIX locking are required.

## Plan an update

`plan-update` accepts:

```json
{
  "operation_id": "11111111-1111-4111-8111-111111111111",
  "record_dir": "/private/update-records/11111111-1111-4111-8111-111111111111",
  "candidate_dir": "/source/skills/vibe-setup",
  "revision": "0000000000000000000000000000000000000000",
  "installed": {"root": "/installed/vibe-setup", "baseline": {}},
  "targets": [
    {
      "root": "/projects/example",
      "kind": "project",
      "baseline": {},
      "clients": {
        "app": {
          "runtime": "observed client version",
          "session": "observed native thread ID",
          "hook_source": "/projects/example/.codex/hooks.json",
          "settings_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
        }
      },
      "task": null,
      "activation_revision": null,
      "exclusions": []
    }
  ],
  "authorizations": [
    {"action": "install", "roots": ["/installed/vibe-setup"], "provenance": "Exact user instruction or reference", "constraints": []},
    {"action": "adopt", "roots": ["/projects/example"], "provenance": "Exact user instruction or reference", "constraints": []}
  ],
  "requirements": [
    {"root": "/projects/example", "layer": "execution", "client": "app"},
    {"root": "/projects/example", "layer": "protocol", "client": "app"}
  ]
}
```

Replace illustrative paths, identifiers and hashes with observed values. `baseline`
maps previously owned relative paths to `{ "sha256": "…", "mode": 420 }` or
`null` for an absent file. Use hashes retained from the prior reviewed installation;
do not turn current customized bytes into an alleged prior baseline. An empty map
claims no prior ownership. An existing differing file then conflicts. The helper
never replaces an unrelated installed file merely because it is absent from the
new package.

`installed` may be `null` for a selected-project-only update. Its root must already
exist and must be separate from the package source and every selected target.
Neither installed-skill/target ancestor direction is allowed, including source-only
targets. Explicit umbrella and software-child relationships among targets remain
valid. The full committed candidate
is staged privately, including tests and executable dependencies. Only Python
caches, pytest caches and `.DS_Store` are excluded. An uncommitted, missing,
symlinked or incomplete candidate is rejected. The exact revision must be current
source HEAD. Commit the reviewed candidate before planning; later apply uses the
frozen private stage.

The record directory must end with its operation UUID and stay outside the source,
installed discovery directory and every selected target. It contains `plan.json`,
`state.json`, the complete `stage/`, owned destination `payloads/`, and durable
`backup/` files. Files containing existing local configuration remain private;
JSON reports contain hashes, not configuration values or credentials.

Target kinds are `project` (exact Git root), `umbrella` (explicit non-Git
coordination root), and `source` (package-only role with no consumer writes).
Source repositories may also be deliberate consumers through a `project` target.
No children are inferred. Installed-skill and project ownership are separate.
Project baseline paths are limited to the existing component installer's owned
files. The default installer still refuses collisions; incremental planning runs
it against a private preview with only reviewed package assets substituted.
Known single-command subagent groups can update when the entire current hook file
matches its reviewed baseline. Unrelated groups remain intact. A customized hook
file requiring a definition migration stays a scoped conflict for explicit review.
Unrelated hooks, ignore rules, custom configuration and independent lifecycle and
cleanup opt-outs are preserved.

Lifecycle-enabled Git changes require `task: {"task_id":"…","worktree":"…"}`
bound by the existing `start` helper. The target must be that verified worktree.
For primary local activation after publication, `activation_revision` must equal
the reviewed current HEAD, and no tracked setup file may change or differ from
that commit. This allows ignored local configuration to activate the already
published version. Lifecycle-disabled projects retain their explicit opt-out.
Umbrellas have neither a task binding nor an activation revision.
An umbrella must be outside every Git repository. Git ownership is checked during
planning and again before writes, so a Git primary or nested repository directory
cannot bypass lifecycle checks by selecting a different kind. Existing Git
metadata, including broken worktree pointers, and unexpected or missing Git
diagnostics block classification rather than proving the root is non-Git.

Client inventory accepts only `app` and `vscode`. Each context binds runtime,
native session, exact hook-source spelling, and the SHA-256 of the canonical JSON
settings object (`sort_keys=True`, separators `(',', ':')`) observed by native
qualification. Do not copy settings from another client. The helper stores only
the settings fingerprint, never authentication material. A CLI run cannot supply
either client identity.

Authorization records preserve action, exact selected roots, provenance and
constraints across interruption. Actions are `install`, `adopt`, `publish`,
`release`, `cleanup`, and `qualify`. They are audit records, not a permission engine
or native trust grant. The coordinator must obey the original constraints and
request only genuinely missing scope. Apply requires recorded `install`/`adopt`
authority for the corresponding destination. It can continue independent roots
while another root has a preservation, authority or remote-access blocker.

## Apply, recover and roll back

`apply-update`, `resume-update`, and `rollback-update` accept only:

```json
{"record_dir": "/private/update-records/11111111-1111-4111-8111-111111111111"}
```

Apply validates all selected owned paths before replacement, locks the operation
and destination directories, saves original owned bytes durably, then uses the
existing durable replacement helper. Interrupted operations resume from before
and after hashes, with a durable per-file write intent and the original backup.
Apply, resume and rollback still require every selected root and the source
candidate directory to exist. A missing root blocks the operation before other
destinations change; these commands never recreate an archived worktree.
Rollback never claims an identical file created by another writer before that intent.
A changed destination,
stage, task binding, policy or target HEAD stops affected work for reconciliation.

Rollback visits owned changes in reverse order. It restores only files still
matching the operation's after hash, removes only unchanged files created by this
operation, and preserves unrelated files. Later user edits block rollback. Retain
the record and backups until the final outcome is verified. Trust decisions and
native settings are not files owned by this transaction and are never restored
from these backups. A rolled-back operation cannot be applied again; create a new
reviewed operation identity.

Repeating the exact plan request returns the existing operation. A completed
no-change apply makes no destination or receipt writes. Optional `reuse_from`
names a prior private record directory: evidence is reused only when the new
source, files, root, client and context fingerprint still match. Reuse never
launches a probe or creates a publication request.

## Record outcomes and determine completion

Supported outcome layers are `tests`, `review`, `installation`, `activation`, `discovery`,
`execution`, `protocol`, `display`, `publication`, `remote_access`, `cleanup`,
`exclusions`, and `release`. Client layers are discovery, execution, protocol,
display and exclusions; all other layers use `client: null`.

Standard client qualification requires discovery, execution and protocol evidence
for hooks and native subagent dispatch. Add `display` only for an explicitly
requested consumer test; its absence is not a missing upgrade requirement. Do not
introduce consumer product names or display prompts into routine upgrade reports.
Frozen plans retain any previously explicit display requirement.

Installation is automatically required for selected writable destinations.
Project activation is recorded separately. A publication requirement adds an
early remote-access prerequisite. Requested exclusions add one effective-discovery
requirement per selected client. Configuring an exclusion does not prove it took
effect. Publication, release and cleanup remain externally executed outcomes.

`record-update` accepts the record directory and an immutable evidence reference:

```json
{
  "record_dir": "/private/update-records/11111111-1111-4111-8111-111111111111",
  "evidence": {"path": "/private/evidence/app-execution.json", "sha256": "…"}
}
```

The referenced JSON envelope contains exactly:

```json
{
  "schema_version": 1,
  "root": "/projects/example",
  "layer": "execution",
  "client": "app",
  "fingerprint": "copy the matching outcome fingerprint from plan/status",
  "state": "passed",
  "reason": "Actual bounded worker execution verified",
  "next_action": "No action required",
  "source": {
    "client": "app", "runtime": "observed client version",
    "session": "observed native thread ID",
    "hook_source": "/projects/example/.codex/hooks.json",
    "settings_sha256": "…"
  },
  "outcome": "native_probe",
  "references": [{"path": "/private/evidence/native-probe.json", "sha256": "…"}]
}
```

For non-client evidence, `source` must be `null`. Allowed states are `pending`,
`passed`, `blocked`, `stale`, and `inapplicable`; every state requires a reason and
next action. Evidence must bind the exact required row fingerprint. Each referenced
artifact is checked against its immutable hash. Installation/activation cannot be
closed by external assertions; the helper verifies current owned destination hashes.

Passed execution, protocol and display evidence references a native qualification
receipt, whose one-attempt result, client, root, runtime, session, source and settings
must agree. They remain separate outcomes. A corrected report cannot establish
first-pass protocol. Required display evidence must identify the actual child and
an observer armed before dispatch. The native module evaluates those details.
Ingestion, status checks and evidence reuse call the native module's read-only
`status-probe` boundary. It revalidates the full receipt, declaration, protected
inputs, native context and captured artifact hashes. Missing inputs or altered
child logs, dispatch captures or display snapshots invalidate the outcome even
when the envelope and receipt files are unchanged. Append-only native log events
remain valid when the captured prefix is unchanged. This never dispatches a retry.

Cleanup passes only for observed `outcome: "archived"`; `archive_requested` remains
pending. Exclusions pass only for `effective`; `configured` remains pending and
`compatibility_gap` remains blocked. Remote access passes only for `accessible`;
`inaccessible` remains blocked. These are external observations: the helper does
not change accounts, remotes, credentials, exclusions or native ownership.

Retained `record-update` and `status-update` remain usable through the installed
helper after source or target archival removes the original directories. Continue
passing the frozen source path and external record directory. All canonical-path,
scope, schema and hash checks remain; only live-directory existence is relaxed.
Outcome ingestion locks its private operation record without reopening missing
source or target directories. These commands never recreate those directories.

The response's `roots` map distinguishes `present`, `unavailable` and `archived`.
Disappearance alone, or a queued archive request, leaves a root unavailable and
prevents completion. An observed archived cleanup receipt allows a source-only
root to close while installed and client outcomes continue validating their live
inputs. Removed writable targets have stale installation, activation and client
rows, with retained transaction/evidence references explicitly labeled historical.
Missing native inputs never become a current client success.

One narrow exception preserves completed temporary task work. Installation and
activation can pass with `basis: "historical"` and `deployment: "inactive"` when
the removed project has its frozen verified task binding, a successful applied
transaction with every changed owned file recorded done, explicit cleanup
authority, and a validated observed archive receipt. This does not claim a live
deployment, change stale client rows, or apply to unbound/primary roots, queued
archives, incomplete writes or rolled-back transactions.
Explicit task bindings are verified and retained for no-change plans too. A
successful no-change apply verifies the frozen destination hashes and can retain
historical completion after observed archival under the same gates.

`status-update` accepts the record directory and optional `contexts`, mapping
selected root paths to current App/VS Code context objects. Different current
contexts mark affected evidence stale. Mutated evidence or changed client inputs
also become stale. Status is read-only; it never retries native work.

The response always shows every required outcome, preservation conflicts, changes,
transaction state and `complete`. Completion requires every required outcome to
be passed or explicitly inapplicable, with no preservation conflicts. A blocked
root is useful partial progress, not completion. Include cleanup in requirements
when its completion is part of the task; otherwise report cleanup separately.
Incomplete updates return `status: "action_required"` (CLI exit 2); complete ones
return `status: "ok"` (exit 0). Invalid requests fail with the existing blocked
status. Required source tests and review gate every destination write; equivalent
target requirements gate that target. Record real check evidence before apply.

## Offer the next project update

After `status-update` confirms `complete: true` for an installed-skill upgrade,
report the verified release and checks, then ask once: **Would you like to update
Vibe Setup in a project next?** Include the handoff immediately so the user can
continue without another round trip. A verified no-change upgrade uses the same
handoff. Skip the offer if the user already declined project updates or the
requested project rollout is already complete.

1. Create a new chat inside the project you want to update. Use its actual name
   and root when known from the user's context; otherwise keep this instruction
   generic until the user chooses. Do not scan for or enroll projects to fill it in.
2. Paste this prompt:

   ```text
   Use $vibe-setup to update this project's setup with the installed skill, preserving my settings and customizations. Validate the result and report anything pending.
   ```

The new chat verifies its project root and installed skill before applying the
project-specific workflow. The handoff does not authorize a new shared-skill
upgrade, thread creation, messaging another chat, or project writes in the current
chat. Follow an explicit request to continue in the current chat when its project
root and scope are verified instead of insisting on a new chat.

When required outcomes remain blocked or pending, report partial progress and
the concrete recovery step. Do not present the success handoff as completion or
let an optional project choice block completion of an otherwise finished skill
upgrade. Keep installation, discovery and actual execution evidence distinct.
