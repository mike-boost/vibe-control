"""ProviderTarget identity for notebook-scoped knowledge sync."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_notebook_ref(notebook_ref: str) -> str:
    return sha256_hex(notebook_ref or "")


def target_key_hash(*, provider: str, notebook_ref_hash: str) -> str:
    """Phase 8.0: auth_profile_hash is intentionally excluded."""
    return sha256_hex(
        canonical_json(
            {
                "provider": provider,
                "notebook_ref_hash": notebook_ref_hash,
            }
        )
    )


@dataclass(frozen=True)
class ProviderTarget:
    provider: str
    notebook_alias: str
    notebook_ref_hash: str
    auth_profile_hash: str | None = None
    target_key_hash: str = ""

    def __post_init__(self) -> None:
        if not self.target_key_hash:
            object.__setattr__(
                self,
                "target_key_hash",
                target_key_hash(
                    provider=self.provider,
                    notebook_ref_hash=self.notebook_ref_hash,
                ),
            )

    @classmethod
    def from_ref(
        cls,
        *,
        provider: str,
        notebook_alias: str,
        notebook_ref: str,
        auth_profile_hash: str | None = None,
    ) -> ProviderTarget:
        ref_hash = hash_notebook_ref(notebook_ref)
        return cls(
            provider=provider,
            notebook_alias=notebook_alias,
            notebook_ref_hash=ref_hash,
            auth_profile_hash=auth_profile_hash,
            target_key_hash=target_key_hash(provider=provider, notebook_ref_hash=ref_hash),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "notebook_alias": self.notebook_alias,
            "notebook_ref_hash": self.notebook_ref_hash,
            "auth_profile_hash": self.auth_profile_hash,
            "target_key_hash": self.target_key_hash,
        }
