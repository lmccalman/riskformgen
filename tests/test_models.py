"""Tests for models.py — dataclass logic, to_js() compilation, validation."""

from __future__ import annotations

import json

import pytest

from models import (
    AnyYesRule,
    BinaryQuestion,
    ChoiceMapRule,
    ContainsAnyRule,
    Control,
    ControlEffect,
    CountYesRule,
    Property,
    Section,
    _js_ids,
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
# Risk rule helpers
# ---------------------------------------------------------------------------


class TestJsIds:
    def test_formats_as_json_array(self):
        assert _js_ids(("a", "b")) == '["a", "b"]'

    def test_empty(self):
        assert _js_ids(()) == "[]"


class TestJsResult:
    def test_both_set(self):
        r = _js_result("likely", "major")
        assert r == '{likelihood: "likely", consequence: "major"}'

    def test_likelihood_only(self):
        r = _js_result("likely", None)
        assert r == '{likelihood: "likely", consequence: null}'

    def test_consequence_only(self):
        r = _js_result(None, "major")
        assert r == '{likelihood: null, consequence: "major"}'

    def test_both_none(self):
        r = _js_result(None, None)
        assert r == "{likelihood: null, consequence: null}"


# ---------------------------------------------------------------------------
# Risk rules — to_js() and validation
# ---------------------------------------------------------------------------


class TestAnyYesRule:
    def test_basic_js(self):
        rule = AnyYesRule(question_ids=("q1", "q2"), likelihood="likely")
        js = rule.to_js()
        assert ".some(" in js
        assert "=== 'yes'" in js or '=== "yes"' in js
        assert "likely" in js

    def test_validation_both_none(self):
        with pytest.raises(ValueError, match="at least one"):
            AnyYesRule(question_ids=("q1",))

    def test_referenced_question_ids(self):
        rule = AnyYesRule(question_ids=("q1", "q2"), likelihood="likely")
        assert rule.referenced_question_ids() == ("q1", "q2")


class TestCountYesRule:
    def test_basic_js(self):
        rule = CountYesRule(question_ids=("q1", "q2", "q3"), threshold=2, consequence="major")
        js = rule.to_js()
        assert ".filter(" in js
        assert ">= 2" in js
        assert "major" in js

    def test_validation_both_none(self):
        with pytest.raises(ValueError, match="at least one"):
            CountYesRule(question_ids=("q1",), threshold=1)

    def test_referenced_question_ids(self):
        rule = CountYesRule(question_ids=("a", "b"), threshold=1, likelihood="rare")
        assert rule.referenced_question_ids() == ("a", "b")


class TestChoiceMapRule:
    def test_basic_js(self):
        rule = ChoiceMapRule(
            question_id="q1",
            mapping={"alpha": {"likelihood": "rare"}},
        )
        js = rule.to_js()
        assert "this.answers[" in js
        assert "|| null" in js

    def test_normalises_missing_keys(self):
        rule = ChoiceMapRule(
            question_id="q1",
            mapping={"alpha": {"likelihood": "rare"}},
        )
        js = rule.to_js()
        # The normalised JSON should have consequence: null
        parsed = json.loads(js.split("[this.answers")[0])
        assert parsed["alpha"]["consequence"] is None
        assert parsed["alpha"]["likelihood"] == "rare"

    def test_referenced_question_ids(self):
        rule = ChoiceMapRule(question_id="q1", mapping={})
        assert rule.referenced_question_ids() == ("q1",)


class TestContainsAnyRule:
    def test_basic_js(self):
        rule = ContainsAnyRule(question_id="q1", values=("a", "b"), likelihood="possible")
        js = rule.to_js()
        assert ".some(" in js
        assert ".includes(" in js
        assert "|| []" in js  # null guard

    def test_validation_both_none(self):
        with pytest.raises(ValueError, match="at least one"):
            ContainsAnyRule(question_id="q1", values=("a",))

    def test_referenced_question_ids(self):
        rule = ContainsAnyRule(question_id="q1", values=("a",), likelihood="rare")
        assert rule.referenced_question_ids() == ("q1",)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class TestControlEffect:
    def test_validation_both_false(self):
        with pytest.raises(ValueError, match="at least one"):
            ControlEffect(risk_id="r1")

    def test_valid_likelihood_only(self):
        e = ControlEffect(risk_id="r1", reduces_likelihood=True)
        assert e.reduces_likelihood
        assert not e.reduces_consequence

    def test_valid_both(self):
        e = ControlEffect(risk_id="r1", reduces_likelihood=True, reduces_consequence=True)
        assert e.reduces_likelihood and e.reduces_consequence


class TestControlPresenceJs:
    def test_scalar_path(self):
        ctrl = Control(
            id="c1",
            name="C",
            question_id="q1",
            present_value="yes",
            effects=(ControlEffect(risk_id="r1", reduces_likelihood=True),),
        )
        js = ctrl.presence_js()
        assert "Array.isArray" in js
        assert ".includes(" in js
        assert "===" in js

    def test_quoted_values(self):
        ctrl = Control(
            id="c1",
            name="C",
            question_id="q with spaces",
            present_value='val"ue',
            effects=(ControlEffect(risk_id="r1", reduces_consequence=True),),
        )
        js = ctrl.presence_js()
        # json.dumps handles quoting
        assert "q with spaces" in js


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
