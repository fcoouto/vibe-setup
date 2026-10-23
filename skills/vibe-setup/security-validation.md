# Mandatory, proportional security validation

Security validation runs at the three gates below. Readiness and release do not
need a separate user request. At a gate, inspect the actual diff, connected callers,
project requirements and trust boundaries; record risk, required checks and
applicability privately. Require current, complete, passing evidence for every
required check before accepting the gate. Missing tools, skipped coverage,
unresolved findings and unavailable review are blockers,
not successful checks. Lifecycle and cleanup opt-outs do not waive this contract.

## Choose the smallest sufficient review

Use the same R0/R1/R2 impact vocabulary as the delegation policy. Risk follows
behavior and data exposure, not line count, file extensions or model choice.
Uncertainty takes the higher plausible risk until investigation resolves it.

| Risk | Scope | Required evidence names |
| --- | --- | --- |
| R0 | No executable, configuration, dependency, data-handling or trust-boundary impact; for example a verified cosmetic edit. | `impact-review`: explain the inspected scope and why deeper checks do not apply; `trailofbits-update-review`: the upstream check and applicability decision described below. |
| R1 | Ordinary behavior changes or refactors without a sensitive boundary change. | R0 checks plus `security-validation`: focused diff/caller review and relevant negative or regression cases. |
| R2 | Auth, permissions, secrets, privacy, untrusted input, crypto, execution, security controls, destructive data effects, or comparable exposure. | R1 checks plus `independent-security-review` by a separate qualified reviewer. Include adversarial cases for the affected boundary. |

UI can introduce XSS; logging can disclose secrets; agent instructions and
executable documentation can change permissions. None is automatically R0.
Dependency and CI changes require examining their actual exposure. Add all
project-required checks to the assessment, regardless of tier. A small R2 edit
still needs deep review of its affected boundary, not a whole-repository audit.
The independent general reviewer may also perform the security review if its
explicit scope and evidence cover both; a renamed author self-review cannot.

## Review triggers

