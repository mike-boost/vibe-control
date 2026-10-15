# Feedback

Two different channels — do not confuse them:

| Channel | What | Spec |
|---|---|---|
| **GitHub Issues** (this doc, human) | Bug / feature requests to maintainers | below |
| **Experience feedback artifacts** (agent/owner) | Pain / owner dissatisfaction / bright spots / friction captured **in the consumer repo** | [`docs/project/vibe-control-feedback-spec.md`](project/vibe-control-feedback-spec.md) |

Experience feedback is **not** a task system. Analogy: OS crash reporter (stack + context bundle). Artifacts stay local; sharing with the Vibe team is **voluntary**. Always redact secrets.

---

## GitHub Issues (human)

Internal feedback for Vibe Control consumers via Issues:

- **Bug report** — something broken or blocked
- **Feature request** — missing capability (within product scope)

Templates live under `.github/ISSUE_TEMPLATE/`.

You may attach a **redacted** experience-feedback zip/YAML from the consumer repo (see feedback spec).

## Before filing an Issue

```bash
vibe --version
vibe doctor --json
```

Attach a **redacted** doctor JSON (or paste the relevant fields).

## Required fields (bugs)

- Vibe version (`vibe --version`)
- Install method (`install-user.sh` from tag, editable, other)
- OS / Python version
- Whether `components.knowledge.enabled` is true
- Whether `components.task.enabled` is true
- Redacted `vibe doctor --json` output
- Reproduction steps / expected vs actual

## Redaction — never attach

- Tokens, cookies, session material
- `.env` / secret files
- Raw notebook refs / private provider source IDs
- Account passwords or personal access tokens

If a field looks sensitive, replace with `[REDACTED]`.

## Out of scope for either channel

- Telemetry or automatic upload
- Using ChatGPT Project Sources as a product gate
- Asking maintainers to invent unsupported features (`sdd` / `tdd` / plugin frameworks) without a product decision
- Treating feedback artifacts as knowledge SSOT or Beads tasks

## Optional future / shipped thin CLI

Experience artifacts (consumer repo):

```bash
vibe feedback init-preview --json
vibe feedback draft --kind friction --title "…" --summary-file s.txt --attach-doctor --json
# review runtime/vibe-feedback/<id>/ — set redaction.confirmed: true
vibe feedback validate --path <id> --json
vibe feedback pack --path <id> --json   # local zip; share voluntarily
vibe diagnostics bundle --redacted --json   # local doctor+skills zip; never upload
```

See [`docs/project/vibe-control-feedback-spec.md`](project/vibe-control-feedback-spec.md).

Consumer repos: merge `templates/gitignore.consumer.example` (ignore `runtime/vibe-feedback/`).
