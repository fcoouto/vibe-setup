# Vibe Setup

A reusable Codex skill for adopting, repairing, updating and verifying the
[Vibe Coding Toolkit](https://github.com/soumatheusgomes/vibe-coding-toolkit)
in existing projects. It covers project instructions, applicable integrations,
native subagents, validation and independent review.

## Delegation and model policy

Start with the [delegation policy](skills/vibe-setup/delegation-brief.md):
[roles alongside specialties](skills/vibe-setup/delegation-brief.md#role-and-specialty),
[optional native role display](skills/vibe-setup/native-display.md),
[task/specialty table](skills/vibe-setup/delegation-brief.md#task-and-specialty-guide),
[native role metadata](skills/vibe-setup/delegation-brief.md#native-role-metadata),
[ability versus runtime capacity](skills/vibe-setup/delegation-brief.md#demonstrated-ability-versus-runtime-capacity),
[route selection](skills/vibe-setup/delegation-brief.md#choose-the-execution-route),
[model discovery and capacity](skills/vibe-setup/delegation-brief.md#discover-models-and-check-capacity),
and [hook enforcement versus coordinator checks](skills/vibe-setup/delegation-brief.md#what-enforces-each-rule).

Prefer [Local Model Delegation](https://github.com/fcoouto/local-model-delegation)
for tasks that match an enabled, approved local
model's assessed capability and available capacity. Codex verifies every proposal
and owns integration. Otherwise use authorized native execution. Local proposals
are not native subagents and do not pass through the native subagent hooks.

The guide contains Vibe's agent-facing routing policy and native contract, and
points to the plugin's own documentation for local execution. It is installed as
`.codex/delegation-brief.md` in each destination project. Setup links it from that
project's existing `AGENTS.md` and documentation; the installer does not edit those
entry points automatically.

Worker selection is opt-in: the Coordinator can choose model and reasoning for
workers by task difficulty and risk while keeping its own settings unchanged.
Qualified approved local models have priority when the complete task fits and
capacity is admitted. Native fallback, bounded recovery, qualification states and
full-cost measurement follow the [selection policy](skills/vibe-setup/delegation-brief.md#difficulty-based-worker-selection).
The helper prepares/checks decisions; it neither calls models nor certifies model
competence. App and VS Code require separate observed selection evidence.

## Use

Review the self-contained package in [`skills/vibe-setup`](skills/vibe-setup/README.md),
then install that directory once using Codex's skill installer. For example:

```text
Use $skill-installer to install the skill at skills/vibe-setup from
https://github.com/fcoouto/vibe-setup using the reviewed revision.
```

Keep one installed copy and preserve any local customizations. Open the target
project and invoke `$vibe-setup`. The skill adapts the setup to that project's
instructions, stack, selected clients and authorization. Installing the skill
does not configure every project automatically.

The [complete recipe](skills/vibe-setup/README.md) covers source selection,
installation, trust, client qualification, evidence, review, maintenance and
rollback. Its `install.py` installs only the project-local subagent guard.
The integrated skill uses a small Python helper for [verified worktrees and
recoverable setup](skills/vibe-setup/onboarding.md), PR publication and default-on
cleanup with opt-out. Normal tasks invoke the helper through project instructions.
App and VS Code qualification remains evidence for the actual client/version/root;
installation alone never establishes execution.

### Upgrade the installed skill

Paste this prompt in Codex:

```text
Use $vibe-setup to safely upgrade the installed skill to the latest official release.
```

The skill reviews the release, backs up managed files, preserves settings and
customizations, and reports conflicts or pending validation. Project setups are
separate. After a successful skill upgrade, Codex asks whether you want to update
a project and provides two steps: create a new chat inside that project, then
paste the supplied project-update prompt. You choose whether and where to continue.

For updates, the [update workflow](skills/vibe-setup/update-contract.md) tracks the
shared skill, explicitly selected consumers, native client tests and delivery in
one recoverable private record. The [qualification helper](skills/vibe-setup/qualification.md)
prepares complete native dispatch arguments and separates execution, first-report
validity and inherited settings. Standard upgrades validate hooks and native
role metadata without an external display service. Consumer testing is separate
and requires an explicit request. Current model and execution settings remain
under each client's control.

## Develop

The portable guard and tests require Python 3.11+ and POSIX support (macOS/Linux).
No third-party Python dependency is required for the package tests:

```sh
python3 -B -m unittest discover -s skills/vibe-setup/tests -v
```

The skill and its assets live under `skills/vibe-setup/`. Packaged `.codex` files
remain installation inputs. The separate root `.codex` copy configures this
repository as a Vibe Setup consumer; read [the contributor guide](AGENTS.md) and
[its delegation policy](.codex/delegation-brief.md) for development. Local
`.codex/config.toml` stays ignored; merge the portable example without replacing
existing model, provider, reasoning or permission preferences.
Project-specific adoption records belong to each consuming project.

Hooks are workflow guardrails, can fail open, and do not sandbox subagents.
Actual execution must be qualified in each selected Codex client; installation
and unit tests alone are not client qualification.
