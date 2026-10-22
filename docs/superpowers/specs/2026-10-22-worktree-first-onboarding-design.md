# Vibe Setup: worktree-first onboarding and manual recovery

Date: 2026-10-22. Current design. Supersedes the earlier strict-host onboarding and lifecycle designs.

## Decision and scope change

The user accepts that the methodology cannot control every native agent action. The main requirement is doing implementation in a worktree. Automate onboarding and publication as far as the existing environment allows; when automation fails, request concrete manual actions and resume from observed state.

The former requirement for an unbypassable host boundary is removed. Protected host-owned receipts, guaranteed interception of chat/completion, and universally atomic PR metadata updates are no longer release prerequisites. Earlier NO-GO investigations remain valid historical findings; they are not passing tests, but no longer block this revised scope. Previous design/plan versions are preserved in private research records outside the product repository.

Keep one skill and one small Python helper. No MCP server, daemon, custom agent host, credential broker, model routing, permission changes, automatic merge or cleanup. Preserve the current model, reasoning, provider, authentication, permissions, useful customizations and existing work.

## Approach

The skill handles context, decisions, questions, project-specific integration and review. Python handles deterministic worktree checks, bounded file changes, Git/PR observations and recovery. This is the selected approach.

Instructions alone would leave repeated Git/recovery steps less reliable. A mandatory supervisor or MCP gate adds complexity and unsupported requirements. Neither is part of this design.

The first version supports existing GitHub projects on macOS/Linux with Python 3.11+ and Git. Reuse suitable connected GitHub tools when available; otherwise use existing authenticated `gh`. Missing CLI/API access limits publication automation, not verified local work. A connector session does not authenticate a subprocess.

Retain complete Vibe Setup coverage: pinned upstream sources, requirement ledger, component matrix, canonical document mapping, applicable integrations, checks and independent review. The helper supports that process and does not replace semantic review with a success flag.

## One-prompt flow

1. **Inspect without changing the project.** Identify repository/app/harness roots, instructions, staged and dirty files, skill copies, prerequisites, checks, Git identity, remotes and selected clients. Inspect supported settings metadata without exposing credentials. Ask one boundary question for an ambiguous multi-repository workspace; do not enroll siblings silently.
2. **Prepare the smallest complete plan.** Reuse working configuration. Ask only about missing consequential choices, conflicting customizations, or human-only actions. Reuse prior answers and authorization. Establish project trust before asking for hook trust; do not ask users to approve undiscoverable hooks.
3. **Create and verify the worktree.** Prefer native creation, then ordinary Git. Check canonical root, Git common directory, actual worktree registration, branch/base and task binding. Only then edit repository files or dispatch writers there. Set all command/worker directories explicitly; creating a worktree does not move the chat.
4. **Apply recoverably.** Change the verified worktree, preserve unrelated source edits and custom settings, and record exact owned before/after states. Stop on unexplained changes rather than overwrite them.
5. **Validate and deliver.** Run project checks and independent review. Attempt PR synchronization at planned checkpoints/phases. If automation fails, preserve progress, explain the minimum manual action, and report local implementation separately from remote delivery. Exercise actual App/VS Code invocation and recovery without claiming universal interception.

Pure discussion, planning and read-only review need no worktree. If worktree creation fails, guide the user through manual creation/selection, then independently verify it before implementation. Never automatically fall back to the primary checkout, reset/stash unrelated work, or silently adopt another task's branch.

## Git access and user interventions

Treat commit identity, Git transport and PR API identity separately. Preserve existing name/email, SSH/HTTPS transport, account, keys and credential storage. Ask only when missing or conflicting. Read access is not proof of push or PR write access.

Prefer an adequate connected tool; otherwise use authorized CLI authentication. Python's CLI transport uses `gh` only when available. If a connected tool performs publication, pass observed identifiers into subsequent reconciliation; an agent's assertion does not establish remote success. An unsupported App identity check or missing permission becomes a delivery gap, never a reason to switch credentials silently.

