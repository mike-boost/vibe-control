# Phase 11A — Superpowers Skill Comparison

**Status:** Review note / Not a product dependency  
**Date:** 2026-07-14  
**Purpose:** Bounded comparison of Superpowers skill patterns vs Vibe Control Phase 11A skill architecture.  
**Rule:** Do not copy Superpowers business logic. Adopt only patterns that fit skills + CLI.

---

## Decision summary

| Bucket | Items |
|---|---|
| Adopt / already have | front-door/bootstrap skill; mandatory workflow for confirmed flows only; narrow composable skills; TDD/verification before completion; evidence over claims; skill authoring/testing discipline; complexity reduction |
| Reject | multi-platform packaging; git worktree workflow; subagent-driven development as default; long autonomous run; skill-level business logic; direct provider calls from skills; external eval harness; many skills just because Superpowers has many |

---

## Comparison table

| Superpowers pattern | What it solves | Current Vibe Control equivalent | Decision | Minimal Vibe adoption | Overengineering to avoid |
|---|---|---|---|---|---|
| Bootstrap / front-door skill | Clears entry path; orders next skills | Phase 11A `vibe-control` front-door | **Adopt** | Package thin `vibe-control` router that sequences knowledge → reasoning → reconcile | Do not put provider logic in front-door |
| Mandatory workflow for known flows | Prevents agents inventing unsafe order | Phase 11A dogfood: knowledge readonly → agent reasoning → task reconcile --dry-run | **Adopt (confirmed only)** | Document one mandatory Phase 11A workflow | Do not hard-code unknown future workflows as mandatory |
| Narrow composable skills | Keeps skills focused | `vibe-knowledge` + `vibe-implementation` (+ front-door) | **Already have / keep** | Keep three skills max for now | Do not add 10+ skills |
| TDD / verification before completion | Reduces false “done” claims | harness + pytest gates + Test Spec IDs | **Already have** | Keep tests-first for phase slices | Do not add external eval harness |
| Evidence over claims | Forces CLI/JSON proof | JSON envelopes + status/reconcile reports | **Already have** | Require envelope evidence in closeouts | Do not treat chat memory as evidence |
| Skill authoring/testing discipline | Stable skill contracts | `tests/test_skills_content.py`, Phase 10.5/11A skill tests | **Adopt / extend** | Assert no direct NotebookLM/`bd`/`--apply` in skill docs | Do not grow skills into manuals |
| Complexity reduction | Avoids sprawl | Product model: skills thin, CLI deterministic | **Already have** | Prefer CLI modules over skill prose | Do not add frameworks for skill orchestration |
| Multi-platform packaging | Ships skills to many hosts | Repo package + `~/.agents/skills` symlink install | **Reject** | Keep current install model | No npm/marketplace multi-target packaging now |
| Git worktree workflow | Isolates parallel branches | Not part of Vibe V1 | **Reject** | None | No worktree automation skill |
| Subagent-driven development default | Parallelizes agent work | Not required for Phase 11A | **Reject** | None | No subagent workflow as default |
| Long autonomous run | Unattended multi-step execution | Explicit human gates for `--apply` | **Reject** | Keep fail-closed mutation gates | No long autonomous loop skill |
| Skill-level business logic | Puts domain rules in skill text | Forbidden by Phase 10.5 | **Reject** | Keep logic in CLI + tests | No reconcile algorithms in skills |
| Direct provider calls from skills | Bypass control layer | Forbidden (NotebookLM/`bd` via vibe CLI only) | **Reject** | Enforce in skill docs + tests | No raw provider calls |
| External eval harness | Scores agent runs | Local pytest/acceptance gates | **Reject** | Use existing gates | No new eval product in Phase 11A |
| Many specialized skills | Covers many niches | Two domain skills + one front-door | **Reject** | Stay at three packaged skills | Do not mirror Superpowers catalog size |

---

## Phase 11A implication

```text
Package vibe-control as front-door.
Keep vibe-knowledge / vibe-implementation narrow.
Mandatory workflow applies only to confirmed Phase 11A readonly dogfood.
Do not import Superpowers worktrees/subagents/autonomous loops.
```

---

**End of comparison note**
