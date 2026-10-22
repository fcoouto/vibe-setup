# Vibe Setup contributor guide

This repository owns the reusable skill in `skills/vibe-setup/`, its installer,
guard, templates, tests and product documentation. Keep consuming projects'
private records, policies and machine-specific configuration outside this repository.

Read the package README and relevant tests before changes. Preserve the skill's
project-specific authorization, model/provider choices, customizations, trust
boundaries and explicit hook limitations. Do not silently broaden setup scope.
Packaged `.codex` assets remain installation inputs. This repository also consumes
the reviewed setup through its separate root `.codex` copy; keep that developer
configuration distinct from the distributable package and update it deliberately.

Run `python3 -B -m unittest discover -s skills/vibe-setup/tests -v` and
`git diff --check`. Tests require Python 3.11+ on macOS/Linux. Update affected
product documentation and independently review nontrivial changes. Keep test,
installation, discovery and actual-client evidence distinct.

Use supported native delegation when useful, preserve the current model/provider
and authentication, assign one writer per file and keep reviewers read-only.
Verify workers' actual changes and checks. Keep transient task records out of Git.
Publication and deployment follow the user's explicit authorization.

## Delegation policy

Read the [delegation policy](.codex/delegation-brief.md) before choosing local or
native execution. The main agent is Coordinator; each worker has an explicit role
and separate specialty. Prefer local execution only when enabled routing, existing
approval, matching assessment evidence and safe capacity permit the complete task.
Otherwise retain authorized native execution. Unknown roles are rejected; a custom,
nonempty specialty is allowed but remains **Not assessed** without matching evidence.
Role labels never select a native profile or change model, reasoning, provider,
authentication or permissions. Preserve these settings and all explicit user limits.
The [optional native display adapter](.codex/native-display.md) only fills absent
or null `agent_role`; any supplied value wins. Installing its files does not
activate it. Reuse an already qualified shared integration without adding wrappers;
actual badge delivery needs separate client evidence.

## Vibe task lifecycle

Use the reviewed installed Vibe Setup helper at
`$HOME/.codex/skills/vibe-setup/workflow.py` and its adjacent `task-lifecycle.md`.
Resolve the installed skill's actual path if this location differs; do not copy
its helper into this repository. Normal tasks use the helper directly, without
repeating full onboarding. Read `.codex/vibe-workflow.toml`: lifecycle and cleanup
default ON; preserve independent `enabled=false` and `auto_cleanup=false` choices.

Inspect first. Unless opted out, create or adopt a linked worktree and require
`start` to return `implementation=worktree_verified` before editing. Use its
returned command and worker roots; a failed verification never permits primary
checkout edits. Preview setup with `inspect --task-id`, apply the reviewed plan,
and resume the same operation after interruption. With lifecycle disabled, use
the reviewed component installer and ordinary authorized delivery instead.

Follow the installed lifecycle contract for `sync` and `resume`, under the
repository's publication authority. Stop writers and supply explicit files plus
current checks and independent review. Plan at most four checkpoints or one sync
per phase. PRs start draft `[BLOCKED]`; `[READY]` requires current local/remote
checks, review and non-draft status. Withdraw READY before further edits, preserve
human content, reconcile uncertain results and never auto-merge. Publication
failure means “blocked; PR update pending”, with a concrete next action.

After all associated PRs are observed merged, cleanup defaults ON. Verify task
ownership and stopped writers, delete and verify eligible remote branches first,
then remove the exact clean worktree through its owner without force. Keep local
branch refs; preserve ambiguous, shared or dirty resources and explicit opt-outs.
Installation, client discovery and actual execution are separate evidence.

For reusable read-only security review, use
[Vibe Prompt 13](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/13-security-review.md)
against an explicit revision/diff, keeping redacted findings private. Use
[Prompt 14](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/14-harness-evaluation.md)
for relevant disposable harness cases and
[Prompt 15](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/15-harness-improvement.md)
for one bounded native comparison after an observed failure. Preserve settings,
checks and original inputs; no official Harness2 CLI or paid benchmark is implied.
Reapply Vibe Setup after material package/client changes and record installation,
discovery and execution separately in private setup evidence.