When access is missing, request supported sign-in or a manual push/PR action. Never ask for secrets in chat. Do not create tokens, generate/upload keys, switch accounts, alter remotes, install global prerequisites or expand permissions without applicable authorization.

A manual handoff names the verified worktree, branch, remote/base, current commit, failed step, existing PR if known, and minimum next action. Use inspected values and safe quoting for commands. No force flags or assumed default branch. If the outcome is ambiguous, inspect the existing branch/PR before repeating creation. Batch user actions and avoid repeated requests for an unchanged gap.

## Helper and local state

Keep one source helper at `skills/vibe-setup/workflow.py`, installed as `.codex/vibe-workflow.py` in the selected checkout. Reuse the current installer's preflight and customization logic. Python 3.11+ standard library only.

| Operation | Responsibility |
| --- | --- |
| `inspect` | Read-only discovery, prerequisites, configuration comparison and proposed owned changes |
| `start` | Create/reconcile and validate a task-owned linked worktree |
| `apply` | Revalidate task context and plan, then apply journaled owned changes |
| `sync` | Verify local state, attempt publication/update/readback, or return concrete manual actions |
| `resume` | Reconcile files, Git and available remote facts after interruption or human action |

Mutating requests use validated JSON through stdin and explicit subprocess argument arrays. Do not accept arbitrary executable fields or `verified=true`. Validate actual Git facts at entry and before consequential mutations. The skill requires equivalent worktree checks around direct native edits; the helper is not a sandbox for other tools.

Store one small versioned setup/task record beneath the repository's Git common directory in `vibe-setup/`, with an advisory operation lock. Record task/worktree/branch identity, setup write intent, checkpoint IDs, pending events, observed PR/head and evidence references. This is recovery bookkeeping, not a tamper-proof authority. Keep credentials and private machine state out of commits, PR bodies and graph indexes.

Return JSON fields `operation`, `status` (`ok`, `action_required`, `blocked`), `implementation`, `delivery`, `changes`, `pending_user_actions`, `evidence_ref`, and `next_action`. Exit 0 means the requested operation succeeded; 2 requests a user action; 3 stops unsafe/invalid dependent work. A publication failure may return `action_required` while local implementation can continue. An invalid worktree returns `blocked`. Inspection success is not setup completion.

Keep `.codex/vibe-workflow.toml` as Vibe-owned policy, separate from native settings:

```toml
schema_version = 1

[task_lifecycle]
enabled = true
```

Default on when released; preserve explicit user opt-out and reject malformed policy. Never disable the feature automatically to bypass a failure. Opt-out does not delete worktrees, close PRs or change other project rules. No new host attestation system is required to represent the human's choice.

## Checkpoints, PRs and completion

Use one to four routine checkpoints for unphased work, or one synchronization attempt per declared phase. Do not synchronize every implementation step. More than four phases still means one attempt per phase. Coalesce coincident final/readiness events and repeated identical status updates.

Keep each milestone's local acceptance result separate from its remote synchronization event. A local milestone may be complete while publication is pending. Never report an unobserved update as synchronized or claim delivery complete.

Create a draft PR with `[BLOCKED] ` at the first useful checkpoint with publishable work, or earlier for a blocker. Do not manufacture a diff or empty commit to create a PR. The only PR title states remain `[BLOCKED] ` and `[READY] `. Normal work, pending checks, reviews and unresolved issues remain `[BLOCKED]`.

Own only the leading lifecycle prefix and one body section bounded by `<!-- vibe-task-lifecycle:begin task=UUID -->` and `<!-- vibe-task-lifecycle:end -->`. Preserve observed human title suffix and body content. Record summary, progress, validation/commit, remaining work, blockers/resumption and event ID. Malformed/foreign/duplicate markers or edits inside the managed section require reconciliation.

Read current metadata before mutation and verify afterwards. Use conditional updates if supported, but do not require them for release. Preserve known human changes; detected conflicts or uncertain outcomes require manual help. Concurrent edits cannot be guaranteed safe in every API race, and this limit must remain explicit.

