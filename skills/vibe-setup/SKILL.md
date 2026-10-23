---
name: vibe-setup
description: Use when a user asks Codex to upgrade the installed Vibe Setup skill or adopt, repair, update, or verify the full Vibe Coding Toolkit setup in an existing project, including its agent workflow. Not for routine task startup, isolated code changes, general machine setup, or scaffolding a new application.
---

# Vibe Setup

Upgrade the installed skill or complete the applicable Vibe setup in the target
project, including validation and independent review. This directory is a
self-contained skill and portable
subagent package with a small standard-library Python helper. Resolve `workflow.py`
relative to this installed skill; do not assume a source checkout or fixed user
path. The component installer still covers only the subagent guard. Use the
[onboarding guide](onboarding.md) and [lifecycle contract](task-lifecycle.md) for
the helper request schemas, recovery and manual actions.

Delegation follows Vibe's [policy and execution contract](delegation-brief.md).
Prefer enabled, approved local models through the installed `local-model-delegation`
plugin when the full task fits assessed capability and safe capacity. Otherwise
retain authorized native execution. Under an explicitly adopted worker-selection
policy, the Coordinator chooses the worker model and reasoning by difficulty, risk
and scoped qualification while keeping its own settings unchanged. Use the
delegation guide's local-first gates, finite recovery and complete-cost accounting;
qualification of model controls is separate from task competence and savings.
Preserve user restrictions; setup does not
implicitly approve models or enable routing. Local proposals bypass native hooks
and require coordinator verification before integration. Read the linked plugin
workflow at the installed version for local execution; do not copy its procedures
into Vibe or apply newer repository instructions to an older installation implicitly.

## Procedure

