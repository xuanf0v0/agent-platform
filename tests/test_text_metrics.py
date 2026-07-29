"""R1 plain length + R3 KW/RW unique hit counters."""

from __future__ import annotations

from amazon_copy.utils.text_metrics import (
    aggregate_hits_across_texts,
    count_unique_hits,
    find_unique_hits,
    meets_kw_rw_floors,
    plain_len,
    strip_md_bold,
)


class TestStripMdBoldWhenMarkdownMarkers:
    def test_strips_double_star_and_underscore(self) -> None:
        # Given
        marked = "**usb** hub __cable__"
        # When / Then
        assert strip_md_bold(marked) == "usb hub cable"
        assert plain_len(marked) == len("usb hub cable")

    def test_plain_usb_hub_len(self) -> None:
        # AC: **usb** hub → plain usb hub, len correct
        assert strip_md_bold("**usb** hub") == "usb hub"
        assert plain_len("**usb** hub") == len("usb hub")


class TestFindUniqueHitsWhenCaseAndBoundaries:
    def test_case_insensitive_whole_token(self) -> None:
        # Given
        text = "Premium USB Cable pack"
        terms = ["usb", "cable", "hdmi"]
        # When
        hits = find_unique_hits(text, terms)
        # Then
        assert set(hits) == {"usb", "cable"}
        assert "hdmi" not in hits

    def test_no_partial_token_match(self) -> None:
        # "usb" must not match inside "usbcable" without boundary
        assert find_unique_hits("usbcable device", ["usb"]) == []
        assert find_unique_hits("device usb ready", ["usb"]) == ["usb"]

    def test_bold_markers_stripped_before_match(self) -> None:
        # AC: **usb** hub still hits usb
        hits = find_unique_hits("**usb** hub", ["usb", "hub"])
        assert set(hits) == {"usb", "hub"}

    def test_multiplicity_not_counted(self) -> None:
        # unique list items present, not multiplicity
        text = "usb usb USB cable cable"
        assert count_unique_hits(text, ["usb", "cable"]) == 2
        hits = find_unique_hits(text, ["usb", "cable", "usb"])
        assert hits.count("usb") == 1
        assert len(hits) == 2


class TestFindUniqueHitsWhenMultiWordLongestFirst:
    def test_multi_word_before_shorter_in_hits(self) -> None:
        # AC: multi-word usb hub before usb when both present
        text = "portable usb hub for travel"
        terms = ["usb", "usb hub", "hub"]
        hits = find_unique_hits(text, terms)
        assert "usb hub" in hits
        assert "usb" in hits
        assert hits.index("usb hub") < hits.index("usb")

    def test_multi_word_casefold_with_end_boundaries(self) -> None:
        text = "Best USB Hub Adapter kit"
        assert find_unique_hits(text, ["usb hub"]) == ["usb hub"]
        # partial multi-word should not match mid-token
        assert find_unique_hits("xusb hubx", ["usb hub"]) == []


class TestAggregateHitsAcrossTexts:
    def test_union_unique_across_bps(self) -> None:
        texts = [
            "fast charge usb-c",
            "durable cable braid",
            "compact travel size",
        ]
        terms = ["usb-c", "cable", "travel", "missing"]
        hits = aggregate_hits_across_texts(texts, terms)
        assert set(hits) == {"usb-c", "cable", "travel"}
        assert count_unique_hits(" ".join(texts), terms) == len(hits)


class TestMeetsKwRwFloors:
    def test_dense_fixture_passes_floors(self) -> None:
        # Happy: ≥10 KW and ≥20 RW across 5 BPs combined
        keywords = [f"kw{i}" for i in range(12)]
        rootwords = [f"rw{i}" for i in range(22)]
        # Spread terms across 5 bullet texts
        texts = [
            " ".join(keywords[:3] + rootwords[:5]),
            " ".join(keywords[3:6] + rootwords[5:10]),
            " ".join(keywords[6:9] + rootwords[10:15]),
            " ".join(keywords[9:12] + rootwords[15:20]),
            " ".join([*rootwords[20:22], "padding"]),
        ]
        ok, detail = meets_kw_rw_floors(texts, keywords, rootwords)
        assert ok is True
        assert detail["kw_count"] >= 10
        assert detail["rw_count"] >= 20
        assert detail["kw_ok"] is True
        assert detail["rw_ok"] is True

    def test_sparse_fixture_fails_floors(self) -> None:
        keywords = [f"kw{i}" for i in range(12)]
        rootwords = [f"rw{i}" for i in range(22)]
        texts = ["only kw0 and rw0 here", "nothing else useful"]
        ok, detail = meets_kw_rw_floors(texts, keywords, rootwords)
        assert ok is False
        assert detail["kw_count"] < 10
        assert detail["rw_count"] < 20
        assert detail["kw_ok"] is False
        assert detail["rw_ok"] is False

    def test_custom_min_thresholds(self) -> None:
        texts = ["alpha beta gamma"]
        ok, detail = meets_kw_rw_floors(
            texts,
            keywords=["alpha", "beta"],
            rootwords=["gamma", "delta"],
            min_kw=2,
            min_rw=1,
        )
        assert ok is True
        assert detail["kw_count"] == 2
        assert detail["rw_count"] == 1
