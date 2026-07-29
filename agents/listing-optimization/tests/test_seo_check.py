"""Deterministic SEO V/X tables; LLM prose never owns presence booleans."""

from __future__ import annotations

from amazon_copy.agents.seo import check_seo


def test_known_listing_marks_three_of_five_intents() -> None:
    result = check_seo(
        title="USB C Hub for Remote Work",
        bullets=["Connect a monitor and charge a laptop during travel"],
        intents=["remote work", "monitor", "travel", "gaming", "gift"],
        rootwords=["usb", "hub"],
        keywords=["usb c hub"],
    )

    assert [row.mark for row in result.intent_rows] == ["V", "V", "V", "X", "X"]
    assert result.intent_count == 3


def test_bold_markers_do_not_hide_a_hit() -> None:
    result = check_seo(
        title="**USB C Hub**",
        bullets=["A **multiport adapter** for work"],
        intents=["work"],
        rootwords=["usb", "adapter"],
        keywords=["usb c hub", "multiport adapter"],
    )

    assert all(row.present for row in result.intent_rows)
    assert all(row.present for row in result.rootword_rows)
    assert all(row.present for row in result.keyword_rows)


def test_full_embed_is_all_v_and_empty_listing_is_all_x() -> None:
    terms = ["portable", "creator"]
    full = check_seo(
        title="Portable creator hub",
        bullets=["Portable tools for every creator"],
        intents=terms,
        rootwords=terms,
        keywords=terms,
    )
    empty = check_seo(
        title="",
        bullets=[],
        intents=terms,
        rootwords=terms,
        keywords=terms,
    )

    assert {row.mark for row in full.intent_rows + full.rootword_rows + full.keyword_rows} == {"V"}
    empty_rows = empty.intent_rows + empty.rootword_rows + empty.keyword_rows
    assert {row.mark for row in empty_rows} == {"X"}


def test_title_and_bullet_tables_are_separate_and_counts_are_unique() -> None:
    result = check_seo(
        title="USB Hub USB Hub",
        bullets=["HDMI adapter", "HDMI adapter for laptop"],
        intents=["laptop"],
        rootwords=["usb", "hub", "hdmi", "adapter", "HDMI", ""],
        keywords=["usb hub", "hdmi adapter"],
    )

    assert [row.mark for row in result.title_keyword_rows] == ["V", "X"]
    assert [row.mark for row in result.bullet_keyword_rows] == ["X", "V"]
    assert result.rootword_count == 4
    assert result.keyword_count == 2
    assert result.bullet_rootword_count == 2
    assert result.bullet_keyword_count == 1


def test_duplicate_and_malformed_terms_are_deduplicated_without_false_hits() -> None:
    result = check_seo(
        title="USB cable",
        bullets=[],
        intents=["", "  ", "usb", "USB", "cable", "cab", "usb  cable"],
        rootwords=[],
        keywords=[],
        narrative="Optional prose; cannot change table truth.",
    )

    assert [(row.item, row.mark) for row in result.intent_rows] == [
        ("usb", "V"),
        ("cable", "V"),
        ("cab", "X"),
        ("usb cable", "V"),
    ]
    assert result.narrative == "Optional prose; cannot change table truth."


def test_ascii_whole_token_boundary_is_explicit() -> None:
    result = check_seo(
        title="éUSB device but not usbcable",
        bullets=[],
        intents=[],
        rootwords=["usb"],
        keywords=[],
    )

    assert result.rootword_rows[0].mark == "V"
