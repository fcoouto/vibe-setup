# Vibe Setup

A reusable Codex skill for adopting, repairing, updating and verifying the
[Vibe Coding Toolkit](https://github.com/soumatheusgomes/vibe-coding-toolkit)
in existing projects. It covers project instructions, applicable integrations,
native subagents, validation and independent review.

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
The source helper also supports [verified worktrees and recoverable setup](skills/vibe-setup/onboarding.md);
PR automation and automatic client wiring remain later phases.

## Develop

The portable guard and tests require Python 3.11+ and POSIX support (macOS/Linux).
No third-party Python dependency is required for the package tests:

```sh
python3 -B -m unittest discover -s skills/vibe-setup/tests -v
```

The skill and its assets live under `skills/vibe-setup/`. Packaged `.codex` files
are installation inputs, not root configuration for this source repository.
Project-specific adoption records belong to each consuming project.

Hooks are workflow guardrails, can fail open, and do not sandbox subagents.
Actual execution must be qualified in each selected Codex client; installation
and unit tests alone are not client qualification.
