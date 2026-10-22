---
name: vibe-setup
description: Use when a user asks Codex to adopt, repair, update, or verify the full Vibe Coding Toolkit setup in an existing project, including its agent workflow. Not for routine task startup, isolated code changes, general machine setup, or scaffolding a new application.
---

# Vibe Setup

Complete the applicable Vibe setup in the target project, including validation
and independent review. This directory is a self-contained skill and portable
subagent package with a small standard-library Python helper. Resolve `workflow.py`
relative to this installed skill; do not assume a source checkout or fixed user
path. The component installer still covers only the subagent guard. Use the
[onboarding guide](onboarding.md) and [lifecycle contract](task-lifecycle.md) for
the helper request schemas, recovery and manual actions.

Delegation follows Vibe's [policy and execution contract](delegation-brief.md).
Prefer enabled, approved local models through the installed `local-model-delegation`
plugin when the full task fits assessed capability and safe capacity. Otherwise
retain authorized native execution. Preserve user restrictions; setup does not
implicitly approve models or enable routing. Local proposals bypass native hooks
and require coordinator verification before integration. Read the linked plugin
workflow at the installed version for local execution; do not copy its procedures
into Vibe or apply newer repository instructions to an older installation implicitly.

## Procedure

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
   model, effort, provider or permissions. Dashboard delivery requires separate
   evidence; follow the guide's compatibility limits without modifying Habblaud.
   Install the template's normal-task lifecycle instructions into the project's
   existing guide, resolving the actual installed helper path. Routine tasks use
   those instructions directly; they must not repeat complete Vibe onboarding.
5. **Validate.** Run project-native checks, applicable live integrations and
   disposable harness cases. Confirm the resolved project configuration layer is
   trusted and loaded before requesting hook approval; untrusted project hooks
   may be absent from the approval list. Follow [client qualification](README.md#3-establish-trust-and-actual-execution).
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
8. **Clean up cheaply after merge.** When reconciliation first observes merges,
   follow the bounded lightweight worker profile in [delegation](delegation-brief.md).
   Unless opted out, Python must confirm all associated PRs merged and resources
   safe, delete and verify remote branches first, then remove the exact worktree
   without force. Keep local branch refs. Use fresh ownership/writer information
   and resume from outside the target. No polling, build/review reruns, fixed model
   name or silent expensive fallback; pending cleanup gets one precise action.

Finish the applicable work; an installer success or a plan alone is insufficient.
Proven external blockers remain explicit. Do not install machine prerequisites,
change provider/billing/permissions, publish or deploy without applicable authority.

## Example

“Use $vibe-setup for this repository with latest upstream. Target Codex
App and VS Code. Preserve my settings and local changes. Use verified worktrees,
automate delivery and cleanup where possible, and guide necessary manual actions.”