For an update or reapply, start with the [update transaction](update-contract.md).
For an installed-skill-only upgrade, use the latest official release from
`https://github.com/fcoouto/vibe-setup` unless the user selected another source.
Keep project setup steps out of that operation unless projects were explicitly
selected. After verified completion, offer the [project handoff](update-contract.md#offer-the-next-project-update).
Create one private plan covering the released candidate, the existing installed
copy, explicitly selected/enrolled project roots and requested clients. Identify
source-only roots separately from consumers and umbrellas. Reuse applicable
authorization; state concrete changes before asking for missing scope. Freeze
owned-file baselines and check remote access before dependent publication work.
Use `plan-update`, then the reviewed `apply-update`/`resume-update`; preserve
customization conflicts and independent lifecycle/cleanup opt-outs. Stage the
whole skill outside discovery before replacing owned files. No-change updates
reuse evidence only while its source/client bindings remain current.

Qualify one canary in each requested client before expanding a rollout. Use
[native qualification](qualification.md): verify the trusted project hooks and
role/specialty declaration, run `prepare-probe`, persist `begin-probe`, then pass
its exact `native_arguments` to the native tool once. Reconcile real logs with
`record-probe`. A denial consumes the attempt. Keep dispatch, first-report validity,
settings preservation and recovery separate. Default upgrades validate the native
producer contract; they need no external dashboard, observer or display outcome.
Keep upgrade narration and completion reports about hooks and subagent dispatch.
Only when the user explicitly requests a named external consumer test, load the
[optional consumer guide](native-display.md) and add that separate scoped outcome.
Do not suggest or introduce consumer products during an ordinary upgrade. Record every
required outcome through `record-update`; use `status-update` for the single
completion view. Pending trust, inaccessible remotes, ineffective exclusions and
queued archival remain named dependencies with next actions, never completion.

1. **Discover.** Confirm the destination, active instructions, dirty changes,
   software roots, active harness root, stack, canonical documents, requested
   Codex clients and authorization. If opened in the toolkit distribution,
   obtain the destination. Run `workflow.py inspect` for the selected repository
   and clients; its output is evidence, not completed setup. Preserve current
   model, provider, reasoning, authentication, permissions and customizations.
   Reuse existing Git identity and transport. If multiple actors or destinations
   remain ambiguous, ask only for that choice; never switch credentials or install
   machine prerequisites silently. Missing PR access need not stop safe local work.
2. **Freeze sources.** Read [the complete-run contract](README.md#complete-run-contract).
   Use an explicitly supplied toolkit revision/copy; otherwise resolve latest
   upstream once into a temporary checkout outside the target. Read the complete
   `docs/prompts/12-existing-project-setup.md` Prompt block and its mandatory
   sources at that immutable revision. Follow its applicable steps, using current
   official Codex documentation and actual tool schemas for implementation.
   An offline trusted copy is usable with freshness marked unverified.
3. **Baseline and design.** Run safe existing checks. Use available brainstorming
   proportionately; reuse existing approvals and ask only for consequential
   missing decisions. Build the requirement ledger, full catalog matrix and
   canonical document map described in the complete-run contract. Plan ordered,
   verifiable changes. Existing configuration is evidence to inspect, not proof.
4. **Verify the worktree, then implement.** Read lifecycle preferences first.
   Absent settings mean lifecycle and automatic cleanup ON; preserve each explicit
   opt-out and explain the cleanup default without asking an unnecessary question.
   Unless lifecycle is explicitly disabled, use native worktree creation where
   available, otherwise the helper's Git fallback. Run `workflow.py start` and
   require `implementation=worktree_verified` before edits. Creation alone does
   not move the chat: use returned command/worker directories for every write.
   Failure stops dependent implementation; never silently use the primary checkout.
   With lifecycle enabled, preview setup with `inspect --task-id`, apply the exact
   reviewed plan with `apply`, and use the existing operation ID with `resume` after interruption.
   Preserve conflicting customizations instead of forcing a rerun.
   With `enabled=false`, no task binding exists: skip task-bound setup,
   publication and cleanup operations. Use the reviewed component installer's
   check/install/check flow in the checkout allowed by existing project rules;
   preserve the opt-out and follow ordinary authorized project delivery.
   Execute the approved complete plan: context and agreements,
   applicable tools/skills, native delegation, compatible quality improvements,
   security review procedure, memory, recovery and measured harness improvement.
   Reuse working integrations. Review this package's code/tests and follow
   [installation and trust](README.md#2-review-and-apply-the-subagent-package).
   Reconcile project instructions using [the template](AGENTS.md.template).
   Apply the [delegation policy](delegation-brief.md), including local eligibility,
   role/specialty assignments, demonstrated ability versus runtime capacity,
   model discovery, bounded native fallback and coordinator verification. Mark
   specialties without matching model/task evidence **Not assessed**. Link it
   from the target's existing `AGENTS.md` and documentation entry point; record
   effective routes and qualification evidence privately. Keep each file under
   one writer and preserve permitted model/authentication.
   The main agent is Coordinator. Assign each worker a role from the guide and
   a separate specialty; carry both through local execution and native fallback
   using the installed contract. Roles never select native profiles or change
   model, effort, provider or permissions. Validate the declaration, native child
   identity and hook metadata contract without claiming downstream display.
   Consumer-specific delivery is outside the default upgrade scope.
   Install the template's normal-task lifecycle instructions into the project's
   existing guide, resolving the actual installed helper path. Routine tasks use
   those instructions directly; they must not repeat complete Vibe onboarding.
5. **Validate.** Run project-native checks, applicable live integrations and
   disposable harness cases. Confirm the resolved project configuration layer is
   trusted and loaded before requesting hook approval; untrusted project hooks
   may be absent from the approval list. Follow [client qualification](README.md#3-establish-trust-and-actual-execution).
   Before a native probe, verify its session root and prepare the complete
   [dispatch arguments](delegation-brief.md#prepare-each-dispatch), including the
   required top-level `task_name`. A rejected dispatch consumes a single-attempt
   run; stop and record it rather than retrying and reporting a clean pass.
   Test safe reruns and customizations. Record installation, discovery and
   execution separately. Request necessary trust/restart/authentication actions;
   continue work independent of those blockers. Hooks are guardrails and can
   fail open; they do not enforce this entire skill or sandbox children.
6. **Review independently.** Give a separate read-only reviewer the exact base,
   current diff including untracked deliverables, relevant callers/contracts,
   source revision, ledgers and check evidence. Require findings with severity,
   location and failure scenario. Verify findings, fix confirmed issues and rerun
   affected checks. Unavailable review remains a gap, never a self-review pass.
7. **Deliver.** Reconcile every requirement/catalog row with evidence. Update
   canonical setup/quality documentation and maintenance triggers. Report changes,
   checks, review coverage, limits, pending interventions and next action.
   When lifecycle is enabled, publish under the target's actual authorization and
   readiness policy using `sync`: no more than four planned unphased checkpoints, or one synchronization per phase.
   Stop writers before snapshotting. Create PRs draft with `[BLOCKED]`, preserve
   human content, and verify remote head/metadata before claiming synchronization.
   Blockers stop implementation: update the PR before chat; if that fails, report
   “blocked; PR update pending” with the exact manual action. `[READY]` requires
   checks/review, non-draft status and applicable remote readiness. Withdraw READY
   before further implementation, pausing that PR if withdrawal cannot be observed
   or explicitly confirmed. Distinguish implementation, delivery and cleanup;
   attribute human confirmations and never infer remote facts from local records.
   Missing automation gets concrete manual lookup/push/PR steps and same-event
   recovery, not a new account, duplicate PR or silent completion. Never auto-merge.
8. **Close superseded work and clean up terminal tasks.** Apply `[SUPERSEDED]`
   through the lifecycle contract's `supersede` command with a verified replacement;
   it records intent, preserves human content and closes predecessor PRs. Support
   unpublished predecessors through their explicit publication inventory. Never
   infer supersession from a title alone or discard uncommitted work.
   When reconciliation observes merge, closure or supersession, follow the bounded
   cleanup profile in [delegation](delegation-brief.md). Independent options
   `delete_remote_branches` (merged/closed PRs) and `delete_worktrees`
   (merged/recorded supersession) default ON. Preserve each opt-out and the legacy
   `auto_cleanup=false` master switch. Keep local branch refs and all ownership,
   dirty-file, writer and branch safeguards. When both actions are enabled, verify
   remote absence before local removal; a remote opt-out permits independent local
   removal. For `native_action`, use the exact worktree's native owner and run
   `cleanup` again from the source; queued archival stays pending until filesystem
   and Git registration absence are verified. Persist/report each pending outcome
   and precise next action. No polling, build/review reruns or silent expensive
   fallback; installation alone does not prove actual-client cleanup.

Finish the applicable work; an installer success or a plan alone is insufficient.
Proven external blockers remain explicit. Do not install machine prerequisites,
change provider/billing/permissions, publish or deploy without applicable authority.

## Example

“Use $vibe-setup for this repository with latest upstream. Target Codex
App and VS Code. Preserve my settings and local changes. Use verified worktrees,
automate delivery and cleanup where possible, and guide necessary manual actions.”
