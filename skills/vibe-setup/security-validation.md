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
| R1 | Ordinary behavior changes or refactors without a sensitive boundary change. | R0 checks plus `security-validation` and `security-coverage`: focused diff/caller review, relevant negative or regression cases, and the structured coverage record below. |
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

## Required coverage record

For R1 and R2, include `security-coverage` in both `required_checks` and `checks`.
Its fingerprinted file must be a UTF-8 JSON record with exactly `schema_version`
(integer `1`), `snapshot` (the assessment digest), `files` (every declared
publication/release path, without duplicates), and `areas`. Old R1/R2 records
without this entry cannot authorize a new READY or release. R0 keeps its existing
impact/update requirements; do not classify executable instructions as R0 to avoid
coverage. Draft, blocker and withdrawal events remain available.

`areas` must contain exactly the seven names below. Each value has exactly
`status`, `summary` and `evidence`. Status is `covered`; only `history` and
`callers` may use `not_applicable`, supported by evidence of the inspected scope.
Missing tools, unexamined paths and unavailable history are incomplete coverage,
not non-applicability. A new entrypoint can lack prior history, but its callers,
configuration, invocation and trust boundaries still need examination.

| Area | Required review and retained evidence |
| --- | --- |
| `scope` | Exact base/head or working snapshot, all changed files, connected code, risk, trust boundaries and explicit exclusions. Explain content-equivalent reuse after commit/merge; a refreshed digest alone is insufficient. |
| `methods` | Each selected upstream method and immutable revision; installed upstream execution or native adaptation; map applicable method steps to concrete evidence. Explain exclusions and gaps. Do not label an adaptation fully equivalent when relevant upstream steps are missing. |
| `history` | Baseline blame/log for removed or weakened protections and pertinent introducing/fix commits. Check reintroduced code against prior fixes. Record commands, inspected ranges, conclusions and limits; current diff inspection alone is insufficient. |
| `callers` | Enumerate affected symbols or instruction entrypoints and their direct caller identities/counts. Trace relevant transitive, CLI, configuration and dynamic invocation paths. Separate production/test callers and same-named functions in different modules. Record search scope, exclusions and unresolved dynamic reach. A count alone is not analysis. |
| `tests` | Map changed behavior and security boundaries to concrete positive/negative cases and observed results. Preserve failing-before/passing-after proof for defects, skipped/failed coverage and its disposition. Reused logs retain original source/environment bindings. |
| `adversarial` | Concrete attacker or mistaken-caller goal, preconditions, steps, impact, defended boundary and corresponding test/review evidence. Include races and partial failures when relevant. |
| `execution` | State precisely which claims are static review, deterministic fixtures, instruction scenarios, installation, discovery or actual-client execution. Required runtime claims need an observed client/session/version and actual tool outcomes; a fixture cannot substitute. Record limits, supported reuse and pending client actions. |

Each summary is nonempty text of at most 8192 characters without NUL. Each area
references 1–32 supporting evidence entries using the existing exact
`name`, `outcome`, `path`, `sha256` shape. Outcomes must be `passed` and fingerprints
must match canonical local files. The coverage record cannot reference itself.
A shared detailed report can support several areas when it actually covers each;
seven aliases to an assertion such as “reviewed” are not substantive evidence.
Keep reports and source excerpts private, outside tracked files.

The record is limited to 64 KiB. For example, this complete structure uses a
shared detailed report; replace all illustrative values with observed evidence:

```json
{
  "schema_version": 1,
  "snapshot": "<current assessment digest>",
  "files": ["src/guard.py", "tests/test_guard.py"],
  "areas": {
    "scope": {"status": "covered", "summary": "Exact base/head, files and trust boundaries: report section 1.", "evidence": [{"name": "scope", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]},
    "methods": {"status": "covered", "summary": "Pinned method-step mapping and native adaptation limits: section 2.", "evidence": [{"name": "methods", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]},
    "history": {"status": "covered", "summary": "Baseline blame and prior fix comparison: section 3.", "evidence": [{"name": "history", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]},
    "callers": {"status": "covered", "summary": "Named callers, counts and transitive reach: section 4.", "evidence": [{"name": "callers", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]},
    "tests": {"status": "covered", "summary": "Boundary cases, commands, outcomes and regression proof: section 5.", "evidence": [{"name": "tests", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]},
    "adversarial": {"status": "covered", "summary": "Attack preconditions, steps and defended outcomes: section 6.", "evidence": [{"name": "adversarial", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]},
    "execution": {"status": "covered", "summary": "Observed execution layers, required runtime claims and limits: section 7.", "evidence": [{"name": "execution", "outcome": "passed", "path": "/private/security-review.json", "sha256": "<report SHA-256>"}]}
  }
}
```

The helper checks this structure, scope/snapshot binding and every nested
fingerprint again at existing readiness/recovery gates. It cannot establish the
truth of summaries, exhaustive caller discovery or reviewer competence. The
coordinator verifies the source material; the independent R2 reviewer checks all
seven areas, method equivalence, exclusions and reuse against the actual diff.
A valid JSON record with inadequate substantive coverage must still block.
No new scanner, model, permission, background audit or trigger is introduced.

### Close historical gaps without rewriting history

Retain original reports, failed checks and immutable lifecycle requests. Add a
separately dated retrospective report bound to the original base/head and actual
source hashes. Record newly performed history/caller analysis and negative checks
as new evidence; never assert they ran at the old gate. Distinguish a historical
finding later fixed/superseded from a current unresolved defect. Inspect relevant
fix provenance before reusing the later resolution. Missing old execution logs
remain unknown; rerun a bounded current client case only when that runtime claim
is required and authorized. A retrospective report is not a fresh release approval.
For a new gate, build a current coverage record and use a fresh READY event with
all existing gates; do not retrofit the old event or silently grant legacy records
an exemption. Preserve the original snapshot and reports when rebinding proven
content-equivalent evidence.

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
additional project requirements by name. The risk tier sets the minimum names, including `security-coverage` for R1/R2.
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
withdraw READY, retain old records, and use a fresh `ready` event in an existing
planned milestone with current evidence. Readiness transitions do not consume the
routine checkpoint budget. Do not rewrite an immutable event to retrofit acceptance.
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
