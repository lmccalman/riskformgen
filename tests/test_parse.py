"""Tests for parse.py — YAML dict → dataclass parsing."""

from __future__ import annotations

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
)
from parse import (
    _ensure_str,
    parse_control,
    parse_control_effect,
    parse_property,
    parse_question,
    parse_risk,
    parse_rule,
    parse_section,
    parse_subsection,
    validate_property_dag,
    validate_question_properties,
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
# parse_question
# ---------------------------------------------------------------------------


class TestParseQuestion:
    def test_binary(self):
        q = parse_question(
            {"type": "binary", "id": "q1", "text": "Risky?", "properties": ["p1", "p2"]}
        )
        assert isinstance(q, BinaryQuestion)
        assert q.id == "q1"
        assert q.properties == ("p1", "p2")

    def test_binary_no_properties(self):
        q = parse_question({"type": "binary", "id": "q1", "text": "Q"})
        assert isinstance(q, BinaryQuestion)
        assert q.properties == ()

    def test_guidance(self):
        q = parse_question(
            {
                "type": "binary",
                "id": "q1",
                "text": "Q",
                "properties": ["p1"],
                "guidance": "Some help text",
            }
        )
        assert q.guidance == "Some help text"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown question type"):
            parse_question({"type": "slider", "id": "q1", "text": "Q"})

    def test_old_types_raise(self):
        for old_type in ["yes_no", "free_text", "multiple_choice", "multiple_select"]:
            with pytest.raises(ValueError, match="Unknown question type"):
                parse_question({"type": old_type, "id": "q1", "text": "Q"})


# ---------------------------------------------------------------------------
# parse_rule
# ---------------------------------------------------------------------------


class TestParseRule:
    def test_any_yes(self):
        r = parse_rule(
            {
                "type": "any_yes",
                "question_ids": ["q1", "q2"],
                "likelihood": "likely",
            }
        )
        assert isinstance(r, AnyYesRule)
        assert r.question_ids == ("q1", "q2")
        assert r.likelihood == "likely"
        assert r.consequence is None

    def test_count_yes(self):
        r = parse_rule(
            {
                "type": "count_yes",
                "question_ids": ["q1"],
                "threshold": 1,
                "consequence": "major",
            }
        )
        assert isinstance(r, CountYesRule)
        assert r.threshold == 1

    def test_choice_map(self):
        r = parse_rule(
            {
                "type": "choice_map",
                "question_id": "q1",
                "mapping": {"a": {"likelihood": "rare"}},
            }
        )
        assert isinstance(r, ChoiceMapRule)

    def test_contains_any(self):
        r = parse_rule(
            {
                "type": "contains_any",
                "question_id": "q1",
                "values": ["a", "b"],
                "likelihood": "possible",
            }
        )
        assert isinstance(r, ContainsAnyRule)
        assert r.values == ("a", "b")

    def test_contains_any_bool_values(self):
        """YAML parses bare `true`/`false` as bools — _ensure_str should fix."""
        r = parse_rule(
            {
                "type": "contains_any",
                "question_id": "q1",
                "values": [True, False],
                "likelihood": "possible",
            }
        )
        assert isinstance(r, ContainsAnyRule)
        assert r.values == ("yes", "no")

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown rule type"):
            parse_rule({"type": "magic", "question_id": "q1"})


# ---------------------------------------------------------------------------
# parse_subsection / parse_section
# ---------------------------------------------------------------------------


class TestParseSubsection:
    def test_basic(self):
        sub = parse_subsection(
            {
                "title": "Basics",
                "description": "Basic stuff",
                "questions": [
                    {"type": "binary", "id": "q1", "text": "Q1", "properties": ["p1"]},
                ],
            }
        )
        assert sub.title == "Basics"
        assert len(sub.questions) == 1


class TestParseSection:
    def test_roundtrip(self):
        sec = parse_section(
            {
                "id": "s1",
                "title": "Section 1",
                "description": "First section",
                "subsections": [
                    {
                        "title": "Sub A",
                        "description": "Sub A desc",
                        "questions": [
                            {"type": "binary", "id": "q1", "text": "Q1", "properties": ["p1"]},
                            {"type": "binary", "id": "q2", "text": "Q2"},
                        ],
                    }
                ],
            }
        )
        assert sec.id == "s1"
        assert len(sec.subsections) == 1
        assert len(sec.subsections[0].questions) == 2


# ---------------------------------------------------------------------------
# parse_risk / parse_control
# ---------------------------------------------------------------------------


class TestParseRisk:
    def test_happy_path(self):
        r = parse_risk(
            {
                "id": "r1",
                "name": "Breach",
                "description": "Data breach risk",
                "rules": [
                    {"type": "any_yes", "question_ids": ["q1"], "likelihood": "likely"},
                ],
            }
        )
        assert r.id == "r1"
        assert r.default_likelihood == "rare"  # default
        assert r.default_consequence == "minor"  # default

    def test_custom_defaults(self):
        r = parse_risk(
            {
                "id": "r1",
                "name": "R",
                "description": "D",
                "rules": [
                    {"type": "any_yes", "question_ids": ["q1"], "consequence": "major"},
                ],
                "default_likelihood": "possible",
                "default_consequence": "major",
            }
        )
        assert r.default_likelihood == "possible"
        assert r.default_consequence == "major"


class TestParseControlEffect:
    def test_basic(self):
        e = parse_control_effect(
            {
                "risk_id": "r1",
                "reduces_likelihood": True,
            }
        )
        assert isinstance(e, ControlEffect)
        assert e.reduces_likelihood
        assert not e.reduces_consequence

    def test_defaults_to_false(self):
        e = parse_control_effect(
            {
                "risk_id": "r1",
                "reduces_consequence": True,
            }
        )
        assert not e.reduces_likelihood
        assert e.reduces_consequence


class TestParseControl:
    def test_happy_path(self):
        ctrl = parse_control(
            {
                "id": "c1",
                "name": "Encryption",
                "question_id": "q1",
                "present_value": True,
                "effects": [
                    {"risk_id": "r1", "reduces_likelihood": True},
                ],
            }
        )
        assert isinstance(ctrl, Control)
        assert ctrl.present_value == "yes"  # _ensure_str applied
        assert len(ctrl.effects) == 1


# ---------------------------------------------------------------------------
# parse_property / validate_property_dag / validate_question_properties
# ---------------------------------------------------------------------------


class TestParseProperty:
    def test_with_parents(self):
        p = parse_property(
            {"id": "handles_pii", "description": "Handles PII", "parents": ["handles_data"]}
        )
        assert isinstance(p, Property)
        assert p.id == "handles_pii"
        assert p.parents == ("handles_data",)
        assert p.activation == "all"

    def test_without_parents(self):
        p = parse_property({"id": "handles_data", "description": "Handles data"})
        assert isinstance(p, Property)
        assert p.parents == ()

    def test_any_activation(self):
        p = parse_property(
            {
                "id": "flexible",
                "description": "Flexible",
                "parents": ["a", "b"],
                "activation": "any",
            }
        )
        assert p.activation == "any"


class TestValidatePropertyDag:
    def test_valid_dag(self):
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
            Property(id="grandchild", description="Grandchild", parents=("child",)),
        ]
        validate_property_dag(props)  # should not raise

    def test_duplicate_id_raises(self):
        props = [
            Property(id="a", description="First"),
            Property(id="a", description="Second"),
        ]
        with pytest.raises(ValueError, match="Duplicate property ID"):
            validate_property_dag(props)

    def test_unknown_parent_raises(self):
        props = [
            Property(id="child", description="Child", parents=("missing",)),
        ]
        with pytest.raises(ValueError, match="unknown parent"):
            validate_property_dag(props)

    def test_cycle_raises(self):
        props = [
            Property(id="a", description="A", parents=("b",)),
            Property(id="b", description="B", parents=("a",)),
        ]
        with pytest.raises(ValueError, match="cycle"):
            validate_property_dag(props)

    def test_self_cycle_raises(self):
        props = [
            Property(id="a", description="A", parents=("a",)),
        ]
        with pytest.raises(ValueError, match="cycle"):
            validate_property_dag(props)


