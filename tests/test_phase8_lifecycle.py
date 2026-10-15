"""Phase 8 integration: update lifecycle receipt-switch-before-delete (fake provider)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe_control.knowledge.managed_names import content_sha256_bytes, managed_name, upload_filename
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.sync_lifecycle_phase8 import replace_item_with_receipt_switch


class FakeLifecycleProvider:
    def __init__(self) -> None:
        self.remote: list[dict] = []
        self.mutations: list[tuple] = []
        self._n = 0

    def list_sources(self, *, notebook_ref: str) -> dict:
        return {"ok": True, "sources": list(self.remote)}

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict:
        self._n += 1
        sid = f"src-{self._n}"
        name = Path(file_path).name
        self.remote.append({"id": sid, "title": name, "status": "ready"})
        self.mutations.append(("add", sid, name))
        return {"ok": True, "result": {"source": {"id": sid, "title": name}}}

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict:
        return {"ok": True, "status": "ready"}

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict:
        for item in self.remote:
            if item.get("id") == source_id:
                return {"ok": True, "found": True, "source": item}
        return {"ok": False, "found": False}

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict:
        self.mutations.append(("delete", source_id))
        self.remote = [x for x in self.remote if x.get("id") != source_id]
        return {"ok": True}


@pytest.mark.integration
def test_update_switches_receipt_before_delete(tmp_path: Path):
    target = ProviderTarget.from_ref(
        provider="notebooklm", notebook_alias="OPM-test", notebook_ref="nb-life"
    )
    provider = FakeLifecycleProvider()
    old_body = b"old content\n"
    new_body = b"new content\n"
    old_sha = content_sha256_bytes(old_body)
    new_sha = content_sha256_bytes(new_body)
    mname = managed_name("vibe-control", "spec")
    old_name = upload_filename(mname, old_sha)
    new_file = tmp_path / "spec.md"
    new_file.write_bytes(new_body)

    receipt = {
        "provider_target": target.to_dict(),
        "items": {
            "spec": {
                "doc_id": "spec",
                "path": "spec.md",
                "content_sha256": "sha256:" + old_sha,
                "provider_source_id": "src-old",
                "source_id_hash": "sha256:old",
                "managed_name": mname,
                "upload_filename": old_name,
                "ready": True,
            }
        },
        "cleanup_pending": [],
    }
    provider.remote.append({"id": "src-old", "title": old_name, "status": "ready"})

    events: list[str] = []

    def on_receipt(data: dict) -> None:
        events.append("receipt_switched")
        assert data["items"]["spec"]["provider_source_id"] != "src-old"
        assert any(x.get("provider_source_id") == "src-old" for x in data.get("cleanup_pending") or [])

    def on_before_delete(source_id: str) -> None:
        events.append(f"delete:{source_id}")
        assert "receipt_switched" in events

    result = replace_item_with_receipt_switch(
        provider,
        notebook_ref="nb-life",
        target=target,
        project_id="vibe-control",
        doc_id="spec",
        path_str="spec.md",
        file_path=new_file,
        content_sha256=new_sha,
        receipt=receipt,
        on_receipt_switched=on_receipt,
        on_before_delete=on_before_delete,
    )
    assert result["ok"] is True
    assert events[0] == "receipt_switched"
    assert events[1].startswith("delete:")
    assert not any(x.get("id") == "src-old" for x in provider.remote)
    assert receipt["items"]["spec"]["content_sha256"] == "sha256:" + new_sha
    assert receipt.get("cleanup_pending") == []
