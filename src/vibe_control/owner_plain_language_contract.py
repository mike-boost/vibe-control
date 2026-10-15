"""Owner-facing communication: plain language, no opaque jargon."""

from __future__ import annotations

from typing import Any

OWNER_PLAIN_LANGUAGE_CONTRACT_ID = "vibe.communication.owner_plain_language.v1"


def owner_plain_language_contract_dict() -> dict[str, Any]:
    return {
        "contract_id": OWNER_PLAIN_LANGUAGE_CONTRACT_ID,
        "name": "owner_plain_language",
        "purpose": (
            "When talking to the product owner, use plain language. "
            "Do not hide meaning behind internal nicknames or unexplained English jargon."
        ),
        "rules": [
            "Answer the owner's question first, in short plain Chinese (or the owner's language).",
            "Prefer everyday words: 上传、同步、索引、格式、限制 — not unexplained slang.",
            "If a technical term is needed, define it in one short clause the first time, then reuse the short form.",
            "Forbidden with owner unless immediately explained: managed, managed sync, envelope, SSOT, "
            "ask-clean, product_ready, closeout, drift, next_actions, harness black-box nicknames.",
            "Do not invent new codenames in chat. Say what the CLI or provider actually does.",
            "Internal code/docs may keep precise identifiers; owner replies must still translate them.",
            "If two providers differ, say: Knowledge 有两个 provider，各自规则不同 — then list the difference.",
        ],
        "bad_examples": [
            "Vibe managed path forces .md upload_filename",
            "ask-clean + product_ready knowledge half via local_fts",
        ],
        "good_examples": [
            "Knowledge 有两个 provider。local_fts 只适合读文本/Markdown；"
            "notebooklm（Gemini Notebook）产品本身还能吃 pdf/图片/音频。"
            "我们应按当前选用的 provider 去限制能进知识库的文件格式。",
            "同步到 Gemini Notebook 时，Vibe 现在会把文件当成 .md 去上传"
            "（文件名也改成 .md）——这是当前实现，不是 Google 产品的完整格式表。",
        ],
        "entry_commands": [
            "vibe describe --json  # communication_contracts.owner_plain_language",
        ],
        "docs": [
            "AGENTS.md",
            "docs/harness/owner-plain-language-contract.md",
        ],
    }
