"""Tests for parse.py — YAML dict → dataclass parsing."""

from __future__ import annotations

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
    FreeTextQuestion,
    MultipleChoiceQuestion,
    MultipleSelectQuestion,
    Not,
    YesNoQuestion,
)
from parse import (
    _ensure_str,
    parse_condition,
    parse_control,
    parse_control_effect,
    parse_question,
    parse_risk,
    parse_rule,
    parse_section,
    parse_subsection,
)


# ---------------------------------------------------------------------------
# _ensure_str
# ---------------------------------------------------------------------------


class TestEnsureStr:
    def test_true_becomes_yes(self):
        assert _ensure_str(True) == "yes"

    def test_false_becomes_no(self):
        assert _ensure_str(False) == "no"

    def test_string_passthrough(self):
        assert _ensure_str("maybe") == "maybe"

    def test_int_raises(self):
        with pytest.raises(TypeError, match="int"):
            _ensure_str(123)

    def test_none_raises(self):
        with pytest.raises(TypeError):
            _ensure_str(None)


# ---------------------------------------------------------------------------
# parse_condition
# ---------------------------------------------------------------------------


class TestParseCondition:
    def test_equals(self):
        c = parse_condition({"equals": {"question_id": "q1", "value": "yes"}})
        assert isinstance(c, Equals)
        assert c.question_id == "q1"
        assert c.value == "yes"

    def test_equals_bool_value(self):
        c = parse_condition({"equals": {"question_id": "q1", "value": True}})
        assert c.value == "yes"

    def test_contains(self):
        c = parse_condition({"contains": {"question_id": "q1", "value": "opt"}})
        assert isinstance(c, Contains)

    def test_not(self):
        c = parse_condition({"not": {"equals": {"question_id": "q1", "value": "no"}}})
        assert isinstance(c, Not)
        assert isinstance(c.condition, Equals)

    def test_any(self):
        c = parse_condition({
            "any": [
                {"equals": {"question_id": "a", "value": "1"}},
                {"equals": {"question_id": "b", "value": "2"}},
            ]
        })
        assert isinstance(c, Any)
        assert len(c.conditions) == 2

    def test_all(self):
        c = parse_condition({
            "all": [
                {"equals": {"question_id": "a", "value": "1"}},
                {"equals": {"question_id": "b", "value": "2"}},
            ]
        })
        assert isinstance(c, All)
        assert len(c.conditions) == 2

    def test_nested_any_containing_all(self):
        c = parse_condition({
            "any": [
                {"all": [
                    {"equals": {"question_id": "a", "value": "1"}},
                    {"equals": {"question_id": "b", "value": "2"}},
                ]},
                {"equals": {"question_id": "c", "value": "3"}},
            ]
        })
        assert isinstance(c, Any)
        assert isinstance(c.conditions[0], All)

    def test_empty_dict_raises(self):
        with pytest.raises(ValueError, match="exactly one key"):
            parse_condition({})

    def test_multiple_keys_raises(self):
        with pytest.raises(ValueError, match="exactly one key"):
            parse_condition({"equals": {}, "not": {}})

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unknown condition"):
            parse_condition({"xor": {}})


# ---------------------------------------------------------------------------
# parse_question
# ---------------------------------------------------------------------------


class TestParseQuestion:
    def test_yes_no(self):
        q = parse_question({"type": "yes_no", "id": "q1", "text": "Risky?"})
        assert isinstance(q, YesNoQuestion)
        assert q.id == "q1"

    def test_free_text(self):
        q = parse_question({"type": "free_text", "id": "q2", "text": "Describe"})
        assert isinstance(q, FreeTextQuestion)

    def test_multiple_choice(self):
        q = parse_question({
            "type": "multiple_choice",
            "id": "q3",
            "text": "Pick",
            "options": ["a", "b"],
        })
        assert isinstance(q, MultipleChoiceQuestion)
        assert q.options == ("a", "b")

    def test_multiple_select(self):
        q = parse_question({
            "type": "multiple_select",
            "id": "q4",
            "text": "Pick many",
            "options": ["x", "y"],
        })
        assert isinstance(q, MultipleSelectQuestion)

    def test_guidance(self):
        q = parse_question({
            "type": "yes_no",
            "id": "q1",
            "text": "Q",
            "guidance": "Some help text",
        })
        assert q.guidance == "Some help text"

    def test_visible_when(self):
        q = parse_question({
            "type": "yes_no",
            "id": "q1",
            "text": "Q",
            "visible_when": {"equals": {"question_id": "q0", "value": "yes"}},
        })
        assert q.visible_when is not None
        assert isinstance(q.visible_when, Equals)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown question type"):
            parse_question({"type": "slider", "id": "q1", "text": "Q"})


