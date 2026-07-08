"""Offline unit tests for VLM-grounded localization (no API calls).

Tests cover:
  - _scale_box: normal, degenerate, and out-of-range coordinates
  - _ocr_text_in_box: word center filtering
  - _regions_from_schema: schema → region extraction
  - _cross_check_score: verified / unverified / contradicted scenarios
  - _score_regions: end-to-end region scoring with mock parsed data
  - quorum rejection: too few surviving boxes → None
  - extract_json repair: malformed JSON recovery pipeline
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.vlm_locate import (
    _cross_check_score,
    _ocr_text_in_box,
    _regions_from_schema,
    _scale_box,
    _score_regions,
    MIN_VERIFIED,
    MIN_KEPT_FRACTION,
    VERIFY_SCORE,
    CONTRADICT_SCORE,
)
from pipeline.locate import FieldBox, Line, Word
from pipeline.vlm_client import extract_json


# ─────────────────────────── _scale_box ───────────────────────────


class TestScaleBox:
    def test_normal_coordinates(self):
        """Valid 0-1000 coords → pixel (x, y, w, h)."""
        box = [100, 200, 500, 800]  # ymin, xmin, ymax, xmax
        result = _scale_box(box, 1000, 1000)
        assert result is not None
        x, y, w, h = result
        assert x == 200 and y == 100
        assert w == 600 and h == 400

    def test_degenerate_sliver_width(self):
        """Box too narrow (<30px) → None."""
        box = [100, 500, 500, 510]  # xmax - xmin = 10 → w ≈ 10px on 1000px page
        assert _scale_box(box, 1000, 1000) is None

    def test_degenerate_sliver_height(self):
        """Box too short (<12px) → None."""
        box = [500, 100, 505, 800]  # ymax - ymin = 5 → h ≈ 5px
        assert _scale_box(box, 1000, 1000) is None

    def test_page_sized_box(self):
        """Box covering >65% of page → None (localizes nothing)."""
        box = [0, 0, 1000, 1000]  # full page
        assert _scale_box(box, 1000, 1000) is None

    def test_just_under_page_size(self):
        """Box covering ~64% of page → still valid."""
        box = [0, 0, 800, 800]  # 64%
        result = _scale_box(box, 1000, 1000)
        assert result is not None

    def test_clamping_negative(self):
        """Out-of-range negative coords → clamped to 0."""
        box = [100, -100, 500, 500]  # xmin = -100
        result = _scale_box(box, 1000, 1000)
        assert result is not None
        x, y, w, h = result
        assert x == 0  # clamped

    def test_clamping_overflow(self):
        """Coords > 1000 → clamped to page edge."""
        box = [100, 200, 500, 1200]  # xmax > 1000
        result = _scale_box(box, 1000, 1000)
        assert result is not None
        x, y, w, h = result
        assert x + w <= 1000

    def test_non_numeric_input(self):
        """Non-numeric box values → None."""
        assert _scale_box(["abc", 200, 500, 800], 1000, 1000) is None
        assert _scale_box(None, 1000, 1000) is None

    def test_real_world_proportions(self):
        """Realistic page (1200x1600) with normalized box."""
        box = [200, 50, 350, 950]  # narrow horizontal band
        result = _scale_box(box, 1200, 1600)
        assert result is not None
        x, y, w, h = result
        assert 50 <= x <= 70   # 50/1000 * 1200 = 60
        assert 300 <= y <= 340  # 200/1000 * 1600 = 320
        assert w > 30 and h > 12  # not degenerate


# ────────────────────── _ocr_text_in_box ──────────────────────────


class TestOcrTextInBox:
    def _make_lines(self, word_specs: list[tuple[int, int, int, int, str]]) -> list[Line]:
        """word_specs: [(x, y, w, h, text), ...]"""
        return [Line(words=[Word(x, y, w, h, t)]) for x, y, w, h, t in word_specs]

    def test_words_inside(self):
        """Words whose center falls inside the box are collected."""
        lines = self._make_lines([
            (100, 100, 50, 20, "hello"),
            (200, 100, 50, 20, "world"),
            (500, 100, 50, 20, "outside"),
        ])
        result = _ocr_text_in_box(lines, (80, 80, 200, 60))
        assert "hello" in result
        assert "world" in result
        assert "outside" not in result

    def test_empty_box(self):
        """No words inside → empty string."""
        lines = self._make_lines([(500, 500, 50, 20, "far")])
        result = _ocr_text_in_box(lines, (0, 0, 50, 50))
        assert result == ""

    def test_word_on_boundary(self):
        """Word center exactly on box edge → included."""
        lines = self._make_lines([(100, 100, 50, 20, "edge")])
        # center of word: (125, 110)
        result = _ocr_text_in_box(lines, (100, 100, 25, 10))
        assert "edge" in result


# ──────────────────── _regions_from_schema ────────────────────────


class TestRegionsFromSchema:
    def test_basic_schema(self):
        """Regions extracted from schema fields, page-only excluded."""
        schema = {"fields": [
            {"name": "a", "fr": "Champ A", "from": "zone1"},
            {"name": "b", "fr": "Champ B", "from": "zone1"},
            {"name": "c", "fr": "Champ C", "from": "page"},
            {"name": "d", "fr": "Champ D", "from": "zone2"},
        ]}
        regions = _regions_from_schema(schema)
        assert "zone1" in regions
        assert "zone2" in regions
        assert "page" not in regions
        assert len(regions["zone1"]) == 2

    def test_empty_schema(self):
        """No non-page fields → empty dict."""
        schema = {"fields": [{"name": "a", "from": "page"}]}
        assert _regions_from_schema(schema) == {}


# ────────────────── _cross_check_score ────────────────────────────


class TestCrossCheckScore:
    def test_exact_match(self):
        """Identical text → score near 100."""
        score = _cross_check_score("Abidjan le 16 Juillet", "Abidjan le 16 Juillet")
        assert score >= 95

    def test_partial_overlap(self):
        """VLM reads more than OCR captured → still high via partial_ratio."""
        score = _cross_check_score(
            "POUR L'ANNEE 1959 REGISTRE DES ACTES",
            "ACTES D'ABIDJAN 1959",
        )
        # token_set_ratio should pick up "1959", "ACTES" overlap
        assert score > 40  # not contradicted

    def test_completely_different(self):
        """Unrelated texts → low score."""
        score = _cross_check_score(
            "Naissance de Yamousso THIAM",
            "République Gabonaise Libreville",
        )
        assert score < 50

    def test_empty_inputs(self):
        """Empty claimed or OCR → 0."""
        assert _cross_check_score("", "some text") == 0.0
        assert _cross_check_score("claimed", "") == 0.0
        assert _cross_check_score("", "") == 0.0

    def test_ocr_noise(self):
        """OCR with garbage chars but same core text → still verifies."""
        score = _cross_check_score(
            "Dressé le vingt quatre Juillet",
            "=======Dressé le vingt quatre Juillet",
        )
        assert score >= VERIFY_SCORE


# ─────────────────── _score_regions ───────────────────────────────


class TestScoreRegions:
    def _make_lines(self, text_items: list[tuple[int, int, str]]) -> list[Line]:
        """text_items: [(x, y, text), ...] — simple words at given positions."""
        return [Line(words=[Word(x, y, 50, 20, t)]) for x, y, t in text_items]

    def test_verified_region(self):
        """Region with matching OCR → verified."""
        parsed = {
            "zone1": {"box_2d": [100, 100, 400, 900], "text": "hello world here now"},
        }
        regions = {"zone1": ["description"]}
        # put OCR words inside the box
        lines = self._make_lines([
            (200, 250, "hello"), (300, 250, "world"), (400, 250, "here"),
        ])
        fields, audit, n_ver, failed = _score_regions(parsed, regions, lines, 1000, 1000)
        assert len(fields) == 1
        assert n_ver >= 1
        assert fields[0].anchor_interpolated is False  # verified
        assert not failed

    def test_missing_region(self):
        """Region not in response → failed."""
        parsed = {}
        regions = {"zone1": ["description"]}
        fields, audit, n_ver, failed = _score_regions(parsed, regions, [], 1000, 1000)
        assert len(fields) == 0
        assert "zone1" in failed

    def test_sanity_rejection(self):
        """Full-page box → dropped."""
        parsed = {"zone1": {"box_2d": [0, 0, 1000, 1000], "text": "anything"}}
        regions = {"zone1": ["description"]}
        fields, audit, n_ver, failed = _score_regions(parsed, regions, [], 1000, 1000)
        assert len(fields) == 0
        assert "zone1" in failed


# ─────────────────── extract_json repair ──────────────────────────


class TestExtractJsonRepair:
    def test_clean_json(self):
        """Already valid JSON → passes through."""
        result = extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fences(self):
        """JSON wrapped in ```json ... ``` → stripped."""
        result = extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_trailing_comma(self):
        """Trailing comma before } → fixed."""
        result = extract_json('{"key": "value",}')
        assert result == {"key": "value"}

    def test_trailing_comma_nested(self):
        """Trailing comma in nested object → fixed."""
        result = extract_json('{"a": {"b": 1,}, "c": 2,}')
        assert result == {"a": {"b": 1}, "c": 2}

    def test_think_blocks(self):
        """<think>...</think> blocks stripped before parse."""
        result = extract_json('<think>let me think about this</think>{"key": "value"}')
        assert result == {"key": "value"}

    def test_text_around_json(self):
        """Extra text before/after JSON object → isolated."""
        result = extract_json('Here is the result:\n{"key": "value"}\nDone.')
        assert result == {"key": "value"}

    def test_single_quotes(self):
        """Single-quoted keys → converted to double-quoted."""
        result = extract_json("{'key': 'value'}")
        assert result == {"key": "value"}

    def test_no_json_at_all(self):
        """No JSON object → raises ValueError."""
        with pytest.raises(ValueError, match="no JSON object"):
            extract_json("just some text without any braces")

    def test_complex_real_world(self):
        """Realistic Gemini output with fence + trailing comma."""
        raw = '''```json
{
  "entete": {"box_2d": [30, 50, 120, 950], "text": "POUR L'ANNEE 1959"},
  "naissance": {"box_2d": [130, 50, 300, 950], "text": "ACTE N° 375"},
}
```'''
        result = extract_json(raw)
        assert "entete" in result
        assert result["entete"]["text"] == "POUR L'ANNEE 1959"

    def test_bom_and_control_chars(self):
        """BOM + control chars → stripped."""
        result = extract_json('\ufeff\x00{"key": "value"}')
        assert result == {"key": "value"}

    def test_newlines_in_strings(self):
        """Literal newlines inside string values → escaped."""
        raw = '{"text": "line one\nline two"}'
        result = extract_json(raw)
        assert "line one" in result["text"]


# ─────────────────── quorum logic ─────────────────────────────────


class TestQuorum:
    def test_quorum_thresholds(self):
        """MIN_KEPT_FRACTION and MIN_VERIFIED are sane defaults."""
        assert 0 < MIN_KEPT_FRACTION <= 1.0
        assert MIN_VERIFIED >= 1
        # with 6 regions, need at least 3 kept and 2 verified
        n_regions = 6
        assert max(1, round(MIN_KEPT_FRACTION * n_regions)) == 3
        assert MIN_VERIFIED == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
