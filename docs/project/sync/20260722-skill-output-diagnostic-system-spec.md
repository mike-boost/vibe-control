# Design — Skill output diagnostic system (Path B) + triage feedback loop

**Status:** Superseded (2026-07-22) by `docs/project/sync/20260722-skill-assay-spec.md`
**Date:** 2026-07-22
**Document type:** Historical draft (Path B) — do not implement
**Audience:** owner + coding agents
**Language:** Explanation in Chinese where helpful; schemas / commands / field names in English.

> **Superseded:** Renamed to **Skill Assay / `skill-assay`**, separated from `vibe skills` install,
> orchestrator-collected evidence, typed checks only, two-stage finalize. See the accepted spec.

**Related:**
- Self-grill contract: `docs/project/sync/20260721-agent-self-grill-comm-contract.md`
- Self-grill loop design: `docs/project/sync/20260721-self-grill-session-loop-design.md`
- Grill session code: `src/vibe_control/grill_session.py`
- Knowledge local FTS spec (house style reference): `docs/project/sync/20260721-knowledge-local-fts-provider-spec.md`
- Spec / product model: `docs/project/vibe-control-spec.md`
- Owner plain language: `docs/harness/owner-plain-language-contract.md`

**Owner stance gate:** This is **Path B** (a generic adapter tool for any skill: diagnose first; repair/strengthen later). Path A (absorb skill determinism into vibe-control CLI) is **not** the default growth path — owner does not want vibe-control to bloat and lose its center. A companion **triage skill** gates whether any skill's deterministic part should ever be promoted into vibe-control.

---

## 0. One-line verdict

```text
Add a host-agnostic diagnostic system that, for any skill, runs the skill N independent
times in a target host, collects structured execution traces, diffs them against the
skill's declared output contract, cross-checks gaps against a vibe-owned host capability
matrix + current official docs, and emits a structured diagnosis envelope.
A companion triage skill consumes diagnosis evidence to re-decide what stays prose vs what
should be promoted to CLI — closing the loop without bloating vibe-control's core.
```

This is a **measurement / diagnosis** mechanism. It does **not** mutate skills, does **not**
mutate hosts, and is **not** a closeout / product_ready gate. It is the same receipt class
as grill / feedback: local, gitignored, not SSOT.

---

## 1. Problem

1. A skill that behaves well in one host (e.g. codex) may produce bad output in another
   (e.g. github copilot, cursor). The drift is real but invisible: owners feel "worse"
   without a measurable gap.
2. The host runtime is a black box: vibe-control cannot read the host's internal reasoning,
   truncation, or tool-call fidelity. "Expose the black box" is impossible from outside.
3. What **is** possible: measure the **differential** — run the same skill across hosts,
   compare structured traces, surface the gap. The gap is the visible evidence of drift.
4. Owners do not want vibe-control to absorb every skill's determinism (Path A by default),
   because that bloats the product and dilutes its center. We need a gate, not a vacuum.

---

## 2. Non-goals (locked)

- Not a skill mutator. No auto-rewrite of skills (repair / strengthen are future, out of v1).
- Not a host introspector. We do not read host telemetry or internal logs.
- Not a closeout / product_ready / ask_clean gate.
- Not a second readiness engine. Not a parallel control plane.
- Not a prose "skill doctor" skill that reads other skills and gives prose advice
  (that would itself drift across hosts — explicitly rejected).
- Not a quality judge without an external anchor. No self-grading loop.

---

## 3. Concepts

