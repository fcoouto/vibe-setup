# Native hook and dispatch qualification

Use the installed `workflow.py` for one bounded read-only canary in each requested
client. These commands prepare and evaluate evidence; they never run a model,
invoke a hook, change settings, or grant trust. Keep private JSON outside source
repositories and discoverable skill directories. Current native tool schemas and
actual client observations remain authoritative.

The default upgrade checks trusted hook definitions/scripts, exact task identity,
explicit role/specialty, native child binding, observed reads, first report and
preserved settings. It requires no external service or display observer. Configured
hooks and disposable contract tests do not independently prove runtime hook
invocation; retain actual client hook evidence when available and state that limit
when it is unavailable. Neither result proves downstream delivery.

## Prepare before dispatch

Observe the current App or VS Code window/thread, exact harness root, runtime,
and one active project guard source. Record that observation privately as:

```json
{
  "client": "app",
  "thread_id": "native-parent-thread-id",
  "runtime": "observed-client-runtime",
  "harness_root": "/absolute/project",
  "observed_via": "native-ui",
  "hook_sources": [{
    "path": "/absolute/project/.codex/hooks.json",
    "sha256": "current-definition-sha256",
    "trusted": true,
    "scripts": {"/absolute/project/.codex/hooks/subagents.py": "reviewed-script-sha256"}
  }]
}
```

`observed_via` is `native-ui` or `native-app-tool`. These are attributed external
observations, not self-attesting Python checks. Retain the native UI/tool source
alongside the observation. An unchanged definition may reuse its exact existing
approval; current discovery still needs evidence. No direct trust-store edits.
An unresolved exclusion, stale discovery, or ambiguous accumulated guard stays
open in the update record. A CLI's `source=vscode` metadata alone does not identify
which desktop client performed the run.

Create the complete declaration at the **host thread's harness root**. Require a
canonical role, nonempty specialty, `read_only: true`, and `budget.attempts: 1`.
The guard contract supplies the other required fields. Limit the declared work to
reading that declaration and bounded public project text, such as README lines
1–20. Do not include secrets in the probe. Custom specialties remain **Not assessed**.

Pass this request to `workflow.py prepare-probe /absolute/project` on stdin:

```json
{
  "record_path": "/private/update/app-probe.json",
  "task_name": "app_update_canary",
  "parent_log": "/absolute/native-parent-rollout.jsonl",
  "client_context": "/private/update/app-context.json",
  "tool": {
    "name": "collaboration.spawn_agent",
    "fields": ["task_name", "message", "fork_turns"]
  },
  "read_paths": [{"path": "/absolute/project/README.md", "max_lines": 20}],
  "protected_files": ["/absolute/project/.codex/config.toml", "/absolute/project/.codex/hooks.json"]
}
```

Use the actual native tool's name and available fields. The helper rejects a tool
without top-level `task_name` and `message`, wrong host root, ambiguous guard,
invalid declaration or stale source. It emits `native_arguments` containing the
task name, one declaration pointer and the exact seven-field report skeleton.
By default it emits no model, reasoning, provider, authentication, permission or
profile override. Authentication is not read from credential stores. Existing
inherited probes and their receipts remain compatible.

### Qualify explicit worker selection

To test an authorized worker model/effort choice, add `worker_selection` to the
preparation request. Use exact pairs observed from the current native host, and
retain that observation with the approval reference in private evidence:

```json
{
  "worker_selection": {
    "model": "observed-worker-model",
    "reasoning_effort": "low",
    "authorization": "reference to the user's approval for this client probe",
    "supported_pairs": [
      {"model": "observed-worker-model", "reasoning_effort": "low"}
    ]
  }
}
```

The actual `tool.fields` must include `task_name`, `message`, `model`,
`reasoning_effort`, and `fork_turns`. The helper rejects an unsupported exact
pair, absent authorization, or missing native control. The returned packet sets
the selected `model` and `reasoning_effort`, with `fork_turns: "none"`. It changes
no Coordinator settings. Authorization and supported pairs are external
observations: validating their structure does not establish their truth, model
competence, or ordinary-work eligibility. The Coordinator verifies those sources.
Do not change the prepared selection, approval reference, inventory, or packet
after preparation; revalidation rejects inconsistent receipts.

For each requested client, choose a worker model and effort different from the
Coordinator to demonstrate both controls. A matching inherited default cannot
prove a change took effect. Use separate real App and VS Code attempts and retain
their actual originator, parent/child identities and runtime versions. Unsupported
client controls remain an explicit gap; CLI evidence is no substitute. This probe
qualifies dispatch controls only. Capability qualification and savings require
their own task evidence under the [delegation policy](delegation-brief.md).

