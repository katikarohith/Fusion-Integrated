# Employee Leave Management (ELM) integration

## What this adds

ELM is a Fusion module registered as `leave_elm` at `/leave`, with API routes under
`/api/v1/elm/`. Its server-owned `registry.py` supplies the module navigation and permission
manifest. The client uses a static lazy import in `client/src/app/registry.ts` and page routes in
`client/src/modules/elm/routes.tsx`.

The module owns its leave records and accounting tables. It stores IAM user identifiers as scalar
IDs and does not add cross-module foreign keys. Directory reads use the approved
`modules.directory.contracts` interface. The ELM domain rules are pure Python; read scoping lives
in selectors and all writes go through transactional services.

## Requirements and implementation map

| Requirement area | Implementation |
|---|---|
| Category eligibility, counting, overlap, half-day CL, vacation windows, year-end arithmetic | `modules/elm/domain/leave_rules.py`, `services/leave.py`, `services/year_end.py` |
| Leave balances, reservations, postings, reversals, append-only account history | `services/accounts.py`, `models.py` |
| Substitute consent, decline recovery, sequential authority decisions, self-approval guard | `services/workflow.py`, `services/leave.py` |
| Cancellation, extension, resumption, offline synchronization | `services/leave.py`, `services/policy.py` |
| Current policy, employee context, routes, published calendars, SLA thresholds | `services/policy.py`, `services/sla.py` |
| Scoped reads and authorization at the API boundary | `selectors/leave.py`, `api/views.py`, `registry.py` |
| Employee request, status, balance, history, and workflow pages | `client/src/modules/elm/pages/` |
| Administrator configuration and maintenance | `client/src/modules/elm/pages/AdminPage.tsx` |
| Source specifications supplied with the assignment | `source-specs/` (copied without edits) |

The migration seeds the baseline category policies stated in the supplied business rules: CL 8,
RH 2, SCL up to 15, non-faculty EL 30, eligible COL 20, and faculty VL 60. Converted faculty EL
is retained as a zero annual entitlement policy so the account can receive the specified VL-to-EL
credit and later be used. The migration intentionally creates no routes or calendar rows because
those require current institutional authority assignments and the current Academic Calendar.

## Instance setup required

Before opening the module to employees, a Leave Administrator must configure current routes and
employee organizational context, then create and publish each required calendar with restricted
holidays and vacation periods taken from the approved Academic Calendar. Missing policy, calendar,
or route configuration causes the application workflow to fail closed. SLA thresholds are
configurable and reminders/escalations are processed with `process_elm_sla`; annual account
processing runs with `process_elm_year_end YYYY` after the year closes.

The target repository does not expose an Academic Calendar or organizational hierarchy through
the directory contract. The current implementation therefore uses an audited ELM calendar snapshot
and explicit route/profile configuration. ELM also has no attendance domain contract; resumption
updates ELM's leave period and balances, but attendance synchronization remains an integration gap.

## Attribution and model-trial evidence

The specification markdown files in `source-specs/` are unchanged files from the user-supplied
`ELM_MODEL_1` assignment bundle. The source project did not contain an explicit license file in
the inspected project root. No source code was changed to conceal provenance; this integration is
adapted to Fusion's server, IAM, and frontend conventions.

The source `.aider.model.settings.yml` declares `ollama_chat/qwen2.5-coder:7b` and a context size
of 12,288 tokens. That is configuration evidence only. No model invocation log, quantization tag,
hardware record, or trial result was present in the reviewed source records, so the exact runtime
model build and quantization are unverified. This repository's integration and validation work is
separate from the source project's reported model trial.

## Validation notes

Backend and frontend checks are recorded in the integration task report. Migration consistency
must be checked after applying the generated migrations to the configured database. The client
requires dependencies from `client/package-lock.json` before TypeScript, lint, build, and Vitest
checks can run.