| Id | Meaning |
|---|---|
| `skill_id` | The skill being diagnosed (its name / path). |
| `host_id` | The host runtime the agent ran in for a trace (e.g. `codex`, `cursor`, `copilot`, `claude`). Agent self-reports; not verified by vibe-control. |
| `contract` | The skill's declared output shape + acceptance probes (optional sidecar). |
| `trace` | One structured record of one execution of the skill, written by the agent via a vibe command. |
| `run` | One independent execution that produces one trace. |
| `batch` | N independent runs of the same skill in the same host (default N=3). |
| `stability` | Per-field agreement across a batch's traces (stable / unstable / absent). |
| `matrix` | vibe-owned host capability matrix (data file): known limits per host. |
| `diagnosis` | The final envelope: contract vs actual gaps + stability + matrix hypotheses + doc citations + next_actions. |
| `triage` | Companion skill that consumes diagnosis evidence to recommend prose-vs-CLI split. |

---

## 4. Decisions locked (for review)

| ID | Decision | Value |
|---|---|---|
| D1 | Default run count | **N=3**, configurable (2..5). Independence required (see D3). |
| D2 | Independence enforcement | Each run in an **isolated worktree / fresh session**, no shared context. Reuse best-of-n runner / worktree skill. |
| D3 | Stability semantics | Field stable if all runs agree; unstable if disagree; absent if missing. Unstable fields are flagged, not averaged. |
| D4 | Contract location | Optional sidecar `skill.vibe.yaml` next to `SKILL.md` (or front-matter). No contract => generic trace only, no conformance diff. |
| D5 | Host capability matrix | vibe-owned data file `data/host-capability-matrix.yaml` (in package). Maintained, versioned, dated. |
| D6 | Official docs lookup | Prefer ctx7 when the host has a resolvable library id; else fetch official docs; always record doc version + fetch date. Never trust training memory. |
| D7 | Receipts | Local, gitignored under `runtime/vibe-skill-diagnose/`. Not SSOT. Same class as grill / feedback. |
| D8 | New CLI surface | Minimal: one subcommand group `vibe skill` with `diagnose` (and `trace` for per-call write). No new top-level capability plane. |
| D9 | Triage ownership split | The **rubric** (what counts as deterministic vs interpretive) is a vibe-owned doc. The **triage skill** (applies the rubric) is an external installable skill, thin, not in vibe-control repo. |
| D10 | Feedback loop | Diagnosis evidence is an optional input to triage re-evaluation. Triage may recommend promoting a repeatedly-drifting prose part to CLI. Promotion is owner-approved, not automatic. |
| D11 | Confabulation honesty | Agent self-narration is not ground truth. The stability layer (D3) is the honesty mechanism: we surface uncertainty, we do not average lies into false confidence. |
| D12 | No quality-judge LLM | v1 has no LLM-as-judge of "quality". Conformance + probes + stability + matrix + docs only. Quality judgment without an anchor escalates to owner. |

---

## 5. Skill output contract (sidecar)

Optional. A skill author declares what "correct output" means so the diagnosis can diff.

```yaml
# skill.vibe.yaml (next to SKILL.md)
schema: vibe.skill.contract.v1
skill_id: my-skill
output:
  shape:
    # JSON schema fragment or reference; the fields the agent must produce
    required_fields:
      - id: thesis
        type: string
      - id: steps
        type: array
      - id: evidence_paths
        type: array
  acceptance_probes:
    # CLI commands whose exit code / JSON = pass/fail; host-independent
    - name: evidence_exists
      command: "test -f ${artifact}/evidence.json"
    - name: envelope_ok
      command: "vibe envelope check --artifact ${artifact} --json"
  notes: "produced artifact path is passed via --artifact"
```

If absent, diagnosis runs in **generic mode**: collect traces, compute stability, cross-check
matrix, but no conformance diff and no probes.

---

## 6. Trace record (per call)

The agent writes one trace per run via `vibe skill trace`. The **format is CLI-enforced**
(host-independent); the **content is agent self-narration** (host-dependent, may confabulate).