`display_required` is optional and defaults to `false`. Standard upgrades omit
it and the update plan's `display` layer. Only an explicit user request for a
consumer display test adds that requirement. Read the [optional consumer guide](native-display.md)
for its observer and evidence contract; do not load it during ordinary upgrades.
For an already installed optional adapter, run its disposable contract tests to
check role precedence and binding without connecting to a consumer.

## Consume exactly one attempt

Call `workflow.py begin-probe /absolute/project` with:

```json
{"record_path": "/private/update/app-probe.json"}
```

This persists the consumed attempt before returning the exact native arguments.
Pass that object directly to the native tool in this client. Do not reconstruct
it from prose, omit its task name, or add execution overrides. An error, denial,
lost response or process restart never permits another `begin-probe` for that run.
The helper cannot intercept arbitrary tools outside its boundary; the existing
native guard remains independent protection. A new run requires fresh explicit
authorization, a new task/declaration identity and a new receipt.

## Reconcile actual evidence

Pass native parent/child rollout paths to `record-probe`; do not manufacture logs.
The parent stream is bound before dispatch. The evaluator checks its native calls,
child parent/name/root identity, settings, observed read output, first final report,
corrections, workspace preservation and protected hashes. Known mutation and extra
delegation tool events fail a read-only probe. This is evidence checking, not a
sandbox or proof against arbitrary concealed shell side effects. Inherited transcript history does not count as
child execution. It supports the package's tested Codex JSONL event shapes;
unrecognized layouts remain unqualified.

For a selected worker's fresh history, the native session metadata must bind the
child to the dispatched parent, task name, root and creation time. The first
child turn must match an earlier native `task_started` event, and no child turn
may reuse an observed parent turn identity. Evidence before that first child turn
does not count as child execution. Every child turn must retain the requested
model/effort and the Coordinator's provider and permission settings. Every
observed Coordinator turn after dispatch must preserve its original settings;
a temporary change followed by restoration still fails preservation.

```json
{
  "record_path": "/private/update/app-probe.json",
  "child_log": "/absolute/real-child-rollout.jsonl",
  "dispatch_evidence": "/private/update/app-dispatch.json"
}
```

Omit `child_log` when the response is denied or uncertain. Reconcile the same
consumed attempt after locating evidence; never redispatch. Default qualification
uses native logs and the dispatch capture only. No consumer observation is needed.

Some native clients encrypt message text in disk logs. Every visible dispatch field
must still match the prepared packet. For encrypted text, `dispatch_evidence` must
reference a separately attributed capture of the actual native tool call:
`call_id`, `tool`, `arguments`, `observed_via: "native-tool-call"`, and `source_ref`.
Use the native invocation's actual call ID, exact tool name and exact argument
object, and identify the native tool observation in `source_ref`. The capture
must match the prepared packet. Without it, encrypted text remains unverified and
the probe cannot pass. Do not derive a purported observed capture from the plan
alone. Plaintext logs need no separate capture.

`execution_passed`, `protocol_passed`, `recovery_observed`, `settings_preserved`,
`selection_verified`, `coordinator_settings_preserved`, and `display_passed`
remain separate. `requested_worker_settings` and `observed_worker_settings` expose
the expected settings and every observed child turn's settings. For inherited
probes, `selection_verified` is always false. For explicit selection it requires
the exact dispatch, bound child, matching settings and unchanged Coordinator;
it does not imply successful work, valid report protocol, or model competence.
`settings_preserved` means all worker settings match the expected inherited or
explicitly selected settings. A corrected invalid first report cannot
become a clean first-pass result. `complete` requires execution and first-pass
protocol; optional display also gates completion only when explicitly requested. `display_passed: false`
means unobserved when no display was requested, not an upgrade failure. Omit
unrequested display results from user-facing upgrade reports.
Authentication remains `not_exposed`; unchanged provider/permissions and absent
overrides do not prove credential identity. A worker's report alone never
establishes client qualification.

`status-probe` reads the same record and checks applicability without another
dispatch. It verifies immutable evidence hashes and captured log prefixes while
allowing later appended events. A later parent turn can reconcile the original
consumed attempt; it cannot begin a stale prepared packet. Appended Coordinator
or worker settings drift invalidates cached preservation and selection evidence
even after restoration. Matching appended worker turns remain valid. Legacy
inherited and selected-worker receipts retain their exact original packets,
including the former display-related report wording; status checks never rewrite
those receipts. Record the hashed probe receipt under the matching root/client
update outcomes.
Do not relabel CLI execution as App or VS Code, reuse another window's worker, or
treat installation, discovery, and execution as interchangeable evidence.
