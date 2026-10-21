# Vibe Setup contributor guide

This repository owns the reusable skill in `skills/vibe-setup/`, its installer,
guard, templates, tests and product documentation. Keep consuming projects'
private records, policies and machine-specific configuration outside this repository.

Read the package README and relevant tests before changes. Preserve the skill's
project-specific authorization, model/provider choices, customizations, trust
boundaries and explicit hook limitations. Do not silently broaden setup scope.
Packaged `.codex` assets are for destination projects; do not move them to the
repository root or activate them merely to work on the source.

Run `python3 -B -m unittest discover -s skills/vibe-setup/tests -v` and
`git diff --check`. Tests require Python 3.11+ on macOS/Linux. Update affected
product documentation and independently review nontrivial changes. Keep test,
installation, discovery and actual-client evidence distinct.

Use supported native delegation when useful, preserve the current model/provider
and authentication, assign one writer per file and keep reviewers read-only.
Verify workers' actual changes and checks. Keep transient task records out of Git.
Publication and deployment follow the user's explicit authorization.
