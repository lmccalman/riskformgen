"""Tests for models.py — dataclass logic, to_js() compilation, validation."""

from __future__ import annotations

import pytest

from models import (
    BinaryQuestion,
    ConditionMapping,
    ControlEffect,
    Property,
    Section,
    _js_result,
    all_questions,
)

# ---------------------------------------------------------------------------
# BinaryQuestion
# ---------------------------------------------------------------------------


class TestBinaryQuestion:
    def test_basic(self):
        q = BinaryQuestion(id="q1", text="Is it?", properties=("p1", "p2"))
        assert q.id == "q1"
        assert q.type == "binary"
        assert q.properties == ("p1", "p2")
        assert q.guidance is None

    def test_with_guidance(self):
        q = BinaryQuestion(id="q1", text="Is it?", properties=("p1",), guidance="Help text")
        assert q.guidance == "Help text"

    def test_empty_properties(self):
        q = BinaryQuestion(id="q1", text="Is it?", properties=())
        assert q.properties == ()

    def test_frozen(self):
        q = BinaryQuestion(id="q1", text="Is it?", properties=("p1",))
        with pytest.raises(AttributeError):
            q.id = "q2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


class TestProperty:
    def test_root_property(self):
        p = Property(id="p1", description="Root")
        assert p.parents == ()
        assert p.activation == "all"

    def test_with_parents(self):
        p = Property(id="p2", description="Child", parents=("p1",))
        assert p.parents == ("p1",)

    def test_any_activation(self):
        p = Property(id="p2", description="Any", parents=("p1",), activation="any")
        assert p.activation == "any"


# ---------------------------------------------------------------------------
# Risk model helpers
# ---------------------------------------------------------------------------


class TestJsResult:
    def test_both_set(self):
        r = _js_result("likely", "major")
        assert r == '{likelihood: "likely", consequence: "major"}'

    def test_special_chars_escaped(self):
        r = _js_result("almost_certain", "minor")
        assert '"almost_certain"' in r
        assert '"minor"' in r


# ---------------------------------------------------------------------------
# ConditionMapping
# ---------------------------------------------------------------------------


class TestConditionMapping:
    def test_to_js_emits_single_property_check(self):
        cond = ConditionMapping(property="p1", likelihood="likely", consequence="major")
        js = cond.to_js()
        assert "this.prop_p1 === true" in js
        assert "likely" in js
        assert "major" in js
        assert "null" in js
        assert ".some(" not in js
        assert ".every(" not in js

    def test_frozen(self):
        cond = ConditionMapping(property="p1", likelihood="rare", consequence="minor")
        with pytest.raises(AttributeError):
            cond.property = "p2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class TestControlEffect:
    def test_basic(self):
        e = ControlEffect(risk_id="r1")
        assert e.risk_id == "r1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestAllQuestions:
    def test_flattens(self, sample_sections):
        qs = all_questions(sample_sections)
        assert len(qs) == 2  # binary_q + binary_q2 from sample_subsection

    def test_empty_sections(self):
        assert all_questions([]) == []

    def test_empty_subsections(self):
        section = Section(id="empty", title="Empty", description="", subsections=())
        assert all_questions([section]) == []
