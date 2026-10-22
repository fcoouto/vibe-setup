# Native client qualification

Use the installed `workflow.py` for one bounded read-only canary in each requested
client. These commands prepare and evaluate evidence; they never run a model,
invoke a hook, change settings, or grant trust. Keep private JSON outside source
repositories and discoverable skill directories. Current native tool schemas and
actual client observations remain authoritative.

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
  "protected_files": ["/absolute/project/.codex/config.toml", "/absolute/project/.codex/hooks.json"],
  "display_required": true
}
```

Use the actual native tool's name and available fields. The helper rejects a tool
without top-level `task_name` and `message`, wrong host root, ambiguous guard,
invalid declaration or stale source. It emits `native_arguments` containing the
task name, one declaration pointer and the exact seven-field report skeleton.
It emits no model, reasoning, provider, authentication, permission or profile
override. Authentication is not read from credential stores.

When badges are required, start a bounded read-only Habblaud observer **before**
beginning the attempt. Record its start time. Observe real sessions; never create
synthetic hook events or rewrite native/Habblaud state.

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

```json
{
  "record_path": "/private/update/app-probe.json",
  "child_log": "/absolute/real-child-rollout.jsonl",
  "display_evidence": "/private/update/app-display.json",
  "dispatch_evidence": "/private/update/app-dispatch.json"
}
```

Omit `child_log` when the response is denied or uncertain. Reconcile the same
consumed attempt after locating evidence; never redispatch. Omit `display_evidence`
when unobserved: required display remains incomplete. Its observation has this
shape, with actual timestamps expressed as Unix seconds:

```json
{
  "client": "app",
  "parent_thread_id": "native-parent-thread-id",
  "child_thread_id": "actual-child-thread-id",
  "role": "Tester",
  "observed_label": "Tester",
  "observer_started_at": 1000.0,
  "observed_at": 1010.0,
  "source": "habblaud"
}
```

Some native clients encrypt message text in disk logs. Every visible dispatch field
must still match the prepared packet. For encrypted text, `dispatch_evidence` must
reference a separately attributed capture of the actual native tool call:
`call_id`, `tool`, `arguments`, `observed_via: "native-tool-call"`, and `source_ref`.
Use the native invocation's actual call ID, exact tool name and exact argument
object, and identify the native tool observation in `source_ref`. The capture
must match the prepared packet. Without it, encrypted text remains unverified and
the probe cannot pass. Do not derive a purported observed capture from the plan
alone. Plaintext logs need no separate capture.

Retain a bounded actual API/UI snapshot with the observation. `snapshot` may name
that supporting artifact. The display record is an external observation; Python
checks its correlation and timing, not whether a person truthfully observed UI.
The adapter fills only absent/null `agent_role`; any supplied value wins.

`execution_passed`, `protocol_passed`, `recovery_observed`, `settings_preserved`
and `display_passed` remain separate. A corrected invalid first report cannot
become a clean first-pass result. `complete` requires execution and first-pass
protocol, plus display when requested. Authentication remains `not_exposed`;
unchanged provider/permissions and absent overrides do not prove credential
identity. A worker's report alone never establishes client qualification.

`status-probe` reads the same record and checks applicability without another
dispatch. It verifies immutable evidence hashes and captured log prefixes while
allowing later appended events. A later parent turn can reconcile the original
consumed attempt; it cannot begin a stale prepared packet. Record the hashed probe
receipt under the matching root/client update outcomes.
Do not relabel CLI execution as App or VS Code, reuse another window's worker, or
treat installation, discovery, and execution as interchangeable evidence.
