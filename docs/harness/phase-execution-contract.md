# Phase Execution Contract

Standard flow for future phase landings. Keep prompts short by pointing here.

1. Read `AGENTS.md` and `docs/harness/*`
2. Run baseline gates (`pytest -q` + relevant acceptance scripts + read-only remote/receipt checks)
3. Report baseline before editing
4. Add or update tests first
5. Implement the smallest code needed
6. Run acceptance
7. Record real mutations in the phase report (or confirm none)
8. Run sensitive-data scan on changed docs/reports
9. Commit when gates pass — **agent-owned** for implement/land/release tasks; never ask the owner “shall I commit?” or stall for commit permission (see `AGENTS.md` / `vibe describe` → `communication_contracts.git_land`)
10. Never push unless explicitly asked (or the task is an explicit release that includes push)

Do not invent sub-phases without a real blocker.
Do not treat accidental provider mutations as silent success.
