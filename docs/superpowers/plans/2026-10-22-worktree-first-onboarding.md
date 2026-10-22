# Vibe Setup Worktree-First Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution, or superpowers:subagent-driven-development if the user chooses delegation. Track steps with checkboxes. This document records the revised scope; Phase 1 is merged; Phase 2 local implementation, validation and independent review are complete. Phases 3–4 remain unimplemented; remote delivery is tracked in each phase PR.

**Goal:** Deliver one-prompt onboarding with verified worktrees, a small Python helper, best-effort PR automation, default-on post-merge cleanup with opt-out, and concrete manual recovery.

**Architecture:** The skill coordinates project decisions and supported tools. A standard-library helper verifies Git facts, applies bounded recoverable changes, and manages publication attempts and pending user actions. Native clients retain their current model/authentication/permissions; there is no mandatory host-control layer.

**Tech Stack:** Python 3.11+ standard library, Git, existing connected GitHub tools or authenticated `gh`, `unittest`, macOS/Linux, Codex App and VS Code.

**Spec:** [Current practical design](../specs/2026-10-22-worktree-first-onboarding-design.md). This plan replaces both earlier implementation sequences and their strict-host entry condition.

## Status and global constraints

The user's 2026-10-22 direction removes universal host enforcement as a release gate. Historical Phase 1 NO-GO results remain factual but do not block these new phases. No previous strict test is marked passed. Phase 1 has 55 passing tests, completed independent review and was merged through [PR #2](https://github.com/fcoouto/vibe-setup/pull/2). Phase 2 adds recoverable recipe setup with 76 passing tests and completed independent review; remote delivery is recorded in its associated PR. Phases 3–4 remain unimplemented. Post-merge cleanup remains planned, not activated by Phase 2.

- Create and verify a task-owned linked worktree before repository implementation or writable delegation. If unavailable, request manual recovery and verify the result; never automatically edit the primary checkout.
- Preserve current model, reasoning, provider, authentication, permissions, global settings and unrelated work. Do not introduce an MCP server, daemon, proxy, credential service or new Python dependency.
- Keep the feature default-on; preserve explicit human opt-out. Never auto-disable it to resolve an error.
- Use one to four routine checkpoints for unphased work, or one synchronization attempt per phase. No per-step PR updates within a phase.
- Every task PR starts `[BLOCKED]`; only verified or explicitly user-confirmed merge readiness permits `[READY]`. No automatic merge or force-push updates.
- Automatic cleanup defaults ON through `[task_lifecycle].auto_cleanup = true`; preserve explicit false across setup, upgrades and resume. Whole-lifecycle opt-out also disables automatic cleanup.
- Keep cleanup inexpensive: deterministic Python checks and one bounded cleanup worker on a lightweight compatible native model when delegation is needed. No fixed model name, expensive fallback, repeated code review/test runs, polling or provider/authentication changes.
- Cleanup requires a complete, nonempty associated-PR inventory with every PR confirmed merged. Delete their remote branches first, verify absence, then remove the local worktree folder. Preserve unfinished work and retain resources whenever verification or deletion is uncertain.
- Publication failures leave delivery pending. Safe local work may continue in a verified worktree. Failed worktree validation or unsafe repository state stops implementation.
- Record local milestone completion separately from remote synchronization. Never report an unobserved update as synchronized or inaccessible remote facts as independently verified.
- Supply concrete manual actions after automation fails. Reconcile before retrying an ambiguous remote mutation.
- Retain full Vibe Setup coverage, project checks, independent review, and actual-client execution evidence. Hooks remain documented guardrails.

## Review focus

1. Native worktree creation succeeds but the chat/worker continues in the primary checkout. Phase 1 tests command/worker context and refuses primary roots.
2. Read access succeeds while push or PR permissions fail. Phase 3 tests useful handoff and local progress without credential changes.
3. Setup stops between a file write and journal update. Phase 2 tests exact-state recovery and preservation of later human edits.
4. A lost response conceals successful PR creation, or the user completes publication manually. Phase 3 tests reconciliation without duplicates.
5. Local checks pass while remote requirements are unknown, or a ready PR needs new edits. Phase 3 tests honest readiness and the bounded pause for correcting `[READY]` to `[BLOCKED]`.
6. One of several associated PRs is unmerged, a branch has advanced, or cleanup stops halfway. Phase 3 tests all-PR confirmation, conditional deletion, local preservation, opt-out and resumable ordering.

