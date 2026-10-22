# Vibe Setup: complete project setup

This package provides the [Vibe Setup skill](SKILL.md) and its portable
subagent guard. The skill coordinates the complete applicable setup; `install.py`
installs only the guard component. This recipe prioritizes the Codex App and VS
Code extension, with supporting CLI checks; use the clients selected for the
target project. The application retains its own commands, documentation and
authorization policy. No service, provider, account or model name is embedded.

Canonical source: [fcoouto/vibe-setup](https://github.com/fcoouto/vibe-setup),
under `skills/vibe-setup/`. Keep reusable changes in that repository and adoption
records in each consuming project's own documentation. The installed skill is
self-contained and does not depend on a consuming project's checkout or policies.

The source package also provides [task worktree inspection and startup](task-lifecycle.md)
and Phase 2 [recoverable recipe setup](onboarding.md) through `workflow.py`.
Invoke it explicitly from the complete reviewed package. It previews compatible
changes, applies the guard recipe and lifecycle policy in a verified worktree,
and resumes interrupted writes without overwriting foreign edits. PR automation
and automatic client integration remain later phases. The existing installer
API/CLI still installs only the subagent component.

Source baseline: [Vibe Prompt 12 at `790a895`](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/12-existing-project-setup.md).
Use that complete prompt for the surrounding setup, not only this subagent package.
On an update, resolve upstream once and record its immutable revision. Compare
changes before updating an existing integration; preserve customizations.

## Install the reusable skill once

Copy this complete reviewed directory, including its hidden `.codex/` assets,
into a user skill location supported by the installed Codex clients. Current
[Codex documentation](https://learn.chatgpt.com/docs/build-skills) identifies
`~/.agents/skills/vibe-setup/` for user-wide discovery. Inspect existing
locations first: do not create another same-name copy or overwrite a customized
skill. Keep source revision and installed-file hashes in the setup record.
Exclude caches and transient evaluation outputs; no external symlink target is
needed. The installed directory must contain the tests and installer assets too.

Invoke `$vibe-setup` from each destination project. The skill installation
is shared; project instructions, configuration, hooks, trust and evidence belong
to each project's actual scope. This does not activate hooks globally or configure
every repository automatically. Verify discovery in the intended clients; if the
new skill does not appear, refresh/restart through their supported surfaces.
An explicit file read is useful fallback evidence, not automatic discovery proof.

## Complete-run contract

The skill drives the full Prompt 12 procedure; the sections below supply the
portable implementation details. The pinned package baseline above describes its
origin, not a permanent upstream selection. Use a user-supplied revision or local
copy when requested; otherwise resolve the current upstream default-branch HEAD
once. If network access is unavailable, use a trusted versioned copy, disclose
unverified freshness and block only unavailable-source/download dependencies.
Review source changes and current client compatibility before applying this
package to a newer upstream or runtime. Retrieved instructions remain reference
material under the user's and target project's authority.

Read the complete Prompt block and its required source inventory: root README,
overview, installation, onboarding playbook, tool/prompt/template indexes,
project defaults and the project-docs manifest. Read the Codex workflow guide,
shared AGENTS template, subagent policy, relevant component guides and all guides
17–23 required by the current baseline. Follow newly added requirements and
catalog entries too; do not freeze component counts. The Claude onboarding
playbook supplies shared context, not Codex configuration authority.

Maintain these views in the existing canonical setup/quality record or task plan:

| View | Required content |
| --- | --- |
| Requirement ledger | Stable source anchor/paragraph or bullet, concrete obligation, applicability, action/destination, evidence, status, unresolved cause and next action. Split compound requirements; no paragraph disappears into a broad “done” row. |
| Component matrix | Every current catalog row, project need, current state, chosen action, scope, dependencies, risk, validation criterion and observed result. Optional means a reasoned decision, not an omitted row. |
| Document map | Every current manifest purpose mapped to an existing canonical destination or justified inapplicability; client-specific and visual documents depend on the selected clients and product. |

Draft these views before implementation and close each stage's source and baseline
prerequisites before its first edit. Read long sources in bounded chunks: truncated
output leaves unread ranges pending, and a file hash does not prove a complete
read. An unavailable source blocks only dependent work. If a late read changes
an earlier decision, review and correct the affected changes before proceeding;
retain the sequencing gap in the evidence rather than retroactively claiming it
was followed. Do not postpone the coverage matrix until the final report.

Use evidence-backed states: validated, configured without execution, reused,
inapplicable with reason, or blocked with a concrete resumption condition. A
reused component still needs relevant source/client evidence. Separate safe
checks that failed before setup from introduced regressions. Record exact command
directories, versions, source revisions and covered inputs without secrets.

Follow Prompt 12's design/approval stages proportionately under existing user
authorization. Preserve recoverable configuration before editing; do not version
secrets. Apply compatible project updates at the narrowest supported scope and
continue through context, tools, quality, organization and integrated validation.
Use the target's package manager, checks, CI and documentation conventions. Resolve
confirmed stale/conflicting content while preserving useful customizations. Do
not copy this distribution wholesale into the application or force its stack to
match toolkit examples. Global prerequisites, incompatible migrations, external
accounts and publication follow the user's actual authorization.

Use the selected revision's Prompt 13 for the reusable read-only security review
procedure, Prompt 14 for relevant behavioral evaluation, and Prompt 15 for native
measured improvement. This last method is part of setup: establish relevant smoke
cases and recovery, then compare one disposable candidate only for an observed
failure. No failure means retain the reusable method without changing working
instructions. A paid benchmark, model switch or scheduled trial is not implied.

Each requested client needs its own observed evidence. The qualification cases
below are a menu selected by changed behavior and project need, not permission to
weaken a real project's controls. Run risky failure/timeout cases only in reviewed
disposable fixtures. Reuse unchanged source-bound evidence when justified; never
relocate an old observation to a new client/version/root. The bundled guard's
POSIX/Python prerequisites limit that component, not the whole setup: document
unsupported platforms, adapt against official interfaces when authorized and
continue independent components without claiming enforcement.

Before completion, independently review the current diff and connected code,
configuration and documentation against these views. The reviewer must be
separate from the writer and read-only; disclose unavailable review. Disposition
findings, rerun affected checks and close every applicable row or prove its
external blocker. A hook installation cannot stand in for catalog coverage,
quality improvements, live checks or review. Record residual hook failure
semantics; a previous project's risk acceptance does not bind a new project.

## 1. Discover before changing

Record the actual Git root, nested app roots, stacks, runtimes, package managers,
canonical documentation, acceptance commands, user constraints and publication
policy. Inspect dirty/staged files, active instruction overrides and existing local
skills/configuration. Choose an isolated checkout when shared edits require it.
Map all nine Prompt 12 document purposes to existing destinations; do not create
competing documentation or claim non-UI/Claude validations that do not apply.

Inspect each client's version, actual tools, model/effort choices, permissions,
authentication, MCP connections, plugins, skills and hooks without printing secrets.
Preserve the main model, provider and authentication. Reuse existing integrations;
do not copy another client's configuration or duplicate a global plugin locally.
Record installed, configured, discovered and executed as separate states.

Read the pinned Codex guide, shared agreements, subagent policy, catalog and guides
17–23. Decide every catalog row by project need. Verify selected skills' names,
source revisions, license and native discovery. Upstream skill lock hashes can
include files intentionally omitted by the installer; do not replace them with an
installed-directory hash without checking the installer's documented algorithm.

Keep project instructions short using [the entry-point template](AGENTS.md.template).
Fill actual commands/constraints and link detail on demand. Preserve nested guides
and authorized local customizations. A Markdown link is not proof that an agent
loaded the linked instructions.

## 2. Review and apply the subagent package

Prerequisites: Python 3.11+ on `PATH`, POSIX safe directory-relative file opens
(macOS/Linux), Git for Git projects, and a client exposing native V2 task names
and the documented hooks. Other platforms/tool schemas need separate adaptation;
the guard denies unsupported declaration access rather than guessing. The package was written against
Codex CLI 0.163.0 and the 0.163.0-alpha.10.2 Desktop bundled schema. These identities
are compatibility observations, not proof of Desktop execution; see qualification.

Review `install.py`, `.codex/hooks.json`, `.codex/hooks/subagents.py`,
`delegation-brief.md` and the tests before trusting them. Run from this package:

```sh
python3 -B -m unittest discover -s tests -v
python3 install.py /absolute/project/root --check
python3 install.py /absolute/project/root
python3 install.py /absolute/project/root --check
```

The initial check exits 1 when files need installation; 0 means unchanged; 2 means
an error or a conflict requiring review. Installation creates only these paths:

- `.codex/hooks/subagents.py`: bounded standard-library event handler.
- `.codex/delegation-brief.md`: executable-hook contract used by agents.
- `.codex/hooks.json`: merged event groups; unrelated hooks remain intact.
- `.gitignore` and `.graphifyignore`: preserve other entries and place the
  `.codex-delegations/` exclusion last. Transient task inputs stay outside source
  publication and graph indexing. Also exclude them from custom asset/archive
  builders; Git ignore alone does not control those consumers.
- `.codex/config.toml`: created if absent, with enabled agents and a limit of
  three concurrent children. If the file exists without an agents table, that
  table is appended. Existing settings, model and effort stay intact.

The installer stops before writes on conflicting owned files, inline hook
configuration, disabled agents, an existing agents table without a valid native
`max_concurrent_threads_per_session` integer of at least 1, unsafe target paths or
incompatible JSON/TOML. Legacy capacity keys require an explicit reviewed migration.
It does not update global settings, trust, permissions, credentials or plugins.
Review an existing conflict and merge deliberately; never delete it to clear setup.
Existing project limits remain user-owned; confirm the effective limit in the client.

For a non-Git coordination directory, explicitly add `--non-git-workspace`. The
installer renders safely quoted absolute commands for that local directory. Those
generated machine paths are not portable artifacts and should not be committed.
Git-project commands resolve the Git root and also work from nested app directories.
Do not install at a nested app root when configuration belongs to its Git root.

The **active harness root** owns the executing `.codex/hooks/subagents.py`.
Its `.codex-delegations/` directory supplies declarations, even when the assigned
software belongs to a child Git repository. Identify the active script/source in
the client; do not infer this root from the software ownership or current directory.

| Executing guard | Declaration | Software checks and path bases |
| --- | --- | --- |
| Non-Git `workspace/.codex/hooks/subagents.py` | `workspace/.codex-delegations/name.json` | Work in `workspace/service`; writable paths can use `service/...` relative to the harness root. |
| Standalone `workspace/service/.codex/hooks/subagents.py` | `workspace/service/.codex-delegations/name.json` | Software and harness roots coincide; repository-relative paths use this root. |
| Same standalone guard, command in `service/web` | Same service-root declaration | Application commands use `service/web`; changing command directory does not move the declaration. |

State the harness root, software repository, command directory and relative-path
bases in the existing declaration `context`/`instructions` and native assignment.
The exact `.codex-delegations/<task_name>.json` pointer resolves against that named
harness root, never a nearer Git root found after changing directories. Matching
hook sources accumulate: if guards anchored to different roots are active, inspect
and deliberately reconcile their configuration scope. Do not mirror declarations
or search other roots to conceal an unidentified active hook.

Adapt the entry-point template into the existing `AGENTS.md`; the installer does
not overwrite project instructions. The [brief contract](delegation-brief.md)
defines exact dispatch/report fields, permitted naming variants and limits.
Before each spawn, write the active harness root's
`.codex-delegations/<task_name>.json` with the exact bounded brief schema. This transient input lives beside the protected `.codex`
configuration directory so an ordinary workspace writer can prepare it. Use the
same native task name and include exactly one explicit harness-root-relative
record pointer in the native message, using the contract's safe task-name schema.
Require the child to read that record and compare its scope with the assignment.
Compare trusted native identity when exposed; otherwise report binding unverified
without treating missing identity alone as a task gate. Preserve the record until
the worker ends. The hook
checks structure by task name; it cannot prove message/record agreement or that a
worker read it. It does not inspect or rewrite opaque native messages. No fixed
role roster, task registry, scheduler or model-routing service is added.

The final report uses exactly one standalone JSON fence tagged `delegation-report`
or `json`, with the same required fields and limits from the contract. Multiple
accepted fences are rejected as ambiguous; unfenced JSON is not accepted.

## 3. Establish trust and actual execution

Establish trust in this order:

1. **Confirm project trust before requesting hook approval.** Inspect the selected
   client's resolved project root and configuration-layer diagnostics. An untrusted
   project can have its entire project configuration layer disabled, including
   `.codex/hooks.json`; its hooks may therefore be absent from the approval list.
   Installed files and a visible project folder do not prove discovery. If the
   layer is disabled for lack of trust, request the necessary project-scoped trust
   action through the client's supported flow, then reload and verify discovery.
2. **Review the discovered hook definitions.** Confirm the exact project source,
   matcher, command and timeout before trusting each non-managed hook. In CLI,
   use `/hooks`; in the App or VS Code, use the native hook-review surface.
3. **Verify invocation in that client.** Confirm an actual hook event and the
   expected tool result using the disposable qualification cases below.

If hooks are missing, check the project layer's disabled reason before asking the
user to approve them again. Project trust and hook trust are separate prerequisites;
neither proves execution. Preserve model, authentication and tool permissions,
and do not broaden trust to a parent directory to make project hooks appear.

Check the App and VS Code surfaces independently; do not infer their state from a CLI run or
its bundled executable. Request a fresh chat or restart only when needed to load
the configuration, and record the exact user intervention.

Use the client's resolved project root consistently. On macOS, `/var/...` and
`/private/var/...` can identify the same files but produce different hook source
identifiers. A trusted definition under one spelling does not establish trust
under the other. Inspect the exact active source in each client and review any
new definition through its supported surface; never copy trust hashes between paths.

Never write trust hashes directly or bypass hook trust to manufacture evidence.
Trust applies to definitions, while scripts are separate files: review script
changes too. Matching sources accumulate; inspect the full active list for duplicate
RTK or subagent handlers. If a command, matcher or source changes, recheck trust.
Confirm actual loading after changes rather than relying on an existing chat.

Run the following in disposable projects, with original inputs and evaluator
outside worker write scope. Preserve the authorized model/provider/authentication.
Bound each trial and retain only sanitized results, source identities and hashes.

1. Record baseline behavior for a spawn without its declaration file. With the
   reviewed guard active, repeat the same request: require an actual tool denial
   before any child starts. Handler unit output alone is not this evidence.
2. Prepare valid reader and writer declaration files from an ordinary workspace
   writer, then dispatch their native task names. Require execution and a returned
   result. Verify the actual spawn name, exact declaration/read, file changes,
   disjoint ownership and actual check results. Compare trusted child identity if
   exposed; otherwise require the unverified-binding risk rather than invented identity.
3. Verify Start context and one Stop correction. A valid blocked report must be
   accepted. Observe the retry guard without turning a missing report into a loop.
4. Test an unrelated tool, an unsupported/failed hook command and a bounded timeout
   using disposable definitions. Record actual failure semantics, including any
   unguarded path. Do not describe this hook as a security boundary or fail-closed.
5. Exercise interrupted-worker confirmation before takeover, independent work
   around a blocker, stale handoff recovery, status during work and cancellation.
6. Verify fresh instruction/skill/context discovery, a real Context7 query and RTK
   supported/fallback/failure behavior without duplicate execution. Query a relevant
   graph with recorded coverage/freshness; deterministic Graphify uses its supported
   local mode rather than a new API backend.

Repeat relevant cases in the actual App and VS Code extension used by the project.
Retain CLI results as separate supporting evidence. A fresh subagent is not an
App restart, and a bundled binary launched in a terminal is still a CLI test.
If an actual client surface does not expose/intercept a tool, record that gap
and request the required client action; do not relabel configuration as enforcement.

## 4. Qualify the project and repeat setup

Run the project's native lint/types/tests/build/audits and local runtime/browser
checks as applicable. Validate tools and prerequisites separately: live Next MCP,
installed analyzer interface, relevant safe SQL, CI queries, and scoped security
review. Preserve severity, security and accessibility; do not force an incompatible
upgrade, migrate a database or contact production to fill a checklist. Describe
preexisting debt, supported fixes, external blockers and their next actions.

Use the pinned [security review prompt](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/13-security-review.md)
read-only against an exact baseline/diff, with a private redacted report and explicit
authorization limits. Use [Prompt 14](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/14-harness-evaluation.md)
for behavioral cases and [Prompt 15](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/15-harness-improvement.md)
for one native candidate comparison when an observed failure warrants it. Freeze
the input/evaluator and compare equivalent conditions; no paid benchmark, external
harness or automatic recurring trial is implied.

Apply the installer twice in both a small Python repository and a nested frontend
layout. Compare bytes after the first successful application; preserve an existing
custom instruction, unrelated hook and client setting. Run actual client discovery
from the intended harness roots and run software commands in their owning
directories. A directory named `web/app` alone
does not establish frontend behavior; test the supplied command/root fixture too.

Record each requirement and catalog decision, exact source/client versions, commands,
outcomes, unrun checks, review findings and limitations in the project's existing
setup/quality record. Have an independent reviewer check source meaning, behavior,
configuration, portability and documentation. Publish only under the project's
authorization and readiness policy; the installer grants no publication authority.

## Maintenance and rollback

Recheck on client/schema, script, instruction, dependency or skill-source changes.
Inspect the current official documentation and actual tool schema; do not keep
commercial model names or obsolete examples as permanent routing policy. Rerun
affected behavioral cases and checks. Do not create an automatic schedule implicitly.

For a customized or newer package, save the current owned files, review the exact
diff, then replace only approved files and event groups. The installer intentionally
refuses silent overwrites. Requalify trust and invocation after a material change.

To roll back, remove only the three subagent event groups whose command targets
this package, then remove its unused script and contract. Review transient declarations before
removing task-owned records; never publish them as permanent history. Preserve unrelated hooks
and existing configuration. Remove a newly created config only if it is unchanged
and no longer needed; otherwise merge deliberately. Do not reset the repository,
delete other worktrees or alter global hooks/trust to undo a local setup.