Synchronization sequence: confirm task/worktree; ask owned writers to stop and verify their completion; record event intent; stage only task-owned publishable files; commit/push as authorized without force; locate or create the bound PR; update managed metadata; read back identity/head/content/draft state; record observed success. If writers cannot be stopped, do not commit a moving snapshot; request intervention. Locks coordinate cooperating helper calls, not all native processes.

Use one bounded mutation attempt followed by reconciliation. Reuse the event ID. Multiple matches, branch divergence, closed/merged PRs and unknown create outcomes require inspection before another mutation. Attach task PRs through the native artifact tool where available.

## Manual recovery and readiness

| Failure | Behavior |
| --- | --- |
| Missing/foreign/unverifiable worktree | Stop implementation; guide manual repair and verify before continuing |
| Missing commit identity | Ask for the intended identity; never invent one or change global settings silently |
| Push/authentication or PR creation failure | Keep progress locally; guide sign-in, normal push and manual PR creation using actual branch/base |
| PR metadata failure | Supply the precise pending prefix/section change; preserve human content |
| Timeout with unknown outcome | Reconcile or ask the user to inspect before retrying |
| Remote checks/reviews inaccessible | Show local results and identify the remote checks, reviews and mergeability the user must verify |

By default, a remote publication failure leaves delivery pending while safe local implementation can continue in the verified worktree. This is the proposed operational default under the user's manual-fallback direction. An actual code/product blocker stops dependent work; unrelated authorized work may continue.

Try to update the PR before a semantic blocker/readiness report. If automation fails, report promptly with “PR synchronization pending,” the failure and manual action. Do not withhold chat or label all local work blocked solely because GitHub is unavailable.

If checks/review pass locally without an observable PR, report “Implementation ready; publication pending.” Guide push and PR creation as `[BLOCKED]`, followed by remote validation before promotion or merge. This is not a third PR title state.

Draft status and the title prefix serve separate purposes. A PR may leave draft to request review while retaining `[BLOCKED]`. If that transition fails, request the manual “Ready for review” action and confirm the result before promotion.

An existing PR becomes `[READY]` only when non-draft status, current local checks/review and applicable remote checks/reviews/mergeability are established for its head. Where only the user can inspect remote facts, state that responsibility and attribute confirmation to the user. Never claim independent verification of inaccessible facts. Never merge automatically.

Before changing a `[READY]` PR again, withdraw the prior readiness claim and restore `[BLOCKED]`. If automation fails, request manual correction and pause implementation on that PR until correction is observed or user-confirmed. This bounded safety pause prevents actively changing work being presented as merge-ready; ordinary `[BLOCKED]` publication failures do not stop safe local work.

After any manual action, reread accessible Git/PR facts and record observed versus user-confirmed evidence. Resume the same task/event; do not create duplicates. An unavailable read interface does not invalidate the user's confirmation, but remains a stated limit.

## Recovery, acceptance and delivery

Journal owned before/after writes with atomic individual file replacement and an advisory lock. Retry only recognized states. A rollback is a reviewed inverse change to unchanged owned files; never restore an old entire state or overwrite later work. Do not snapshot credentials or unknown secret-bearing configuration into recovery records.

Acceptance requires verified worktree startup/refusal, correct worker directories, safe reruns, preserved customizations, interrupted-operation recovery, honest local/remote status, exact PR tags and useful manual instructions. Exercise ordinary successful and failing paths in actual App and VS Code. Document hook limits instead of requiring universal fail-closed enforcement.

Tracked setup and ignored local activation differ. Report which checkout/client was exercised. A merge does not activate ignored settings in another checkout; reconcile activation when authorized. Update the installed skill only after review and applicable installation authorization.

Design approval changed planning artifacts only. Implementation progress and evidence are recorded in the plan and associated PR; this document does not claim installation or client activation. The [revised plan](../plans/2026-10-22-worktree-first-onboarding.md) can proceed under this scope; the former host-enforcement blocker is retired by the user's requirement change, not a technical breakthrough.

Independent read-only review identified one missing draft-state transition. This revision explicitly requires confirmed non-draft status before `[READY]`, permits `[BLOCKED]` during review, and includes manual recovery and corresponding plan tests.
