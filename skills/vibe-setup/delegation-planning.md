# Delegation planning and measurement interface

Use this interface with the [difficulty policy](delegation-brief.md#difficulty-based-worker-selection).
The Coordinator supplies verified observations, inspects the result, dispatches
through the selected client's supported controls, and verifies the work. These
helpers make no model calls, change no settings, and write no records. Their input
files are observations, not host attestations or a replacement approval registry.

```sh
python3 -B /absolute/installed/vibe-setup/workflow.py plan-delegation /absolute/project < request.json > plan.json
python3 -B /absolute/installed/vibe-setup/workflow.py report-delegation /absolute/project < observation.json > report.json
```

Keep requests, plans, approvals and receipts in the existing private task/setup
record, outside Git. Each invocation accepts one JSON object on standard input
(64 KiB maximum); referenced evidence files have a 1 MiB limit. Unknown fields,
duplicate JSON keys and nonfinite numbers are rejected. Evidence references are
absolute existing regular files without symlink traversal. The project opt-in's
`authorization_ref` is a nonempty source reference, such as a scoped chat URI;
it is not required to be a machine-specific file in tracked configuration.

## Planning request

The required top-level fields are `task`, `coordinator`, `client`, `candidates`,
`budget`, `attempts` and `mode`. Optional fields are `manifest` and `recovery`.

| Object | Required fields |
| --- | --- |
| `task` | `task_id`, canonical `role`, nonempty `specialty`, `domain`, `language`, `dimensions`, `risk`, `checks`, `independent_review`, `delegation_reason`, `context_tokens`, `output_tokens`, `tools`, `source_ref`, `contract_ref`, `checks_ref` |
| `coordinator` | Actual `model`, `effort`, `provider`, `permissions`, `session_id` |
| `client` | `name` (`app` or `vscode`), `version`, actual spawn `tool`, `pairs`, `selection_supported`, `observation_supported`, `evidence_ref` |
| `budget` | `attempt_limit` (1 or 2), timezone-qualified ISO8601 `deadline`, positive `output_tokens` |
| Each `attempts` row | Unique `attempt_id`, `state`, original `request_hash` |

`dimensions` has exactly `reasoning`, `ambiguity`, `coupling` and `context`, each
containing an integer `rating` from 0 to 3 and a nonempty `reason`. `risk` is
`R0`, `R1` or `R2`; R2 imposes D2 minimum and independent review. `checks` and
`tools` are string lists. Token limits are positive integers. `permissions` is a
nonempty string or object describing the observed execution scope. Client pairs
are exact `{ "model": "observed-model-id", "effort": "supported-effort" }`
objects. The two client support fields and `independent_review` are booleans.

Attempt states are `failed`, `denied`, `canceled`, `running`, `uncertain`,
`completed` or `accepted`. A pending or completed worker needs reconciliation;
an identical attempted request cannot be replayed. Recovery needs a nonempty
`diagnosis`, `changed_variable` and `reason`. Planning does not reserve an attempt:
the Coordinator must persist immutable attempt identity before submission and
account for every denial, timeout and fallback in the shared task budget.

`mode` is `ordinary`, `evaluation` or `canary`. Missing policy opt-in preserves
inheritance. Missing verification, exhausted budgets or unresolved attempts keep
the task with the Coordinator. An empty candidate list is valid and selects no
new worker pair. It does not authorize an inherited fallback beyond existing limits.

## Candidates and qualification evidence

Each candidate requires `id`, `route` (`native` or `local`), `model`, `effort`,
`provider`, `version`, `authorization_ref`, `qualification_ref`, `tools`,
`context_limit` and `output_limit`. A native candidate must retain the Coordinator's
provider and have an exact supported pair. Provider, credentials, permissions and
global defaults are never changed to obtain a candidate.

Optional candidate fields:

| Field | Meaning |
| --- | --- |
| `expected_cost` | `{unit, total, evidence_ref}` for complete expected cost. Comparable units rank eligible candidates within the preferred route. Missing cost does not disqualify local execution. |
| `expected_seconds`, `timing_ref` | Measured duration estimate and supporting receipt. A candidate exceeding the explicit deadline is ineligible. |
| `local_status_ref` | Required for local candidates; current normalized plugin observations described below. |
| `avoid_local_ref` | Bounded measured-harm exception, with `reason: "measured_harm"`, exact `qualification_ref`, `evidence_ref` and `expires_at`. |

All qualification records require `state`, `binding`, `scope`, `expires_at`,
`review_ref`, `pilot` and `canary`. States are `not_assessed`, `pilot_only`,
`qualified` and `suspended`. Expiry timestamps need an explicit timezone.

`binding` contains exact `route`, `model`, `effort`, `provider`, `version`, `client`,
`client_version` and `tool`; local bindings also contain `runtime_digest`.
`scope` contains `role`, `specialty`, `domain`, `language`, assessed integer
`tiers`, `risks`, `context_tokens`, `output_tokens` and `tools`. A larger tier
does not implicitly certify a smaller one: list the assessed tiers explicitly.

Each pilot row requires unique `case_id`, unique SHA-256 `case_hash`, `category`
(`ordinary`, `boundary` or `failure`), `baseline`, `candidate`, `rescued`,
`critical_failure` and `evidence_ref`. The hash identifies frozen case inputs,
contract and checks. Qualification requires at least 12 distinct cases, at least
four per category, both outcomes `passed`, and both flags false. Each canary row
requires unique `task_id`, `outcome`, `rescued`, `critical_failure` and
`evidence_ref`: exactly ten accepted, unrescued, noncritical deliveries are needed.
The Coordinator verifies that receipts support these claims. The helper hashes
files for change detection; it does not authenticate their authors or rerun cases.

`local_status_ref` points to a normalized record with boolean `routing_enabled`,
`approved`, `assessment_passed`, `admitted`, `evaluation_path`; `expires_at`;
SHA-256 `runtime_digest`; and original plugin `approval_ref`, `assessment_ref`,
`admission_ref`. The first four gates must pass. Evaluation additionally needs
the plugin's authorized evaluation path. Copy observations from the installed
plugin's supported interface; Vibe cannot grant these approvals. Recheck admission
immediately before dispatch. Planning neither reserves capacity nor enables routing.

Evaluation and canary modes require an absolute `manifest` file with `mode`,
`candidate_bindings`, `authorization_ref`, `expires_at`, `max_calls`, `used_calls`,
`scope`, `case_refs`, `rubric_ref`, `stop_conditions` and boolean `disposable`.
`candidate_bindings` maps each candidate ID to its complete exact `binding`
object above, including client/tool versions and local runtime digest. An ID
cannot be retargeted to a different configuration under the same manifest.
Calls need remaining budget and matching scope. Canary requires `pilot_only`, a
passing pilot, review, at most ten calls, no failed/rescued existing cohort member,
and disposable R2 work. Suspended evaluation also requires `diagnosis_ref`.
These modes never grant ordinary qualification or automatic promotion.

## Executing a returned plan

Check `decision.route`, `candidate_id`, `reason` and `rejections`. Eligible local
candidates take priority. Native `overrides` contain exact `model`,
`reasoning_effort` and `fork_turns: "none"`; transfer them only to a compatible
native tool. Local execution uses the plugin's supported submission contract.
Declarations, file ownership and the existing seven-field worker report stay intact.

The returned plan binds the project root, policy, task, budget, attempt history,
client observations and evidence hashes. Save it unchanged. `plan_hash` detects
accidental edits, not malicious rewriting. Full-history forks may inherit settings;
they are not evidence that explicit selection succeeded. Use the separate
[native qualification probe](qualification.md) to test actual client controls.

## Reporting a result

Required request fields are `plan` (absolute saved-plan path), `observation` and
`measurements` (object or null). Changed plan evidence or a different project root
blocks reconciliation. `observation` requires `candidate_id`, `worker_id`, actual
`model`, `effort`, `provider`, `permissions`, `coordinator_after`, `outcome`, boolean
`rescued`, `evidence_ref` and `checks_ref`. `coordinator_after` has the same schema
as `coordinator`. Outcome is `accepted`, `failed`, `denied`, `canceled` or `uncertain`.
Unknown or mismatched worker/Coordinator settings are routing failures. A rescued
delivery can be accepted overall while `candidate_accepted` remains false.

Measurements require `unit`, boolean `matched`, `match_ref`, `expected_owners`
and `spans`. Units are `token_proxy`, `actual_currency`, `price_estimate` or
`runtime_seconds`; keep currency/rate basis consistent in the supporting receipts.
Expected owners must be exactly `baseline`, `candidate`, `investment`. Compare
identical inputs, contracts and checks with a frozen inherited baseline. To compare
delegation against direct Coordinator execution, run a separately authorized arm.

Each span requires `source`, `run`, `span`, `owner`, nonnegative `amount` (or null),
booleans `complete`, `exclusive`, `overhead_complete`, and `evidence_ref`. Optional
`kind` is `total` (default) or `component`. Supply authoritative complete totals
including coordination, validation, failures, retries and rescue. Record explicit
zero investment when none was allocated; omitted overhead is not zero.

Identical source/run/span receipts count once; conflicting receipts or multiple
whole-task totals per source/run fail closed. One complete total supersedes that
run's components. Components alone, incomplete usage or missing owners leave
savings unknown. The Coordinator must prevent overlap between independent sources
and maintain the cumulative ledger across reports; this helper deduplicates only
within one invocation. No implicit subscription billing conversion is performed.

For a matched accepted delivery, operating difference is baseline minus complete
candidate cost. Delivered net estimate subtracts allocated experiment investment;
negative values remain negative. In evaluation mode both arms are experimental
investment, and delivered savings are zero. A matched experiment may show an
operating difference but cannot count its trials as production savings. Report
end-to-end latency separately from summed runtime. Null measurements are valid
and produce `savings_claim: "unknown"`; qualification remains unchanged.