```yaml
schema: vibe.skill.trace.v1
trace_id: trace-...
skill_id: my-skill
host_id: copilot          # agent self-reports
run_index: 0              # 0..N-1 within the batch
received:
  skill_loaded: true      # agent's claim that it saw the skill content
  truncation_suspected: false
  perceived_instructions: "..."   # short summary of what the agent thought it was asked to do
executed:
  steps:                  # ordered, what the agent actually did
    - "read contract"
    - "produced artifact"
  deviations: []           # where it believes it deviated from the skill
produced:
  artifact_path: runtime/vibe-skill-diagnose/artifacts/<trace_id>/
  fields_present: [thesis, steps, evidence_paths]
  fields_absent: []
self_reported_issues: []   # agent's own list of friction / host limitations it hit
written_at: ...
```

**Honesty caveat (D11):** `received.skill_loaded=true` is a claim, not verified truth. If the
host truncated the skill, the agent may not know it is missing something. This is why we run
N independent runs and rely on stability, not on a single self-report.

---

## 7. CLI surfaces (thin)

| Command | Role | Auto-run? |
|---|---|---|
| `vibe skill trace --skill <id> --host <id> --artifact <path> --json` | Agent writes one trace record (local file) | yes (local write) |
| `vibe skill diagnose --skill <id> --host <id> [--runs 3] --json` | Orchestrate N independent runs, collect traces, compute stability, run conformance + probes, cross-check matrix + docs, emit diagnosis envelope | yes (readonly + local writes; isolated worktrees) |
| `vibe skill diagnose --report <diagnosis_id> --json` | Re-read a stored diagnosis | yes (readonly) |

No mutation of skills, hosts, or provider state. `diagnose` spawns isolated runs via the
existing best-of-n runner / worktree machinery; it does not run in the live chat context.

---

## 8. Diagnosis envelope

```yaml
schema: vibe.skill.diagnosis.v1
diagnosis_id: diag-...
skill_id: my-skill
host_id: copilot
runs: 3
contract_present: true

conformance:
  ok: false
  gaps:
    - field: evidence_paths
      expected: array
      actual: absent
      severity: high
    - field: thesis
      expected: string
      actual: present
      severity: none

probes:
  - name: evidence_exists
    pass: false
  - name: envelope_ok
    pass: true

stability:
  stable_fields: [thesis, steps]
  unstable_fields: [evidence_paths]   # present in run 0, absent in runs 1,2
  absent_fields: []

matrix_hypotheses:
  - cause: "copilot tool-call fidelity: structured array outputs drop on long artifacts"
    evidence: "evidence_paths unstable + absent in 2/3 runs"
    matrix_ref: "host-capability-matrix.yaml#copilot.tool_call_fidelity"
    confidence: medium
    action: "consider shorter artifact or chunked emission"

doc_citations:
  - host: copilot
    doc_version: "2026-07"
    fetch_date: "2026-07-22"
    source: ctx7 | official_docs
    ref: "..."
    relevance: "supports tool-call fidelity hypothesis"

next_actions:
  - CONTINUE_TRIAGE_WITH_EVIDENCE   # feed this diagnosis to the triage skill
  - OWNER_DECISION_on_quality       # quality judgment without anchor -> owner

loop_status: EXHAUSTED | BLOCKED_ON_LIVE | OWNER_DECISION
```

---

## 9. The feedback loop (diagnosis -> triage)

This is the relationship the owner sensed: **triage is design-time split, diagnosis is
runtime measurement, and diagnosis feeds back into triage.**

```text
triage skill
   |  applies vibe-owned rubric
   v
prose-vs-CLI split for a skill
   |
   v
skill runs in host X  --(N independent runs)-->  diagnosis envelope
   |
   v
diagnosis evidence (which prose parts drift, how badly, across which hosts)
   |
   v
triage re-evaluation:
   - prose part drifts hard + cross-host  -> recommend promote to CLI (owner-approved)
   - prose part stable cross-host         -> keep as prose
   - grey area                            -> OWNER_DECISION
   |
   v
(loop)
```

**Promotion is never automatic.** Triage only **recommends**; any promotion of a skill's
deterministic part into vibe-control CLI requires owner approval (consistent with the
"don't bloat vibe-control" stance). Diagnosis is evidence; triage is recommendation; owner
is the gate.

