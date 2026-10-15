# Phase 2 Acceptance Report

## Phase Goal

Establish a durable, repeatable acceptance baseline for Vibe Control v0.5 Phase 2:
config + desired corpus inventory + **degraded repo fallback query**, without NotebookLM
mutation or Beads task workflows.

## What This Phase Proves

- `.vibe/control.yaml` can be validated against the packaged template shape.
- Desired corpus includes active Specs and curated `include_extra` docs.
- Desired corpus excludes superseded Specs and dynamic plan/dashboard/archive paths.
- `knowledge query` returns degraded local search evidence over the desired corpus only.
- Missing / unused NotebookLM does **not** block repo fallback behavior.
- Thin skills remain routing guidance; mechanics stay in the CLI.
- No provider mutation commands are required for Phase 2 acceptance.

## Commands Verified

```bash
pytest -q
python acceptance/phase2/run_phase2_acceptance.py
python -m vibe_control --version
python -m vibe_control doctor --json
python -m vibe_control config validate --json          # cwd = fixture
python -m vibe_control knowledge inventory --json      # cwd = fixture
python -m vibe_control knowledge status --json         # cwd = fixture
python -m vibe_control knowledge query --question-file ... --json
```

## Acceptance Fixture

```text
acceptance/phase2/fixtures/migration-harness-mini/
  .vibe/control.yaml
  docs/project/spec-registry.yml
  docs/project/ACTIVE_SPEC.md
  docs/project/SUPERSEDED_SPEC.md
  docs/project/DECISION_LOG.md
  docs/program/plans/EXCLUDED_PLAN.md
  docs/phases/phase3/plans/EXCLUDED_PHASE_PLAN.md
  docs/dashboard/EXCLUDED_DASHBOARD.md
  docs/archive/EXCLUDED_ARCHIVE.md
```

Runner:

```bash
python acceptance/phase2/run_phase2_acceptance.py
```

## Spec Alignment

| Vibe Control v0.5 principle | Evidence in this phase | Status |
|---|---|---|
| Repository is SSOT | Fixture registry + inventory selects only authoritative active Specs | PASS |
| NotebookLM is derived read layer | Query/status never mutate NotebookLM; status keeps `synced=false` | PASS |
| Repo fallback works when NotebookLM unavailable | `knowledge query` always `mode=degraded` / `provider=repo` | PASS |
| Skills stay thin | Skill content tests require routing rules, not sync mechanics | PASS |
| No mutation by default | Acceptance uses read-only CLI; no add/delete/sync commands | PASS |
| Dynamic plans excluded from KB | Inventory/query exclude program/phase plans, dashboard, archive | PASS |

## Not Proved Yet

- NotebookLM sync / retry / rebuild / auth repair
- NotebookLM semantic QA equivalence
- Beads init / ready / claim / checkpoint / complete
- Spec publish commit/push automation
- Global install into `~/.agents`
- Git hooks / GitHub Issues / Projects / Jira / NotebookLM MCP

## Known Gaps

- Repo fallback is keyword search, not semantic retrieval.
- Phase 2 does not claim NotebookLM sync completeness.
- Task provider remains PATH-only stub (`bd`).
- Skills are packaged in-repo; not yet installed under `~/.agents/skills/`.

## Design Adjustment During Acceptance

Project root resolution now prefers the nearest ancestor containing
`.vibe/control.yaml` before falling back to git root / cwd. This makes nested
acceptance fixtures work inside the vibe-control checkout and matches the
product rule that repo policy lives beside the working tree being controlled.

## Next Phase Recommendation

Phase 3 should add a **dry-run-first NotebookLM sync status/plan** that:

1. compares desired corpus vs remote sources without mutation,
2. emits explicit sync/diff JSON,
3. keeps repo fallback as the degraded path,
4. still forbids source add/delete until an explicit later gate.
