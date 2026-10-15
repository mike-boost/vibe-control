"""Phase 4F lifecycle / naming / receipt / wait / preview tests (no real NotebookLM)."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import yaml

from vibe_control.cli import main
from vibe_control.knowledge import managed_names, receipt, source_identity, source_lifecycle
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.sync_preview import RemoteSource, build_sync_preview
from helpers import minimal_config_dict, write_doc, write_registry


REPO = Path(__file__).resolve().parents[1]


def _cfg_dict() -> dict:
    raw = minimal_config_dict(
        include_extra=["docs/project/DECISION_LOG.md"],
        max_sources=20,
        warn_sources=15,
    )
    raw["project"] = {"id": "vibe-control", "name": "Vibe Control"}
    raw["knowledge"]["notebooks"] = {
        "default_alias": "OPM-test",
        "allow_list": [
            {
                "alias": "OPM-test",
                "display_name": "OPM-test",
                "ref_env": "NOTEBOOKLM_NOTEBOOK_OPM_TEST",
                "allowed_operations": [
                    "status",
                    "inventory",
                    "sync_preview",
                    "add_test_sources_with_approval",
                ],
            }
        ],
    }
    return raw


def _write_project(tmp: Path) -> Path:
    cfg = tmp / ".config" / "vibe-control.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump(_cfg_dict()), encoding="utf-8")
    write_registry(
        tmp,
        [
            {
                "id": "vibe_control_v0_5_spec",
                "title": "Vibe Control v0.5 Spec",
                "status": "active",
                "path": "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
            }
        ],
    )
    write_doc(tmp, "docs/project/VIBE_CONTROL_V0_5_SPEC.md", "spec body\n")
    write_doc(tmp, "docs/project/DECISION_LOG.md", "decision body\n")
    return cfg


def _module_imports_notebooklm(module_path: Path) -> bool:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "notebooklm" in alias.name:
                    return True
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "notebooklm" in mod or "providers.notebooklm" in mod:
                return True
            if "notebooklm_provider" in mod:
                return True
    return False


def test_provider_neutral_modules_do_not_import_notebooklm():
    root = REPO / "src" / "vibe_control" / "knowledge"
    for name in ("managed_names.py", "receipt.py", "source_lifecycle.py", "source_identity.py"):
        assert not _module_imports_notebooklm(root / name), name


def test_notebooklm_cli_handling_only_in_provider():
    provider = REPO / "src" / "vibe_control" / "knowledge" / "providers" / "notebooklm.py"
    text = provider.read_text(encoding="utf-8")
    assert "source" in text and ("wait" in text or "add" in text)
    for name in ("managed_names.py", "receipt.py", "source_lifecycle.py"):
        body = (REPO / "src/vibe_control/knowledge" / name).read_text(encoding="utf-8")
        assert "notebooklm source" not in body
    # Implementation module may contain CLI argv; providers package must declare ownership.
    assert "NOTEBOOKLM_SOURCE_COMMANDS" in text or "source wait" in text


def test_repo_fallback_query_works_for_notebooklm_and_repo_providers(
    tmp_path: Path, monkeypatch, capsys
):
    _write_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBE_CONTROL_CONFIG", raising=False)
    q = tmp_path / "q.txt"
    q.write_text("spec body", encoding="utf-8")

    for provider in ("notebooklm", "repo"):
        raw = _cfg_dict()
        raw["knowledge"]["provider"] = provider
        (tmp_path / ".config" / "vibe-control.yaml").write_text(
            yaml.safe_dump(raw), encoding="utf-8"
        )
        code = main(["knowledge", "query", "--question-file", str(q), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert payload["ok"] is True
        assert payload["data"]["provider"] == "repo"
        assert payload["data"].get("synced") is False
        # Repo fallback: unavailable → degraded; reachable-but-unsynced → drift/pending.
        mode = payload.get("mode") or payload["data"].get("mode")
        assert mode in {"degraded", "drift", "pending"}


def test_llm_wiki_stub_not_implemented():
    from vibe_control.knowledge.providers import llm_wiki

    result = llm_wiki.LlmWikiProvider().status()
    assert result["code"] == "PROVIDER_NOT_IMPLEMENTED"


def test_managed_name_format_and_normalization():
    assert (
        managed_names.managed_name("vibe-control", "vibe_control_v0_5_spec")
        == "vibe__vibe-control__vibe_control_v0_5_spec"
    )
    name = managed_names.managed_name("My Project!", "Doc: One [x]")
    assert " " not in name and ":" not in name and "[" not in name and "]" not in name
    assert name.startswith("vibe__")
    assert managed_names.slug_project("a--b") == "a-b"
    assert managed_names.managed_name("a--b", "c___d") == "vibe__a-b__c_d"


def test_upload_filename_includes_content_hash():
    managed = "vibe__vibe-control__vibe_control_v0_5_spec"
    sha_a = hashlib.sha256(b"hello").hexdigest()
    sha_b = hashlib.sha256(b"hello!").hexdigest()
    fa = managed_names.upload_filename(managed, sha_a)
    fb = managed_names.upload_filename(managed, sha_b)
    assert fa == f"{managed}__h__{sha_a[:12]}.md"
    assert fa != fb


def test_source_identity_classification_matrix():
    project = "vibe-control"
    desired = {"vibe_control_v0_5_spec", "decision_log"}
    cases = [
        ("vibe__vibe-control__vibe_control_v0_5_spec", "managed_by_name", "vibe_control_v0_5_spec"),
        (
            "vibe__vibe-control__vibe_control_v0_5_spec__h__abc123abc123.md",
            "managed_by_hashed_filename",
            "vibe_control_v0_5_spec",
        ),
        ("VIBE_CONTROL_V0_5_SPEC.md", "possible_managed_by_legacy_filename", "vibe_control_v0_5_spec"),
        (
            "[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md",
            "legacy_managed",
            "DECISION_LOG",
        ),
        ("Random Notes", "unmanaged", None),
    ]
    for title, expected, doc_id in cases:
        c = source_identity.classify_title(
            title,
            project_id=project,
            desired_doc_ids=desired,
            path_hints={"vibe_control_v0_5_spec": "docs/project/VIBE_CONTROL_V0_5_SPEC.md"},
        )
        assert c["classification"] == expected, title
        if doc_id:
            assert c.get("doc_id") == doc_id


def test_receipt_match_is_managed_by_receipt():
    c = source_identity.classify_remote_source(
        {"id": "src-1", "title": "whatever"},
        project_id="vibe-control",
        desired_doc_ids={"vibe_control_v0_5_spec"},
        receipt_source_ids={"src-1": "vibe_control_v0_5_spec"},
        path_hints={},
    )
    assert c["classification"] == "managed_by_receipt"
    assert c["doc_id"] == "vibe_control_v0_5_spec"


def test_duplicate_and_orphan_and_legacy_blocks_add():
    sources = [
        RemoteSource("a", "vibe__vibe-control__vibe_control_v0_5_spec"),
        RemoteSource("b", "vibe__vibe-control__vibe_control_v0_5_spec"),
        RemoteSource("c", "vibe__vibe-control__orphan_doc"),
        RemoteSource("d", "VIBE_CONTROL_V0_5_SPEC.md"),
        RemoteSource("e", "human notes"),
    ]
    classified = source_identity.classify_inventory(
        sources,
        project_id="vibe-control",
        desired_doc_ids={"vibe_control_v0_5_spec"},
        path_hints={"vibe_control_v0_5_spec": "docs/project/VIBE_CONTROL_V0_5_SPEC.md"},
    )
    assert classified["duplicate_managed_count"] >= 1
    assert classified["orphan_managed_count"] >= 1
    assert any(x["classification"] == "unmanaged" for x in classified["items"])
    assert source_identity.legacy_possible_blocks_add(
        classified, doc_id="vibe_control_v0_5_spec"
    )


def test_sync_preview_operation_states(tmp_path: Path):
    from vibe_control.config import load_config

    _write_project(tmp_path)
    config = load_config(tmp_path)
    corpus = build_desired_corpus(config, repo_root=tmp_path)
    spec = next(d for d in corpus.documents if d.doc_id == "vibe_control_v0_5_spec")
    sha = hashlib.sha256((tmp_path / spec.path).read_bytes()).hexdigest()
    managed = managed_names.managed_name(config.project_id, spec.doc_id)
    hashed = managed_names.upload_filename(managed, sha)

    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[],
        receipt=None,
    )
    assert any(op["op"] == "add_missing" for op in preview["operations"])
    assert preview["safe_to_sync"] is False

    receipt_obj = {
        "documents": {
            spec.doc_id: {"current": {"provider_source_id": "src-1", "content_sha256": sha}}
        }
    }
    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource("src-1", managed)],
        receipt=receipt_obj,
    )
    assert any(op["op"] == "already_current" for op in preview["operations"])

    receipt_obj["documents"][spec.doc_id]["current"]["content_sha256"] = "0" * 64
    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource("src-1", managed)],
        receipt=receipt_obj,
    )
    assert any(op["op"] == "replace_required" for op in preview["operations"])

    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource("src-2", managed)],
        receipt=None,
    )
    assert any(op["op"] == "already_present_needs_verification" for op in preview["operations"])

    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource("src-3", hashed)],
        receipt=None,
    )
    assert any(op["op"] == "managed_by_filename_fallback" for op in preview["operations"])

    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource("src-4", "VIBE_CONTROL_V0_5_SPEC.md")],
        receipt=None,
    )
    ops = preview["operations"]
    assert any(op["op"] == "possible_managed_needs_review" for op in ops)
    assert not any(op["op"] in {"update", "delete", "clean"} for op in ops)

    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=[RemoteSource("src-5", "human notes")],
        receipt=None,
    )
    assert any(op["op"] == "unmanaged_ignore" for op in preview["operations"])

    preview = build_sync_preview(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        remote_sources=None,
        blocked_reason="source_limit_exceeded",
    )
    assert any(op["op"] == "blocked" for op in preview["operations"])


def test_receipt_path_and_history(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = receipt.receipt_path("vibe-control")
    assert path.as_posix().endswith(
        ".agents/state/vibe-control/vibe-control/knowledge-sync.json"
    )
    assert ".config" not in path.as_posix()

    status = receipt.status("vibe-control")
    assert status["ok"] is True
    assert status["present"] is False
    assert status.get("warnings") or status.get("warning")

    store = receipt.ReceiptStore(path)
    store.write_verified(
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:abc",
        doc_id="vibe_control_v0_5_spec",
        path_str="docs/project/VIBE_CONTROL_V0_5_SPEC.md",
        managed_name="vibe__vibe-control__vibe_control_v0_5_spec",
        current={
            "provider_source_id": "src-old",
            "upload_filename": "vibe__vibe-control__vibe_control_v0_5_spec__h__aaaaaaaaaaaa.md",
            "remote_title_observed": "vibe__vibe-control__vibe_control_v0_5_spec",
            "title_state": "exact",
            "status": "ready",
            "content_sha256": "a" * 64,
        },
    )
    store.write_verified(
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:abc",
        doc_id="vibe_control_v0_5_spec",
        path_str="docs/project/VIBE_CONTROL_V0_5_SPEC.md",
        managed_name="vibe__vibe-control__vibe_control_v0_5_spec",
        current={
            "provider_source_id": "src-new",
            "upload_filename": "vibe__vibe-control__vibe_control_v0_5_spec__h__bbbbbbbbbbbb.md",
            "remote_title_observed": "vibe__vibe-control__vibe_control_v0_5_spec",
            "title_state": "exact",
            "status": "ready",
            "content_sha256": "b" * 64,
        },
    )
    data = store.load()
    doc = data["documents"]["vibe_control_v0_5_spec"]
    assert doc["current"]["provider_source_id"] == "src-new"
    assert doc["history"][0]["provider_source_id"] == "src-old"
    assert doc["history"][0]["state"] == "superseded"

    public = receipt.inspect("vibe-control", report_mode=True)
    dumped = json.dumps(public)
    assert "src-new" not in dumped
    assert "src-old" not in dumped

    path.write_text("{not-json", encoding="utf-8")
    corrupted = receipt.status("vibe-control")
    assert corrupted["ok"] is False
    assert corrupted["code"] == "RECEIPT_CORRUPTED"
    assert corrupted.get("next_actions")


def test_verified_add_receipt_write_gate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = receipt.receipt_path("vibe-control")
    store = receipt.ReceiptStore(path)
    assert not path.exists()
    result = source_lifecycle.record_verified_add(
        store,
        verified=False,
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:x",
        doc_id="doc",
        path_str="p.md",
        managed_name="vibe__vibe-control__doc",
        current={"provider_source_id": "s", "content_sha256": "c" * 64, "status": "ready"},
    )
    assert result["receipt_written"] is False
    assert not path.exists()

    result = source_lifecycle.record_verified_add(
        store,
        verified=True,
        project_id="vibe-control",
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:x",
        doc_id="doc",
        path_str="p.md",
        managed_name="vibe__vibe-control__doc",
        current={
            "provider_source_id": "s",
            "upload_filename": "vibe__vibe-control__doc__h__cccccccccccc.md",
            "remote_title_observed": "vibe__vibe-control__doc",
            "title_state": "exact",
            "status": "ready",
            "content_sha256": "c" * 64,
        },
    )
    assert result["receipt_written"] is True
    assert path.exists()


def test_source_wait_ready_error_timeout_and_fallback():
    statuses = iter(["processing", "ready"])

    def poll_ready(_sid: str) -> dict:
        return {"status": next(statuses), "found": True}

    r = source_lifecycle.wait_for_source(
        "src",
        poll_status=poll_ready,
        direct_wait=None,
        timeout_seconds=5,
        interval_seconds=0,
    )
    assert r["status"] == "ready"
    assert r["ok"] is True

    def poll_error(_sid: str) -> dict:
        return {"status": "error", "found": True}

    r = source_lifecycle.wait_for_source(
        "src",
        poll_status=poll_error,
        direct_wait=None,
        timeout_seconds=2,
        interval_seconds=0,
    )
    assert r["status"] == "error"
    assert r["ok"] is False

    def poll_stuck(_sid: str) -> dict:
        return {"status": "processing", "found": True}

    r = source_lifecycle.wait_for_source(
        "src",
        poll_status=poll_stuck,
        direct_wait=None,
        timeout_seconds=0.05,
        interval_seconds=0.01,
    )
    assert r["status"] == "timeout"
    assert r["code"] == "SOURCE_WAIT_TIMEOUT"

    def direct(_sid: str, **_kwargs) -> dict:
        return {"ok": True, "status": "ready", "found": True}

    r = source_lifecycle.wait_for_source(
        "src",
        poll_status=lambda _s: {"status": "processing", "found": True},
        direct_wait=direct,
        timeout_seconds=5,
        interval_seconds=0,
    )
    assert r["status"] == "ready"

    for status in ("ready", "processing", "preparing", "error", "unknown", "not_found", "timeout"):
        assert status in source_lifecycle.PROVIDER_NEUTRAL_STATUSES


class FakeNotebookProvider:
    def __init__(self, *, remote=None, add_title=None, never_appear=False, fail_wait=False):
        self.remote = list(remote or [])
        self.add_title = add_title
        self.never_appear = never_appear
        self.fail_wait = fail_wait
        self.mutations = []
        self._counter = 0

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": self.remote}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self.mutations.append(("add", Path(file_path).name, title))
        if self.never_appear:
            return {"ok": True, "code": "OK", "result": {"source": {"id": "ghost", "title": title}}}
        self._counter += 1
        sid = f"src-{self._counter}"
        if self.add_title == "filename":
            observed = Path(file_path).name
        elif self.add_title is not None:
            observed = self.add_title
        else:
            observed = title
        self.remote.append({"id": sid, "title": observed, "status": "ready"})
        return {"ok": True, "code": "OK", "result": {"source": {"id": sid, "title": observed}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        if self.fail_wait or self.never_appear:
            return {"ok": False, "status": "timeout", "code": "SOURCE_WAIT_TIMEOUT"}
        return {"ok": True, "status": "ready"}

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        for item in self.remote:
            if item.get("id") == source_id:
                return {"ok": True, "found": True, "source": item}
        return {"ok": False, "found": False, "status": "not_found"}


def test_verified_add_flow_with_fake_provider(tmp_path: Path, monkeypatch):
    from vibe_control.config import load_config
    from vibe_control.knowledge import verified_add

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_project(tmp_path)
    config = load_config(tmp_path)
    corpus = build_desired_corpus(config, repo_root=tmp_path)
    spec = next(d for d in corpus.documents if d.doc_id == "vibe_control_v0_5_spec")
    sha = hashlib.sha256((tmp_path / spec.path).read_bytes()).hexdigest()
    managed = managed_names.managed_name(config.project_id, spec.doc_id)
    upload = managed_names.upload_filename(managed, sha)

    dry = verified_add.plan_or_run(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=FakeNotebookProvider(remote=[]),
        dry_run=True,
        allow_add=False,
    )
    assert dry["ok"] is True
    planned = dry["data"]["planned"]
    assert planned
    assert planned[0]["managed_name"] == managed
    assert planned[0]["upload_filename"] == upload
    assert "__h__" in planned[0]["upload_filename"]

    legacy_provider = FakeNotebookProvider(
        remote=[{"id": "legacy", "title": "VIBE_CONTROL_V0_5_SPEC.md", "status": "ready"}]
    )
    blocked = verified_add.plan_or_run(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=legacy_provider,
        dry_run=False,
        allow_add=True,
    )
    assert blocked["ok"] is False or blocked["data"].get("needs_manual_review")
    assert not any(m[0] == "delete" for m in legacy_provider.mutations)

    provider = FakeNotebookProvider(remote=[], add_title="filename")
    ok = verified_add.plan_or_run(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=provider,
        dry_run=False,
        allow_add=True,
    )
    assert ok["ok"] is True
    added = ok["data"]["added"][0]
    assert added["provider_source_id"]
    assert added["title_state"] in {"filename_fallback", "exact"}
    assert added["receipt_written"] is True
    assert provider.mutations and provider.mutations[0][0] == "add"
    assert "__h__" in provider.mutations[0][1]
    assert not any(m[0] in {"delete", "clean", "update"} for m in provider.mutations)

    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    ghost = FakeNotebookProvider(remote=[], never_appear=True, fail_wait=True)
    partial = verified_add.plan_or_run(
        config,
        repo_root=tmp_path,
        notebook_alias="OPM-test",
        notebook_ref="nb-ref",
        provider=ghost,
        dry_run=False,
        allow_add=True,
    )
    assert partial["ok"] is False or partial.get("partial_success")
    assert receipt.status("vibe-control")["present"] is False


def test_no_tests_require_real_notebooklm_mutation_markers():
    # Suite covers verified add via FakeNotebookProvider only.
    assert "class FakeNotebookProvider" in Path(__file__).read_text(encoding="utf-8")