---

## 10. Triage companion skill (external, thin)

Not in vibe-control repo. Installable skill, e.g. `skill-triage`.

- **Owns nothing deterministic.** It reads the vibe-owned rubric doc and a diagnosis envelope,
  and emits a recommendation envelope.
- **Rubric is vibe-owned** (`docs/harness/skill-determinism-rubric.md`, new): defines what
  counts as deterministic/verifiable (candidate for CLI) vs interpretive (stays prose) vs
  grey (owner decision). This is the only new vibe-controlled artifact for triage — a doc,
  not a capability plane.
- **Recommendation envelope:**

```yaml
schema: vibe.skill.triage.v1
skill_id: my-skill
based_on_diagnosis: diag-...
parts:
  - part: "output shape enforcement"
    verdict: promote_to_cli_candidate
    evidence: "conformance gap on shape, stable across hosts"
  - part: "creative framing of thesis"
    verdict: keep_prose
    evidence: "interpretive, stable"
  - part: "evidence path emission"
    verdict: owner_decision
    evidence: "unstable cross-host; may be host bug or skill bug"
next_actions:
  - OWNER_REVIEW_promotion_candidates
```

---

## 11. Honesty boundaries (must be communicated to owner)

1. **Black box stays black.** vibe-control cannot see inside the host. We expose the
   **differential** (gap across hosts), not the host's internal truth.
2. **Agent self-narration can confabulate.** The stability layer surfaces uncertainty; it
   does not convert lies into truth. A field stable across 3 runs is more trustworthy, not
   proven true.
3. **Matrix and docs can be stale.** The host capability matrix is maintained by hand and
   can drift from reality; doc citations record version + date so staleness is visible.
4. **No quality judge in v1.** Without an external anchor (probe / owner), "is this output
   good?" escalates to owner. We do not run an LLM-as-judge and call it satisfied.

---

## 12. Scope discipline (anti-bloat)

- vibe-control gains: one CLI group `vibe skill` (trace + diagnose), one data file
  (host capability matrix), one doc (determinism rubric), local receipts. Nothing else.
- vibe-control does **not** gain: skill mutation, host introspection, an LLM judge, a new
  readiness engine, or absorbed skill logic.
- The triage skill lives outside vibe-control. Promotion of any skill part into the CLI is
  owner-approved and case-by-case, never default.

---

## 13. Open questions (for review)

1. Is `vibe skill` the right top-level group, or should it nest under an existing surface to
   avoid a new plane (e.g. `vibe grill skill`)? Owner preference?
2. Default N=3 acceptable, or owner wants N=5 for higher confidence at 5x cost?
3. Host capability matrix: maintain in repo (`data/`) vs docs (`docs/harness/`)? Affects
   whether it ships in the package.
4. Should diagnosis be openable as a grill-style session (with `loop_status` and a prompt
   exit gate), or stay a one-shot report? v1 leans one-shot; session mode is a possible v2.
5. ctx7 may not resolve host product docs (copilot/cursor are not libraries). Acceptable to
   fall back to official docs fetch with version+date recorded?

---

## 14. Implementation slices (if accepted)

1. `vibe skill trace` + trace schema + local receipts.
2. `vibe skill diagnose` orchestration: N isolated runs via best-of-n runner, trace collection.
3. Stability computation + conformance diff + acceptance probes.
4. Host capability matrix data file + matrix hypothesis generation.
5. Doc citation lookup (ctx7 first, official docs fallback).
6. Diagnosis envelope + storage + re-read.
7. Rubric doc `docs/harness/skill-determinism-rubric.md`.
8. Companion triage skill (separate repo / installable) consuming diagnosis envelopes.
9. Tests: trace schema, stability math, conformance diff, matrix hypothesis, independence
   enforcement, honesty-boundary labels present in envelope.