# ---------------------------------------------------------------------------
# parse_rule
# ---------------------------------------------------------------------------


class TestParseRule:
    def test_any_yes(self):
        r = parse_rule({
            "type": "any_yes",
            "question_ids": ["q1", "q2"],
            "likelihood": "likely",
        })
        assert isinstance(r, AnyYesRule)
        assert r.question_ids == ("q1", "q2")
        assert r.likelihood == "likely"
        assert r.consequence is None

    def test_count_yes(self):
        r = parse_rule({
            "type": "count_yes",
            "question_ids": ["q1"],
            "threshold": 1,
            "consequence": "major",
        })
        assert isinstance(r, CountYesRule)
        assert r.threshold == 1

    def test_choice_map(self):
        r = parse_rule({
            "type": "choice_map",
            "question_id": "q1",
            "mapping": {"a": {"likelihood": "rare"}},
        })
        assert isinstance(r, ChoiceMapRule)

    def test_contains_any(self):
        r = parse_rule({
            "type": "contains_any",
            "question_id": "q1",
            "values": ["a", "b"],
            "likelihood": "possible",
        })
        assert isinstance(r, ContainsAnyRule)
        assert r.values == ("a", "b")

    def test_contains_any_bool_values(self):
        """YAML parses bare `true`/`false` as bools — _ensure_str should fix."""
        r = parse_rule({
            "type": "contains_any",
            "question_id": "q1",
            "values": [True, False],
            "likelihood": "possible",
        })
        assert r.values == ("yes", "no")

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown rule type"):
            parse_rule({"type": "magic", "question_id": "q1"})


# ---------------------------------------------------------------------------
# parse_subsection / parse_section
# ---------------------------------------------------------------------------


class TestParseSubsection:
    def test_basic(self):
        sub = parse_subsection({
            "title": "Basics",
            "description": "Basic stuff",
            "questions": [
                {"type": "yes_no", "id": "q1", "text": "Q1"},
            ],
        })
        assert sub.title == "Basics"
        assert len(sub.questions) == 1
        assert sub.visible_when is None

    def test_with_visible_when(self):
        sub = parse_subsection({
            "title": "Conditional",
            "description": "Shows conditionally",
            "questions": [
                {"type": "yes_no", "id": "q1", "text": "Q1"},
            ],
            "visible_when": {"equals": {"question_id": "q0", "value": "yes"}},
        })
        assert sub.visible_when is not None


class TestParseSection:
    def test_roundtrip(self):
        sec = parse_section({
            "id": "s1",
            "title": "Section 1",
            "description": "First section",
            "subsections": [
                {
                    "title": "Sub A",
                    "description": "Sub A desc",
                    "questions": [
                        {"type": "yes_no", "id": "q1", "text": "Q1"},
                        {"type": "free_text", "id": "q2", "text": "Q2"},
                    ],
                }
            ],
        })
        assert sec.id == "s1"
        assert len(sec.subsections) == 1
        assert len(sec.subsections[0].questions) == 2


# ---------------------------------------------------------------------------
# parse_risk / parse_control
# ---------------------------------------------------------------------------


class TestParseRisk:
    def test_happy_path(self):
        r = parse_risk({
            "id": "r1",
            "name": "Breach",
            "description": "Data breach risk",
            "rules": [
                {"type": "any_yes", "question_ids": ["q1"], "likelihood": "likely"},
            ],
        })
        assert r.id == "r1"
        assert r.default_likelihood == "rare"  # default
        assert r.default_consequence == "minor"  # default

    def test_custom_defaults(self):
        r = parse_risk({
            "id": "r1",
            "name": "R",
            "description": "D",
            "rules": [
                {"type": "any_yes", "question_ids": ["q1"], "consequence": "major"},
            ],
            "default_likelihood": "possible",
            "default_consequence": "major",
        })
        assert r.default_likelihood == "possible"
        assert r.default_consequence == "major"


class TestParseControlEffect:
    def test_basic(self):
        e = parse_control_effect({
            "risk_id": "r1",
            "reduces_likelihood": True,
        })
        assert isinstance(e, ControlEffect)
        assert e.reduces_likelihood
        assert not e.reduces_consequence

    def test_defaults_to_false(self):
        e = parse_control_effect({
            "risk_id": "r1",
            "reduces_consequence": True,
        })
        assert not e.reduces_likelihood
        assert e.reduces_consequence


class TestParseControl:
    def test_happy_path(self):
        ctrl = parse_control({
            "id": "c1",
            "name": "Encryption",
            "question_id": "q1",
            "present_value": True,
            "effects": [
                {"risk_id": "r1", "reduces_likelihood": True},
            ],
        })
        assert isinstance(ctrl, Control)
        assert ctrl.present_value == "yes"  # _ensure_str applied
        assert len(ctrl.effects) == 1