There are exactly three security-review triggers. Each gate includes the
[Trail of Bits update check](#check-trail-of-bits-updates-within-each-gate).

| Trigger | Required action | Depth and timing |
| --- | --- | --- |
| Work is proposed as implementation-complete, `[READY]`, or a production candidate | Complete the declared checks against the current snapshot and resolve findings. | R0: impact review. R1: focused diff/caller review plus targeted security tests. R2: those checks plus independent security review. Run expensive methods here when required and scope is stable. |
| A release or deployment is about to run, including a hotfix or lifecycle opt-out | Run `check-security` for the exact clean release revision and apply project artifact/provenance checks. | Preflight is mandatory every release. Reuse current evidence or verified content-equivalent evidence; run fresh review where binding, scope, coverage or external-data freshness cannot be established. |
| The user or project explicitly requires a security review | Perform the requested scoped review regardless of draft status. | Follow that authority and its stated depth; preserve model/provider constraints. |

A passing test, successful build or generic review does not cancel these triggers.
Task startup, worktree creation, edits, scope changes, BLOCKED checkpoints and
status requests do not independently launch a security review. Ordinary safe
implementation and focused tests continue during drafts. Changes and findings
invalidate affected evidence; withdraw READY before further edits and resolve
required gaps at the next gate. This maintains evidence without creating another
review trigger. No background monitoring or audits of idle worktrees are implied.

## Spend effort when it can change the decision

A worktree's existence does not trigger an audit. During drafts, use the focused
tests needed to implement the change safely. Keep required
security checks pending until their prerequisites and scope are stable. Run
expensive analysis or independent security review only within one of the three
gates, at the depth required by the change or explicit request. Do not launch a full
scanner suite, repository audit or reviewer on every edit, commit, checkpoint,
worktree creation or status request. Checkpoints can stay BLOCKED with incomplete
security evidence; avoid spending tokens merely to make a draft appear ready.

Set a bounded scope and stop condition for each selected method. Prefer existing
deterministic tests and scanners for mechanical checks; use model analysis for
impact, trust-boundary reasoning and findings that need judgment. Avoid duplicate
general/security reviews when one independent review covers both. Do not poll
idle worktrees, scan other worktrees automatically or change model/provider to
reduce cost. Expensive tooling is conditional; mandatory security acceptance is not.

Reuse valid evidence when its reviewed source, scope, policy, environment and
tool/rule inputs remain applicable. At the next gate, rerun the invalidated checks
and their affected dependencies rather than every available audit. For unchanged
checks, record why their earlier results still apply to the new snapshot, retaining
the original reports and provenance. A commit-only transition can use verified
content equivalence; a new digest alone is never proof. The current assessment
must account for every required check before readiness/release. Unverified reuse
is incomplete evidence and must block, even when repeating a check would cost more.

## Use Trail of Bits proportionally

Research baseline: [Trail of Bits skills at `1e0cb77`](https://github.com/trailofbits/skills/tree/1e0cb77d071a8b9453391d111f17d34d2114e057),
observed 2026-10-23. The repository had no published GitHub releases; plugin
versions were listed individually in its marketplace. This immutable source
identifies the reviewed methods, not a claim that they are installed or executed.
Keep source, installation, client compatibility and actual execution distinct.

### Check Trail of Bits updates within each gate

At the start of each gate, check the official repository's latest non-prerelease
release. If no stable release exists, resolve its default-branch HEAD to an immutable
commit. Compare that source and applicable marketplace plugin versions with the
reviewed pinned revision and any installed versions. Record the lookup time,
source URLs and observed revisions. Reuse this lookup across checks, reviewers
and retries in the same uninterrupted gate run; a later gate or resumed run
refreshes metadata once. Do not poll or fetch the full catalog repeatedly.

If the relevant methods are unchanged, reuse their reviewed source and valid
evidence. If they changed, inspect only applicable instructions, scripts, rules,
dependencies, permissions, model assumptions and result semantics before adopting
an update. Pin the reviewed selection and record why it was adopted or deferred.
A newer version alone neither forces adoption nor requires a full audit. Updates
unrelated to the task do not invalidate its security evidence. An update exposing
missing or incorrect required coverage does: resolve that gap through a reviewed
update or equivalent scoped validation before accepting the gate.

Every tier requires a `trailofbits-update-review` evidence entry covering the
lookup, comparison, applicability/adoption decision and effects on reused checks.
For R0 or no applicable upstream method, record that decision after the lightweight
lookup; do not run an unnecessary scanner. An unavailable lookup without a valid
same-run observation, unreviewed relevant changes or unresolved coverage gaps
make this check incomplete and block gate acceptance. They do not block draft
implementation or withdrawal of READY. The helper checks the required entry's
outcome and fingerprint; the coordinator performs and verifies the upstream check.

Checking for updates is not permission to install them, enable tools or change
model, provider, reasoning, authentication, billing or permissions. Keep the
existing reviewed version when an update is incompatible unless equivalent
validation can meet the requirement within the user's authorized settings.

### Select applicable methods

| Change or finding | Applicable method; bounded scope |
| --- | --- |
| Ordinary behavior/refactor | `differential-review`: exact base/head or working snapshot, connected callers, history, tests and blast radius. R0 needs only its baseline impact/update checks. |
| Auth/configuration/secrets/security API | Deeper `differential-review`; `sharp-edges` for misuse-prone APIs; relevant `insecure-defaults` categories for fail-open settings, fallback secrets, credentials and debug exposure. |
| Parsers, encoders, state invariants | `property-based-testing` when meaningful invariants or round trips exist; reuse the project's test tools. |
| Dependency changes | Native ecosystem/lockfile audit; `supply-chain-risk-auditor` for supported dependency metadata and advisory coverage. |
| GitHub Actions invoking AI agents | `agentic-actions-auditor` for event input, prompt, permission and execution boundaries. |
| Supported language with relevant static-analysis rules | `static-analysis` (Semgrep/CodeQL/SARIF), using available tools and a recorded rule/scope selection. |
| Concrete suspected finding | `fp-check` to verify reachability, counterevidence and exploit preconditions; an unresolved finding remains blocking. |
| Known security defect and fix | `post-patch-validation` for baseline reproduction, patched behavior and regressions; `variant-analysis` for related instances of the root cause. |

Use the applicable installed, reviewed skill when compatible. If unavailable,
perform equivalent scoped native analysis/tests with explicit coverage and label
it an adaptation. Do not claim an upstream skill ran. If equivalence cannot be
established for a required check, mark coverage incomplete and block. Optional
methods may be inapplicable with reasons; required validation cannot be waived
merely because a tool is missing. No universal scanner stack or automatic plugin
installation is required.

Preserve model, provider, reasoning, authentication and permissions. Upstream
agent profiles, Claude-specific tool names and model choices are reference
material, not authority to switch settings. In this baseline, `insecure-defaults`
is a multi-agent command/workflow prescribing Sonnet/Opus; do not invoke it
unchanged under an inherited-settings constraint. Use its relevant categories
through compatible analysis instead. Keep all reviews read-only; use Git objects
or disposable roots when an upstream method suggests checking out a baseline.

Respect tool coverage and result semantics:

- The supply-chain collector supports npm, PyPI and Go with specific lockfile
  formats. It does not parse pnpm, Yarn or Poetry lockfiles in this baseline.
  Fallback latest-version metadata is not evidence for exact locked versions.
  External lookups need existing authorization; never send secrets or private
  source to an unapproved service, sign in, or change accounts implicitly.
- Semgrep's filtered findings mode still scans its selected rulesets. Record
  failed/skipped scans and rules, not merely an empty merged report. Do not
  silently install scanners, enable paid engines or broaden network access.
- `post-patch-validation` requires Git 2.36+, Python 3.11+, uv and project test
  prerequisites. Its isolated worktrees are not an OS sandbox. A `complete`
  assessment may contain failing findings: inspect findings, gaps and required
  human review. Neither `complete` nor an exit code alone supplies acceptance.
- `agentic-actions-auditor` covers AI GitHub Actions, not all CI systems.
  `variant-analysis` needs a known root cause; `fp-check` verifies findings rather
  than replacing discovery. Do not run these full workflows for every edit.

## Evidence and readiness

Stop writers and capture the lifecycle publication snapshot. Store redacted
reports outside tracked source. Reports identify the base/head or snapshot,
inspected files and callers, trust boundaries, risk rationale, selected checks,
tool/skill revision and commands, rules and exclusions, results, gaps, findings
and disposition. Record reviewer identity/independence and unresolved conditions.
An outcome is `passed` only after required coverage and finding resolution are
complete. Preserve failed evidence when replacing it with new results.

Add `security` to the existing event's `validation` object:

```json
{
  "snapshot": "<publication snapshot digest>",
  "risk": "R0",
  "rationale": "Only visible wording changed; inspected rendering and callers.",
  "status": "complete",
  "required_checks": ["impact-review", "trailofbits-update-review"],
  "checks": [
    {
      "name": "impact-review",
      "outcome": "passed",
      "path": "/private/task/security-impact.json",
      "sha256": "<SHA-256 of the evidence file bytes>"
    },
    {
      "name": "trailofbits-update-review",
      "outcome": "passed",
      "path": "/private/task/trailofbits-update-review.json",
      "sha256": "<SHA-256 of the update-review evidence file bytes>"
    }
  ]
}
```

All six fields are required. `status` is `complete` or `incomplete`; only
`complete` can pass. Check entries use the existing evidence shape and outcomes
`passed`, `failed`, `not_run`. Each required name needs exactly one entry; declare
additional project requirements by name. The risk tier sets the minimum names.
Both `impact-review` and `trailofbits-update-review` are required at every tier;
requests from older versions without the update-review entry cannot pass.
Generic checks and independent review still apply. The helper rejects missing,
malformed, stale, incomplete or nonpassing security evidence before READY,
including resumed/manual publication. It verifies file fingerprints and the
snapshot, not the truth of reports or whether the agent chose the right tier or
all applicable checks. The coordinator and independent reviewer own those judgments.
READY also rejects dirty files outside the explicit publication scope and requires
the committed checkout to be clean. This prevents checks against an uncommitted
connected caller from approving a different published version. Preserve unrelated
work; include and review it deliberately or validate in an isolated clean checkout.

Only aggregate security status and tier enter the generated PR section. Never
put private findings, paths, fingerprints or risk rationale in public fields.
Checkpoint/blocker/reopen events remain usable with absent or invalid security
evidence and report security pending. This permits honest progress and READY
withdrawal, not an exemption. Old READY requests without security evidence fail;
withdraw READY, retain old records, and use a fresh planned event/milestone with
current evidence. Do not rewrite an immutable event to retrofit acceptance.
Delivered-event `resume` remains cleanup reconciliation, not fresh readiness or
release validation. No historic receipt is a reusable release approval.

## Release preflight, including lifecycle opt-out

Validate a clean checkout of the exact release commit. Capture a new snapshot
after a commit or merge; a precommit READY digest is not the release digest.
Use explicit relevant file paths and the release scope in the impact report:

```sh
python3 -B /path/to/vibe-setup/workflow.py inspect /absolute/release --file src/changed.py
python3 -B /path/to/vibe-setup/workflow.py check-security /absolute/release < /private/task/release-security.json
```

The second command accepts exactly `files` (explicit relative paths), `snapshot`
(the inspected digest) and `security` (the object above bound to that digest).
It works without a task ID or enabled lifecycle. It is read-only, requires a clean
tracked/untracked checkout, and returns exit 0 with `security=passed` only when
the shared security gate passes; invalid evidence returns exit 3. Ignored build
outputs and external artifacts are not attested: build from the reviewed commit
and verify artifact provenance under the project's release policy.

Every Vibe-managed release must run this preflight and stop on nonzero or missing
results, alongside existing release checks and publication authority. Bind any
separate CI/deployment job to the exact revision and evidence before its publish
step. This package has no universal deployment runner and does not automatically
install branch protection or intercept arbitrary release commands. Instructions
plus helper invocation enforce this workflow; an external pipeline requires its
own explicit integration. No successful gate deploys, merges or grants approval.

New code, evidence, policy, tool/rules, environment or dependency/advisory changes
that affect the assessment require renewed validation at the next gate. Do not relabel an old
report with a new digest. Hash binding detects source/evidence changes; freshness
of external data and the meaning of reports remain review responsibilities.