class TestValidateQuestionProperties:
    def test_valid(self):
        props = [Property(id="p1", description="P1")]
        questions = [BinaryQuestion(id="q1", text="Q", properties=("p1",))]
        validate_question_properties(questions, props)  # should not raise

    def test_unknown_property_raises(self):
        props = [Property(id="p1", description="P1")]
        questions = [BinaryQuestion(id="q1", text="Q", properties=("p_missing",))]
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_question_properties(questions, props)

    def test_duplicate_setter_raises(self):
        props = [Property(id="p1", description="P1")]
        questions = [
            BinaryQuestion(id="q1", text="Q1", properties=("p1",)),
            BinaryQuestion(id="q2", text="Q2", properties=("p1",)),
        ]
        with pytest.raises(ValueError, match="set by both"):
            validate_question_properties(questions, props)

    def test_no_setter_is_fine(self):
        props = [Property(id="p1", description="P1")]
        questions: list[BinaryQuestion] = []
        validate_question_properties(questions, props)  # should not raise

    def test_multiple_errors_reported(self):
        props = [Property(id="p1", description="P1")]
        questions = [
            BinaryQuestion(id="q1", text="Q1", properties=("p_bad1",)),
            BinaryQuestion(id="q2", text="Q2", properties=("p_bad2",)),
        ]
        with pytest.raises(ValueError, match="p_bad1") as exc_info:
            validate_question_properties(questions, props)
        assert "p_bad2" in str(exc_info.value)
