# Knowledge Provider Boundary

## Format limits (per active provider)

Knowledge is one capability with two providers. **Allowed upload/index formats
follow the active `knowledge.provider`:**

| Provider | Allowed (v1) |
|---|---|
| `local_fts` | `.md` / `.markdown` / `.txt` only (UTF-8 text + markdown chunking) |
| `notebooklm` (Gemini Notebook) | Google upload tip set: documents (pdf/txt/md/docx/csv/pptx/epub), common images, common audio/video — see `format_policy.NOTEBOOKLM_EXTENSIONS` |

Unsupported paths stay in the repo inventory but are **skipped** on sync/index
(`skip_unsupported_format` / `format_skipped` warnings). Do not pretend the two
providers accept the same formats.

Code: `src/vibe_control/knowledge/format_policy.py`.

## Purpose

Keep NotebookLM / local_fts (and future providers) quirks out of skills and generic workflow logic.

## Provider-neutral layer owns

- desired corpus
- `doc_id`
- `content_sha256`
- `managed_name`
- `upload_filename`
- source instance lifecycle
- sync-preview operation model
- receipt schema
- verification result
- JSON envelopes

## Provider-neutral layer must not

- directly invoke `notebooklm` CLI command syntax
- hard-code NotebookLM source wait / rename behavior
- embed NotebookLM source ID formats
- resolve NotebookLM notebook refs / auth commands
- leak provider workarounds into skills

## local_fts provider owns

- SQLite FTS5 index path / schema / trigram+LIKE query
- heading/section chunking with Read-aligned line numbers
- index fingerprint vs DesiredSnapshot
- doctor sqlite version / FTS5 probes
- text-only format gate (`.md` / `.markdown` / `.txt`) before index rebuild

## NotebookLM provider owns

- notebook alias / ref resolution
- `source add` / `list` / `get` / `wait` / `rename` details
- NotebookLM status field mapping
- title fallback after file upload
- auth / doctor / login probes
- Gemini Notebook format gate before upload (documents / images / AV allowlist)

## Skills layer

Skills remain thin intent routers to `vibe` CLI commands.

Skills must not explain or implement:

- NotebookLM rename workarounds
- receipt internals
- source wait internals
- provider source IDs

## Ask hygiene (see also knowledge-ask-hygiene-contract.md)

- `synced` alone does not mean provider-backed ask is clean.
- Clean ask requires `synced` + `required_updates_count=0` + `cleanup-candidates candidate_count=0`.
- Leftover old non-current sources are ask pollution; owner removes them in the UI.
- Durable enforcement belongs in CLI helpers/tests/harness docs, not prompts only.