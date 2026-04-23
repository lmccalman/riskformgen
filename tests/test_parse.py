"""Tests for parse.py — YAML dict → dataclass parsing."""

from __future__ import annotations

import pytest

from models import (
    BinaryQuestion,
    ConditionMapping,
    Control,
    ControlEffect,
    Detail,
    DetailQuestion,
    Property,
    Risk,
)
from parse import (
    _ensure_str,
    parse_condition_mapping,
    parse_control,
    parse_control_effect,
    parse_detail,
    parse_property,
    parse_question,
    parse_risk,
    parse_section,
    parse_subsection,
    validate_control_properties,
    validate_control_risk_ids,
    validate_detail_properties,
    validate_detail_questions,
    validate_property_dag,
    validate_question_properties,
    validate_risk_properties,
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


class TestParseDetail:
    def test_basic(self):
        d = parse_detail({"id": "det1", "description": "Outdoor context", "properties": ["p1"]})
        assert isinstance(d, Detail)
        assert d.id == "det1"
        assert d.description == "Outdoor context"
        assert d.properties == ("p1",)

    def test_no_properties(self):
        d = parse_detail({"id": "det1", "description": "No props"})
        assert d.properties == ()


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

    def test_detail_type(self):
        det = Detail(id="det1", description="Context", properties=("p1",))
        q = parse_question(
            {"type": "detail", "id": "q_det", "text": "Describe", "detail_id": "det1"},
            details_by_id={"det1": det},
        )
        assert isinstance(q, DetailQuestion)
        assert q.detail_id == "det1"
        assert q.properties == ("p1",)

    def test_detail_guidance(self):
        det = Detail(id="det1", description="Context", properties=("p1",))
        q = parse_question(
            {
                "type": "detail",
                "id": "q_det",
                "text": "Describe",
                "detail_id": "det1",
                "guidance": "Help text",
            },
            details_by_id={"det1": det},
        )
        assert isinstance(q, DetailQuestion)
        assert q.guidance == "Help text"

    def test_detail_unknown_detail_raises(self):
        with pytest.raises(ValueError, match="unknown detail"):
            parse_question(
                {"type": "detail", "id": "q_det", "text": "D", "detail_id": "missing"},
                details_by_id={},
            )

    def test_detail_no_details_by_id_raises(self):
        with pytest.raises(ValueError, match="unknown detail"):
            parse_question({"type": "detail", "id": "q_det", "text": "D", "detail_id": "det1"})

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown question type"):
            parse_question({"type": "slider", "id": "q1", "text": "Q"})

    def test_old_types_raise(self):
        for old_type in ["yes_no", "free_text", "multiple_choice", "multiple_select"]:
            with pytest.raises(ValueError, match="Unknown question type"):
                parse_question({"type": old_type, "id": "q1", "text": "Q"})


# ---------------------------------------------------------------------------
# parse_condition_mapping / parse_risk
# ---------------------------------------------------------------------------


class TestParseConditionMapping:
    def test_basic(self):
        cond = parse_condition_mapping(
            {
                "properties": ["p1", "p2"],
                "mode": "any",
                "likelihood": "likely",
                "consequence": "major",
            }
        )
        assert isinstance(cond, ConditionMapping)
        assert cond.properties == ("p1", "p2")
        assert cond.mode == "any"
        assert cond.likelihood == "likely"
        assert cond.consequence == "major"

    def test_mode_defaults_to_all(self):
        cond = parse_condition_mapping(
            {"properties": ["p1"], "likelihood": "rare", "consequence": "minor"}
        )
        assert cond.mode == "all"


class TestParseRisk:
    def test_happy_path(self):
        r = parse_risk(
            {
                "id": "r1",
                "description": "Data breach risk",
                "conditions": [
                    {
                        "properties": ["p1"],
                        "mode": "all",
                        "likelihood": "likely",
                        "consequence": "major",
                    }
                ],
            }
        )
        assert isinstance(r, Risk)
        assert r.id == "r1"
        assert r.description == "Data breach risk"
        assert len(r.conditions) == 1

    def test_multiple_conditions(self):
        r = parse_risk(
            {
                "id": "r1",
                "description": "D",
                "conditions": [
                    {"properties": ["p1"], "likelihood": "likely", "consequence": "major"},
                    {
                        "properties": ["p2", "p3"],
                        "mode": "any",
                        "likelihood": "rare",
                        "consequence": "minor",
                    },
                ],
            }
        )
        assert len(r.conditions) == 2
        assert r.conditions[1].mode == "any"


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
# parse_control
# ---------------------------------------------------------------------------


class TestParseControlEffect:
    def test_basic(self):
        e = parse_control_effect({"risk_id": "r1"})
        assert isinstance(e, ControlEffect)
        assert e.risk_id == "r1"


class TestParseControl:
    def test_happy_path(self):
        ctrl = parse_control(
            {
                "id": "c1",
                "description": "Encryption enabled",
                "property": "encrypted",
                "effects": [
                    {"risk_id": "r1"},
                ],
            }
        )
        assert isinstance(ctrl, Control)
        assert ctrl.description == "Encryption enabled"
        assert ctrl.property == "encrypted"
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
        questions = []
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

    def test_detail_question_does_not_trigger_setter_conflict(self):
        """DetailQuestions sharing a property with BinaryQuestions should not conflict."""
        props = [Property(id="p1", description="P1")]
        questions = [
            BinaryQuestion(id="q1", text="Q1", properties=("p1",)),
            DetailQuestion(id="q_det", text="Describe", detail_id="det1", properties=("p1",)),
        ]
        validate_question_properties(questions, props)  # should not raise

    def test_detail_question_unknown_property_raises(self):
        props = [Property(id="p1", description="P1")]
        questions = [
            DetailQuestion(id="q_det", text="D", detail_id="det1", properties=("p_missing",)),
        ]
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_question_properties(questions, props)


class TestValidateDetailProperties:
    def test_valid(self):
        props = [Property(id="p1", description="P1")]
        details = [Detail(id="det1", description="D", properties=("p1",))]
        validate_detail_properties(details, props)  # should not raise

    def test_unknown_property_raises(self):
        props = [Property(id="p1", description="P1")]
        details = [Detail(id="det1", description="D", properties=("p_missing",))]
        with pytest.raises(ValueError, match="p_missing"):
            validate_detail_properties(details, props)

    def test_empty_details_pass(self):
        props = [Property(id="p1", description="P1")]
        validate_detail_properties([], props)  # should not raise


class TestValidateDetailQuestions:
    def test_valid(self):
        details = [Detail(id="det1", description="D", properties=("p1",))]
        questions = [DetailQuestion(id="q_det", text="D", detail_id="det1", properties=("p1",))]
        validate_detail_questions(questions, details)  # should not raise

    def test_unknown_detail_raises(self):
        questions = [DetailQuestion(id="q_det", text="D", detail_id="missing", properties=())]
        with pytest.raises(ValueError, match="missing"):
            validate_detail_questions(questions, [])

    def test_binary_questions_ignored(self):
        questions = [BinaryQuestion(id="q1", text="Q", properties=("p1",))]
        validate_detail_questions(questions, [])  # should not raise


# ---------------------------------------------------------------------------
# validate_risk_properties
# ---------------------------------------------------------------------------


class TestValidateRiskProperties:
    def test_valid(self):
        props = [Property(id="p1", description="P1")]
        risks = [
            Risk(
                id="r1",
                description="D",
                conditions=(
                    ConditionMapping(
                        properties=("p1",), mode="all", likelihood="rare", consequence="minor"
                    ),
                ),
            )
        ]
        validate_risk_properties(risks, props)  # should not raise

    def test_unknown_property_raises(self):
        props = [Property(id="p1", description="P1")]
        risks = [
            Risk(
                id="r1",
                description="D",
                conditions=(
                    ConditionMapping(
                        properties=("p_missing",),
                        mode="all",
                        likelihood="rare",
                        consequence="minor",
                    ),
                ),
            )
        ]
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_risk_properties(risks, props)

    def test_multiple_errors_reported(self):
        props = [Property(id="p1", description="P1")]
        risks = [
            Risk(
                id="r1",
                description="D",
                conditions=(
                    ConditionMapping(
                        properties=("bad1",), mode="all", likelihood="rare", consequence="minor"
                    ),
                    ConditionMapping(
                        properties=("bad2",), mode="all", likelihood="rare", consequence="minor"
                    ),
                ),
            )
        ]
        with pytest.raises(ValueError, match="bad1") as exc_info:
            validate_risk_properties(risks, props)
        assert "bad2" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate_control_properties / validate_control_risk_ids
# ---------------------------------------------------------------------------


class TestValidateControlProperties:
    def test_valid(self):
        props = [Property(id="p1", description="P1")]
        controls = [
            Control(
                id="c1",
                description="C",
                property="p1",
                effects=(ControlEffect(risk_id="r1"),),
            )
        ]
        validate_control_properties(controls, props)  # should not raise

    def test_unknown_property_raises(self):
        props = [Property(id="p1", description="P1")]
        controls = [
            Control(
                id="c1",
                description="C",
                property="p_missing",
                effects=(ControlEffect(risk_id="r1"),),
            )
        ]
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_control_properties(controls, props)

    def test_multiple_errors_reported(self):
        props = [Property(id="p1", description="P1")]
        controls = [
            Control(
                id="c1",
                description="C1",
                property="bad1",
                effects=(ControlEffect(risk_id="r1"),),
            ),
            Control(
                id="c2",
                description="C2",
                property="bad2",
                effects=(ControlEffect(risk_id="r1"),),
            ),
        ]
        with pytest.raises(ValueError, match="bad1") as exc_info:
            validate_control_properties(controls, props)
        assert "bad2" in str(exc_info.value)

    def test_empty_controls_pass(self):
        props = [Property(id="p1", description="P1")]
        validate_control_properties([], props)  # should not raise


class TestValidateControlRiskIds:
    def test_valid(self):
        risks = [
            Risk(
                id="r1",
                description="D",
                conditions=(
                    ConditionMapping(
                        properties=("p1",), mode="all", likelihood="rare", consequence="minor"
                    ),
                ),
            )
        ]
        controls = [
            Control(
                id="c1",
                description="C",
                property="p1",
                effects=(ControlEffect(risk_id="r1"),),
            )
        ]
        validate_control_risk_ids(controls, risks)  # should not raise

    def test_unknown_risk_raises(self):
        risks = [
            Risk(
                id="r1",
                description="D",
                conditions=(
                    ConditionMapping(
                        properties=("p1",), mode="all", likelihood="rare", consequence="minor"
                    ),
                ),
            )
        ]
        controls = [
            Control(
                id="c1",
                description="C",
                property="p1",
                effects=(ControlEffect(risk_id="r_missing"),),
            )
        ]
        with pytest.raises(ValueError, match="unknown risk 'r_missing'"):
            validate_control_risk_ids(controls, risks)

    def test_empty_controls_pass(self):
        validate_control_risk_ids([], [])  # should not raise