## Baseline and files

Repository: this repository. Phase 1 merged main: `897874401079d1dfd7236ec1aa385997ccb07640`, including the project-trust onboarding correction. Phase 2 starts from `ebcf002ffdb57bae479f616a4fc824d57e18ad86` after cleanup-plan PR #3 merged. Inspect current state before further implementation and preserve newer work.

Create/reuse a verified isolated development worktree before source changes. At execution, place the approved design and plan under `docs/superpowers/specs/2026-10-22-worktree-first-onboarding-design.md` and `docs/superpowers/plans/2026-10-22-worktree-first-onboarding.md`, fixing links. Keep private qualification records local or in the project's established private evidence home.

| Repository-relative file | Responsibility |
| --- | --- |
| `skills/vibe-setup/workflow.py` | New five-operation helper; one source file initially |
| `skills/vibe-setup/.codex/vibe-workflow.toml` | Minimal Vibe policy defaults |
| `skills/vibe-setup/install.py` | Expose pure existing installation planning; preserve current public API/CLI |
| `skills/vibe-setup/onboarding.md` | Prompt, prerequisites, user actions, setup/recovery and activation |
| `skills/vibe-setup/task-lifecycle.md` | Worktree, checkpoint, PR and manual delivery contract |
| `skills/vibe-setup/tests/test_workflow_setup.py` | Policy, inspection, worktrees and shared disposable fixture |
| `skills/vibe-setup/tests/test_workflow_recovery.py` | Recipe setup, interrupted writes and recovery |
| `skills/vibe-setup/tests/test_workflow_lifecycle.py` | Publication, readiness and manual reconciliation |
| `skills/vibe-setup/tests/test_workflow_cleanup.py` | Cleanup policy, all-PR merge gate, ordered deletion and interruption recovery |
| `skills/vibe-setup/tests/test_install.py` | Existing installer behavior and pure-planning compatibility |
| `skills/vibe-setup/SKILL.md`, package/root `README.md`, `AGENTS.md.template`, `agents/openai.yaml` | User-facing integration and honest capability claims |

Do not change the subagent report schema or add another lifecycle service. Existing guards and `delegation-brief.md` need only a narrow wording change if their continuation instructions conflict with the new lifecycle contract.

## Phase 1 — Verified worktree startup and inspection

**Deliverable:** Working local policy/inspection/start path, including manual worktree recovery. This replaces the old host-enforcement investigation phase.

**Files:** Create `workflow.py`, policy asset, and `tests/test_workflow_setup.py`; add the needed lifecycle guide section.

**Interfaces:** `load_policy(root: Path) -> bool`, `inspect_project(root: Path, clients: list[str]) -> dict`, `verify_worktree(source: Path, worktree: Path, branch: str) -> dict`, `start_task(source: Path, request: dict) -> dict`, and `main(argv: list[str] | None = None) -> int`. All task facts are derived/rechecked from Git; task records are bookkeeping, not proof.

- [x] Run the existing suite as baseline: `python3 -B -m unittest discover -s skills/vibe-setup/tests -v`. Record pre-existing failures separately.
- [x] Add failing tests: absent lifecycle key defaults true; explicit false survives; malformed/duplicate/unknown owned fields fail; unrelated settings survive; nested app roots resolve; ambiguous umbrella returns a boundary question; inspection changes no files, credentials or refs.
- [x] Add disposable-Git tests for a valid linked worktree, primary checkout refusal, wrong branch/common directory, foreign/unregistered worktree, symlink escape, unrelated dirty source preservation, native creation failure followed by Git fallback, and manual creation followed by successful verification. Assert source/worker command roots are explicit.
- [x] Run `python3 -B -m unittest discover -s skills/vibe-setup/tests -p test_workflow_setup.py -v`; require the new cases to fail for missing behavior before implementation.
- [x] Implement with standard-library parsing and explicit-argument Git subprocess calls. Use existing native creation through the skill when available; the helper validates its result or performs the Git fallback. Missing model/permission interception is not a blocker. Missing valid worktree is.
- [x] Add access observations without secret output: effective commit identity, transport, required tool availability, and known account/repository ambiguity. Missing PR access returns a delivery prerequisite while valid local startup remains available. No login, account switch, key creation or global configuration write occurs here.
- [x] Rerun targeted tests to PASS and independently review consequential startup checks. The review found a foreign-checkout destination gap; a failing regression reproduced it and the correction now also rejects foreign Git metadata.

