"""Phase 8 unit tests: ProviderTarget and target_key_hash."""

from __future__ import annotations

import pytest

from vibe_control.knowledge.provider_target import (
    ProviderTarget,
    hash_notebook_ref,
    target_key_hash,
)


@pytest.mark.unit
def test_target_key_hash_stable_for_same_ref():
    h1 = target_key_hash(provider="notebooklm", notebook_ref_hash="sha256:abc")
    h2 = target_key_hash(provider="notebooklm", notebook_ref_hash="sha256:abc")
    assert h1 == h2
    assert h1.startswith("sha256:")


@pytest.mark.unit
def test_target_key_hash_changes_when_notebook_ref_hash_changes():
    a = target_key_hash(provider="notebooklm", notebook_ref_hash="sha256:aaa")
    b = target_key_hash(provider="notebooklm", notebook_ref_hash="sha256:bbb")
    assert a != b


@pytest.mark.unit
def test_auth_profile_hash_null_not_in_target_key():
    with_null = ProviderTarget(
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:abc",
        auth_profile_hash=None,
    )
    with_value = ProviderTarget(
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref_hash="sha256:abc",
        auth_profile_hash="sha256:profile",
    )
    # Phase 8.0: auth_profile_hash must not affect target_key_hash
    assert with_null.target_key_hash == with_value.target_key_hash
    assert with_null.auth_profile_hash is None


@pytest.mark.unit
def test_hash_notebook_ref_redacts_raw_ref():
    hashed = hash_notebook_ref("raw-notebook-id-secret")
    assert hashed.startswith("sha256:")
    assert "secret" not in hashed
    assert hashed == hash_notebook_ref("raw-notebook-id-secret")


@pytest.mark.unit
def test_provider_target_to_dict_includes_null_auth():
    target = ProviderTarget.from_ref(
        provider="notebooklm",
        notebook_alias="OPM-test",
        notebook_ref="nb-123",
    )
    data = target.to_dict()
    assert data["provider"] == "notebooklm"
    assert data["notebook_alias"] == "OPM-test"
    assert data["auth_profile_hash"] is None
    assert data["target_key_hash"] == target.target_key_hash
    assert data["notebook_ref_hash"] == hash_notebook_ref("nb-123")
