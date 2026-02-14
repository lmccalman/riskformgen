"""Tests for models.py — dataclass logic, to_js() compilation, validation."""

from __future__ import annotations

import json

import pytest

from models import (
    All,
    Any,
    AnyYesRule,
    ChoiceMapRule,
    Contains,
    ContainsAnyRule,
    Control,
    ControlEffect,
    CountYesRule,
    Equals,
    Not,
    Section,
    _js_ids,
    _js_result,
    all_questions,
)

# ---------------------------------------------------------------------------
# Visibility conditions — to_js()
# ---------------------------------------------------------------------------


class TestEquals:
    def test_basic(self):
        c = Equals(question_id="q1", value="yes")
        assert c.to_js() == 'answers["q1"] === "yes"'

    def test_special_chars_in_value(self):
        c = Equals(question_id="q1", value='it\'s a "test"')
        js = c.to_js()
        # json.dumps escapes quotes properly
        assert '"it\'s a \\"test\\""' in js


class TestContains:
    def test_basic(self):
        c = Contains(question_id="q1", value="opt_a")
        js = c.to_js()
        assert ".includes(" in js
        assert "|| []" in js  # null guard

    def test_output_is_valid_shape(self):
        c = Contains(question_id="q1", value="x")
        js = c.to_js()
        assert js == '(answers["q1"] || []).includes("x")'


class TestAll:
    def test_joins_with_and(self):
        c = All(
            conditions=(
                Equals(question_id="a", value="1"),
                Equals(question_id="b", value="2"),
            )
        )
        js = c.to_js()
        assert "&&" in js
        assert "(answers" in js

    def test_single_condition(self):
        c = All(conditions=(Equals(question_id="a", value="1"),))
        js = c.to_js()
        # Single condition — no && needed, just wrapped in parens
        assert "&&" not in js
        assert "(answers" in js


class TestAny:
    def test_joins_with_or(self):
        c = Any(
            conditions=(
                Equals(question_id="a", value="1"),
                Equals(question_id="b", value="2"),
            )
        )
        js = c.to_js()
        assert "||" in js

    def test_single_condition(self):
        c = Any(conditions=(Equals(question_id="a", value="1"),))
        js = c.to_js()
        assert "||" not in js


class TestNot:
    def test_negation(self):
        c = Not(condition=Equals(question_id="q1", value="yes"))
        js = c.to_js()
        assert js.startswith("!(")
        assert js.endswith(")")

    def test_double_negation(self):
        inner = Equals(question_id="q1", value="yes")
        c = Not(condition=Not(condition=inner))
        js = c.to_js()
        assert js.startswith("!(!(")


class TestNestedConditions:
    def test_any_containing_all(self):
        c = Any(
            conditions=(
                All(
                    conditions=(
                        Equals(question_id="a", value="1"),
                        Equals(question_id="b", value="2"),
                    )
                ),
                Equals(question_id="c", value="3"),
            )
        )
        js = c.to_js()
        assert "||" in js
        assert "&&" in js


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
        assert len(qs) == 2  # yes_no_q + choice_q from sample_subsection

    def test_empty_sections(self):
        assert all_questions([]) == []

    def test_empty_subsections(self):
        section = Section(id="empty", title="Empty", description="", subsections=())
        assert all_questions([section]) == []