Phase delivery uses a commit in the verified development worktree and one PR synchronization attempt. The associated PR records the remote commit, publication outcome, readiness and any manual action; local completion alone does not establish delivery.


## Phase 2 — Recoverable setup without overwriting customizations

**Files:** Modify `install.py`, `tests/test_install.py`; extend `workflow.py` and setup tests; create `onboarding.md`.

**Interfaces:** Add read-only `plan_setup(task: dict, operation_id: str | None = None) -> dict` for the concrete preview. Add `plan_install(target: Path, non_git: bool = False) -> dict[str, bytes]`. Preserve `install(target, check=False, non_git=False) -> list[str]` and its existing CLI exit behavior. Add `apply_setup(plan: dict, task: dict) -> dict` and `resume_operation(root: Path, operation_id: str, confirmation: dict | None = None) -> dict`. Do not call the mutating installer inside the helper's separate transaction.

- [x] Add failing installer tests proving pure planning writes nothing, produces exactly the existing installer bytes, and preserves existing conflicts, custom hooks, model/effort settings and return behavior.
- [x] Add setup tests for no-op reruns, stale plan, interruptions before/after each owned write, same-plan recovery, concurrent operation lock, symlink/nonregular targets, foreign edits, customized managed files, and secret-bearing configuration collisions. Assert exact preservation rather than blanket snapshot rollback.
- [x] Run both targeted suites and observe failures for the missing interfaces/behavior.
- [x] Extract only the existing install calculation/preflight. Implement helper-owned additions and recovery with a small schema-versioned record under the Git common directory, advisory locks, durable write intent and atomic individual replacements. Validate the worktree again before mutation.
- [x] Implement the design's JSON output and exit codes: 0 verified requested-operation success; 2 necessary user action; 3 unsafe/invalid dependent work. Keep implementation and delivery fields separate. Add tests that inspection success never claims installation/client execution.
- [x] Rerun affected tests to PASS and independently review connected code and documentation. All 76 tests passed. The reviewer found one installer-timeout error-boundary gap; a failing inspect/apply/resume regression reproduced it, and the correction passed focused and full verification.

Phase delivery uses a commit in the verified development worktree and one PR
synchronization attempt. Record the remote commit, readiness and any manual
delivery gap in that PR; local completion alone does not establish delivery.

Execution scope: the existing guard recipe plus the lifecycle policy; invoke the
helper from its complete reviewed source package. Automatic helper installation,
skill wiring and actual App/VS Code qualification remain Phase 4. The original
installer API/CLI remains compatible. Recovery stores hashes and modes, not
custom configuration snapshots; changed/partial foreign state requires manual
reconciliation. No automatic rollback or pending-plan rebase is implemented.

## Phase 3 — PR automation, readiness, post-merge cleanup and manual recovery

**Files:** Extend `workflow.py`, `.codex/vibe-workflow.toml`, `tests/test_workflow_lifecycle.py`, `task-lifecycle.md`, and manual recovery guidance; add `tests/test_workflow_cleanup.py`. Update `delegation-brief.md` and `AGENTS.md.template` with the bounded lightweight cleanup-worker profile, without changing the declaration/report schema.

**Interfaces:** `validate_schedule(mode: str, checkpoint_ids: list[str]) -> tuple[str, ...]`, `render_pr(title: str, body: str, task_id: str, state: str, section: str) -> tuple[str, str]`, `sync_event(request: dict, task: dict) -> dict`, and `manual_actions(failure: dict, observed: dict) -> list[dict]`. Extend `resume_operation` to reconcile publication and distinguish observed/user-confirmed facts. Lifecycle resume adds a fresh `usage` report; existing setup resume stays compatible.

