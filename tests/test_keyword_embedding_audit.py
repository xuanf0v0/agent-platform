from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from amazon_copy.resources.amazon_copy_optimization import (
    KeywordAuditListing,
    KeywordEmbeddingAuditPayload,
    MissingKeywordsError,
    audit_keyword_embedding,
    exact_count,
    load_keywords,
)
from amazon_copy.resources.amazon_copy_optimization.scripts.audit_keyword_embedding import app
from pydantic import TypeAdapter
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path


def test_audit_separates_exact_root_and_backend_coverage() -> None:
    # Given: visible copy, backend roots, and two target phrases.
    listing = KeywordAuditListing(
        title="Mesh Zipper Pouch Set",
        item_highlights="Small organizer",
        bullets=("Reusable mesh bags",),
        search_terms="pencil pouch organizer",
    )

    # When: the typed library audits one exact and one root-only phrase.
    result = audit_keyword_embedding(listing, ("mesh zipper pouch", "pencil bag"))

    # Then: exact, root, and incremental outcomes remain distinct.
    assert result.exact_phrase_coverage.covered == 1
    assert result.root_set_coverage.covered == 2
    assert result.backend_search_terms.incremental_tokens == ("pencil",)
    assert result.backend_search_terms.visible_redundant_tokens == ("organizer", "pouch")


def test_exact_count_keeps_nested_phrase_matches_mechanical() -> None:
    # Given: a phrase nested twice in normalized punctuation and case.
    text = "Mesh zipper pouch; MESH ZIPPER POUCHES are different. Mesh zipper pouch."

    # When: exact contiguous singular tokens are counted.
    count = exact_count(text, "mesh zipper pouch")

    # Then: only the two exact contiguous occurrences count.
    assert count == 2


def test_audit_rejects_empty_target_set() -> None:
    # Given: an otherwise valid listing and only blank targets.
    listing = KeywordAuditListing(title="Mesh pouch")

    # When: the typed library starts the audit.
    with pytest.raises(MissingKeywordsError) as captured:
        _ = audit_keyword_embedding(listing, ("", "  "))

    # Then: the typed missing-keyword contract is raised.
    assert str(captured.value) == "provide at least one keyword"


def test_keyword_file_merge_is_stable_and_deduplicated(tmp_path: Path) -> None:
    # Given: repeated CLI values and a commented UTF-8 keyword file.
    source = tmp_path / "keywords.txt"
    _ = source.write_text("# reviewed targets\nmesh pouch\norganizer\n", encoding="utf-8")

    # When: both keyword sources are merged.
    keywords = load_keywords(("organizer", "organizer"), source)

    # Then: first occurrence order is stable and comments are excluded.
    assert keywords == ("organizer", "mesh pouch")


def test_thin_cli_emits_original_json_contract(tmp_path: Path) -> None:
    # Given: a listing JSON file and a repeated keyword option.
    listing_path = tmp_path / "listing.json"
    _ = listing_path.write_text(
        json.dumps(
            {
                "title": "Mesh Zipper Pouch",
                "item_highlights": "",
                "bullets": [],
                "description": "",
                "search_terms": "pencil organizer",
            }
        ),
        encoding="utf-8",
    )

    # When: the retained CLI is invoked through its real Typer surface.
    result = CliRunner().invoke(app, [str(listing_path), "--keyword", "mesh zipper pouch"])

    # Then: it exits cleanly with the original machine-readable top-level fields.
    assert result.exit_code == 0
    payload = TypeAdapter(KeywordEmbeddingAuditPayload).validate_json(result.stdout)
    assert payload["target_keyword_count"] == 1
    assert payload["exact_phrase_coverage"]["covered"] == 1
    assert payload["backend_search_terms"]["incremental_tokens"] == [
        "organizer",
        "pencil",
    ]
