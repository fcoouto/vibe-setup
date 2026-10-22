# Recoverable setup: Phase 2

A coordinator can now preview and apply the reviewed project-local guard recipe
in a verified task worktree, then resume an interrupted application. The helper
uses Python 3.11+ standard library and Git on macOS/Linux. Run it from the complete
reviewed skill package: it reuses the adjacent installer and assets. It is not yet
a standalone project-installed script.

## One prompt, bounded automation

Use this prompt with the reviewed package available to the agent:

> Use Vibe Setup for this project. Preserve my model, provider, reasoning,
> authentication, permissions and customizations. Inspect the project and create
> or verify a task worktree before changes. Preview the setup, apply compatible
> changes, and resume safely if interrupted. Ask only for missing decisions or
> manual actions the tools cannot perform. Report file setup, client validation
> and delivery separately.

The skill still owns complete toolkit onboarding: project decisions, applicable
instructions, tools, validation and review. This helper configures only these
seven recipe paths:

- `.codex/hooks/subagents.py`
- `.codex/delegation-brief.md`
- `.codex/config.toml`
- `.codex/hooks.json`
- `.gitignore`
- `.graphifyignore`
- `.codex/vibe-workflow.toml`

Existing model, reasoning, provider, authentication and permission settings are
preserved. Compatible agent settings and unrelated hook groups survive. Existing
customized managed scripts/contracts and incompatible configuration require
explicit reconciliation before any recipe file is written. Existing lifecycle
opt-out is preserved; absent policy defaults to enabled. Cleanup defaults ON;
`auto_cleanup=false` preserves resources after merge. Phase 3 provides explicit
[publication and cleanup](task-lifecycle.md) operations from the reviewed package.

## Preview, apply, resume

First follow [task startup](task-lifecycle.md) and retain the verified task UUID.
Use the canonical worktree root returned by startup, not the primary checkout.
For clarity, the examples below use `/path/to/vibe-setup` for the reviewed package
and `/absolute/task-worktree` for the verified target. Substitute actual paths.
Save request/result JSON in a private task scratch location, outside tracked files.

```sh
python3 -B /path/to/vibe-setup/workflow.py inspect /absolute/task-worktree \
  --task-id 0652f3d5-16e3-4a59-a1b3-f398149914f3 --client app --client vscode
```

The result's `setup_plan` is a read-only proposal. Review the package recipe and
listed paths with their before/after hashes and file modes. The plan contains no
configuration values. For a local exact-content review, the Python
`plan_install(target)` interface returns proposed bytes in memory; keep any
secret-bearing diff local. Never paste it into a PR, log or chat.

Send `apply` a JSON object with exactly `task_id` and the complete unchanged
`setup_plan` object renamed to `plan`. Do not replace hashes or add approval flags.

```sh
python3 -B /path/to/vibe-setup/workflow.py apply /absolute/task-worktree < setup-request.json
```

Application rechecks the task binding, Git worktree, branch, HEAD, package and
file contents/modes. A stale preview must be regenerated before a new operation.
It writes durable intent under `<git common directory>/vibe-setup/operations/`,
then replaces each changed file atomically. Existing file modes are preserved;
new files use mode `0600` and new directories use `0700`. Other tools must respect
the same worktree and avoid concurrent edits; the advisory lock coordinates only
cooperating helper calls, not arbitrary filesystem writers. Qualification covers
process interruption; it does not establish hardware power-loss durability.

If interrupted, retain all progress and recovery records. Use the operation UUID
from the plan/evidence path and send exactly `{"operation_id":"<that UUID>"}`:

```sh
python3 -B /path/to/vibe-setup/workflow.py resume /absolute/task-worktree < resume-request.json
```

Recovery accepts only recorded before/after states using the same package and
worktree context. It recognizes a completed replacement even if the journal
update was interrupted. A second operation cannot bypass a pending one. Repeating
a completed operation verifies the files without rewriting them. No blanket
snapshot restoration occurs, and custom configuration is never copied into the
journal. Records contain hashes and bookkeeping, not tamper-proof authorization.

## Manual recovery

- **Lock busy:** wait for the other helper to finish, then resume the same operation.
- **Git inspection timed out:** setup returns a sanitized blocked result without
  claiming verification. Check local Git, then retry the same preview/application
  or resume the pending operation; credentials and permissions are unchanged.
- **No intent record after an I/O failure:** no recipe write was authorized by that
  operation; recheck the preview and retry `apply` with the original request.
- **Changed files, modes, branch, HEAD, package or task binding:** stop dependent
  setup, preserve both current work and records, and review the difference locally.
  Return to the reviewed context only when that preserves legitimate work. Do not
  reset the branch, delete a journal, or overwrite a customization to force resume.
- **Unexpected temporary file:** atomic replacement may leave a sibling
  `.vibe-<operation UUID>-<filename>.tmp` after a process crash. A complete matching
  temporary file is reused. A partial or foreign one blocks recovery. Inspect it
  locally; it may contain private configuration. Preserve needed content before a
  human removes only the identified temporary file and retries the same operation.
- **Deliberate change supersedes the plan:** there is no automatic rebase or rollback
  of a pending setup in Phase 2. Reconcile that operation manually before retiring
  its record and making a new preview. Never discard unrelated files or other tasks.

Read `status`, `implementation`, `evidence_ref`, `pending_user_actions` and
`next_action`. Exit `0` means the requested operation succeeded; `2` needs a manual
action/retry; `3` blocks dependent setup because input or state is unsafe. Success
reports `setup_configured`, not complete toolkit adoption or actual client
execution. `delivery=not_checked` never means a PR was created or updated.

## Trust, activation and delivery remain explicit

Project trust comes before hook approval. If the project configuration layer is
untrusted, its hooks may never appear in the approval list. Ask for the precise
project-scoped trust action, verify discovery, then review and approve the exact
hook definitions. Preserve existing authentication and tool permissions; never
write trust hashes or trust a broader parent directory as a workaround. See the
[client qualification procedure](README.md#3-establish-trust-and-actual-execution).

A worktree's ignored local settings do not become active in another checkout by
merging a PR. Inspect and apply activation in the intended checkout through a
separate authorized setup step. The helper does not change installed user skills,
global client settings, credentials or trust. App and VS Code validation remains
separate evidence; these filesystem tests do not qualify either client.

Phase 3 now provides explicit PR synchronization and cleanup. The coordinator
uses the established `[BLOCKED]`/`[READY]` rules and concrete manual delivery steps.
Cleanup must confirm every associated PR merged, delete and verify remote branches
first, then remove the local worktree. Setup itself performs none of those deletions;
cleanup runs only through explicit lifecycle reconciliation.