Add `load_cleanup_policy(root: Path) -> bool` and `cleanup_worktree(task: dict) -> dict`; preserve the existing `load_policy(root) -> bool` contract. Extend owned-policy validation to accept only a boolean `auto_cleanup`, default true, and keep unrelated settings unchanged. Invoke cleanup from `sync_event`/`resume_operation` after eligible merge confirmation, using the existing result envelope and external task record. No extra daemon or CLI operation is needed.

The skill prefers sufficient connected tools. The helper's direct automated transport uses existing `gh` and Git. If those are unavailable, return structured publication inputs/manual actions; do not create a connector proxy or extract credentials. Reconcile accessible facts independently and attribute remaining user confirmations explicitly.

- [x] Add schedule/rendering tests: 1–4 unphased checkpoints; any positive phase count; reject blank/duplicate IDs; create `[BLOCKED]`; preserve human title suffix/body; reject malformed/foreign markers; no silent truncation; detect edited managed content.
- [x] Add publication tests with deterministic fake transport for push/PR success, missing authentication/tool, write permission denied, account/actor ambiguity, uncertain creation/update, partial metadata changes, branch divergence, closed/merged/multiple PR matches, human edits and readback mismatch. Assert no force push, duplicate creation or credential switching.
- [x] Add manual handoff tests asserting actual worktree/branch/base/commit, safe command quoting, existing PR lookup before creation, no secrets, and the minimum next step. Simulate user publication with and without agent read access; reconcile the same event and label confirmations correctly.
- [x] Add readiness tests: passing local checks without PR gives implementation-ready/publication-pending; unknown remote requirements never become independently verified merge readiness; existing PR stays `[BLOCKED]`; a PR may leave draft while `[BLOCKED]` to obtain reviews; `[READY]` requires confirmed non-draft status plus applicable readiness requirements or attributed user confirmation. Test failed draft-to-review transition, exact manual action and reconciliation. Resuming changes to a ready PR first corrects the prefix, pausing that PR's implementation if correction needs the user.
- [x] Add snapshot tests: writers confirmed stopped before staging; inability to stop them prevents commit/push of moving work; no-diff task manufactures no commit/PR; publication failure can leave safe local work allowed while worktree failure blocks it. Local checkpoint success does not imply synchronized delivery.
- [x] Run `python3 -B -m unittest discover -s skills/vibe-setup/tests -p test_workflow_lifecycle.py -v`; require new behavior tests to fail first.
- [x] Implement explicit-file staging, authorized commit/non-force push, PR identity lookup, latest-text merge, readback, stable event records and bounded reconciliation. Use conditional metadata updates when available; otherwise document the race limit and route observed conflicts to manual recovery. No universal concurrency guarantee is required.
- [x] Add cleanup tests: absent preference enables cleanup; explicit false or lifecycle opt-out causes zero delete calls and survives setup/upgrade/resume; malformed values fail. Require a complete paginated inventory and at least one associated PR. Multiple merged PRs permit cleanup; any open/draft/closed-unmerged/missing/inaccessible PR or ambiguous ownership prevents all deletion. Cover squash/rebase merge evidence without relying on local ancestry.
- [x] Add deletion/recovery tests using disposable repositories and deterministic remote responses: remote branches are deleted and read back absent before local removal; already-absent branches succeed; changed/recreated heads fail the conditional deletion; default/protected/shared branches remain. Dirty/untracked/ignored files, extra commits, active writers and primary/shared/pinned/foreign worktrees prevent cleanup. Partial branch deletion, timeout, interrupted local removal and reruns preserve progress and never force removal or delete local branch refs.
- [x] Run `python3 -B -m unittest discover -s skills/vibe-setup/tests -p test_workflow_cleanup.py -v`; observe failing tests before implementation. Implement `cleanup_worktree` with the design's ordered deletions, fresh safety checks, an execution context outside the target, and durable per-step results outside the removed folder. Use conditional remote deletion; if unavailable, request manual recovery. Reconcile uncertain outcomes before retrying and keep the local folder until every remote deletion is confirmed.
- [x] Document the inexpensive cleanup worker: native lightweight compatible model selected at dispatch, three-minute/one-attempt budget, Python verification and ordered mutations, compact report, no routine test/review reruns or polling, and no silent expensive-model fallback.
- [x] Rerun cleanup, lifecycle and installer preservation tests to PASS. Review the destructive-operation boundaries independently. Document default-on cleanup, its opt-out, first-observed-merge trigger, exact manual steps and cleanup status separate from merge status.
- [ ] Verify final delivery through the phase PR: commit and synchronize once, check the remote head and metadata, and confirm readiness. Local implementation and review are complete; do not declare delivery while synchronization is pending.

Implementation evidence: all 120 tests passed, including original installer/setup preservation tests. The independent read-only review found two recovery defects: unresolved READY intent after a lost response, and missing manual readiness-withdrawal confirmation. Both were reproduced and fixed with passing regressions; observed draft state also cannot be overridden by a full READY confirmation. Cleanup resume for delivered events requires fresh ownership/writer information, but no old build/review logs. Actual client qualification and global installation remain Phase 4.

## Phase 4 — Skill integration and App/VS Code qualification

**Files:** Update skill/template/default-prompt/README files, both guides and relevant tests. Keep reusable source and installed package separate.

- [ ] Add prompt/fixture cases for an already-working project, a fresh project missing prerequisites, multiple accounts, untrusted project hooks absent from approval UI, lifecycle and independent cleanup opt-outs across upgrade, partial setup, missing PR write access and manual completion. Require only necessary questions and preserved settings.
- [ ] Integrate the five operations into the full setup skill and normal task instructions. Keep command/worker roots explicit. Explain local completion versus delivery, actual product blockers, manual handoff, project trust before hook trust and activation in the exercised checkout.
- [ ] Expose the automatic-cleanup preference during onboarding and document that it defaults ON. Reuse explicit choices without asking again. Confirm all associated PRs merged before automatic remote-branch deletion and subsequent local-worktree removal; report pending recovery without changing merge status.
- [ ] Run `python3 -B -m unittest discover -s skills/vibe-setup/tests -v` and `git diff --check`; require relevant tests to PASS. Validate the skill package with existing tooling without installing global dependencies.
- [ ] In disposable actual App and VS Code sessions, verify discovery, task worktree startup, worker directory, safe rerun, one phase synchronization, a controlled publication failure and manual/resume behavior. Qualify cleanup opt-out, all-PR confirmation, ordered deletion and recovery from each client's supported worktree lifecycle. Preserve model/authentication/permissions. Do not require native denial of every alternative tool or repeat the rejected universal-enforcement experiment.
- [ ] Obtain independent read-only review of the exact diff, source coverage, worktree checks, access behavior, recovery, human-content preservation and user-facing claims. Fix confirmed issues and rerun affected checks.
- [ ] Attempt final PR synchronization. Keep `[BLOCKED]` until confirmed non-draft status and applicable readiness requirements are established; then apply/verify `[READY]` or give the user exact manual promotion steps with remaining checks and any pending “Ready for review” action explicit. Never merge automatically or claim publication complete while pending.
- [ ] When installation is authorized, preserve the previous installed package, reconcile customizations, update the reviewed files and verify hashes/discovery/execution. State the checkout and clients actually activated. Missing permissions or user actions remain named pending steps, not a hidden downgrade.

## Self-review and handoff

Every review-focus case maps to explicit tests above. Setup recovery and publication share `resume_operation`; neither treats local JSON as authority or a remote fact. Phase boundaries have one synchronization attempt each. Pending publication is not silently marked done, and the worktree prerequisite is not weakened by manual fallback.

The cleanup extension remains within Phase 3 and Phase 4 qualification. Its default, opt-out, all-associated-PR gate, remote-first deletion order, preservation checks and interruption recovery each map to explicit tests. This plan update performs no cleanup and introduces no runtime setting changes.

Independent read-only review found one draft-state gap. The design and readiness tests now distinguish leaving draft for review from `[READY]` for merge, including failure and manual recovery of that transition.

Recommended execution remains inline in one verified development worktree with independent reviews at consequential boundaries. This avoids parallel writers over the shared helper and local state. Phases 1 and 2 are merged. Phase 3 implementation is verified; delivery is tracked by its PR state. Phase 4 remains pending. No further search for perfect native enforcement is required by the current scope.
