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
    Section,
    SubSection,
)
from parse import (
    _validate_id,
    parse_condition_mapping,
    parse_control,
    parse_control_effect,
    parse_detail,
    parse_property,
    parse_question,
    parse_risk,
    parse_section,
    parse_subsection,
    validate_all,
    validate_control_properties,
    validate_control_risk_ids,
    validate_detail_properties,
    validate_detail_questions,
    validate_id_namespaces,
    validate_property_dag,
    validate_question_properties,
    validate_risk_properties,
)

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


# ---------------------------------------------------------------------------
# parse_condition_mapping / parse_risk
# ---------------------------------------------------------------------------


class TestParseConditionMapping:
    def test_basic(self):
        cond = parse_condition_mapping(
            {
                "property": "p1",
                "likelihood": "likely",
                "consequence": "major",
            }
        )
        assert isinstance(cond, ConditionMapping)
        assert cond.property == "p1"
        assert cond.likelihood == "likely"
        assert cond.consequence == "major"

    def test_rejects_legacy_multi_property_shape(self):
        with pytest.raises(ValueError):
            parse_condition_mapping(
                {
                    "properties": ["p1", "p2"],
                    "mode": "any",
                    "likelihood": "likely",
                    "consequence": "major",
                }
            )

    def test_invalid_likelihood_raises(self):
        with pytest.raises(ValueError, match="Invalid likelihood 'liekly'"):
            parse_condition_mapping(
                {"property": "p1", "likelihood": "liekly", "consequence": "major"}
            )

    def test_invalid_consequence_raises(self):
        with pytest.raises(ValueError, match="Invalid consequence 'sever'"):
            parse_condition_mapping(
                {"property": "p1", "likelihood": "likely", "consequence": "sever"}
            )


class TestParseRisk:
    def test_happy_path(self):
        r = parse_risk(
            {
                "id": "r1",
                "description": "Data breach risk",
                "conditions": [
                    {
                        "property": "p1",
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
                    {"property": "p1", "likelihood": "likely", "consequence": "major"},
                    {"property": "p2", "likelihood": "rare", "consequence": "minor"},
                ],
            }
        )
        assert len(r.conditions) == 2
        assert r.conditions[0].property == "p1"
        assert r.conditions[1].property == "p2"

    def test_guidance(self):
        r = parse_risk(
            {
                "id": "r1",
                "description": "D",
                "conditions": [],
                "guidance": "Discuss this with the risk manager.",
            }
        )
        assert r.guidance == "Discuss this with the risk manager."

    def test_guidance_optional(self):
        r = parse_risk({"id": "r1", "description": "D", "conditions": []})
        assert r.guidance is None


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

    def test_multiple_errors_reported(self):
        props = [
            Property(id="dup", description="First"),
            Property(id="dup", description="Second"),
            Property(id="orphan", description="O", parents=("missing",)),
            Property(id="lone", description="L", parents=("also_missing",)),
        ]
        with pytest.raises(ValueError, match="Duplicate") as exc_info:
            validate_property_dag(props)
        msg = str(exc_info.value)
        assert "dup" in msg
        assert "missing" in msg
        assert "also_missing" in msg


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
                    ConditionMapping(property="p1", likelihood="rare", consequence="minor"),
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
                        property="p_missing",
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
                    ConditionMapping(property="bad1", likelihood="rare", consequence="minor"),
                    ConditionMapping(property="bad2", likelihood="rare", consequence="minor"),
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
                    ConditionMapping(property="p1", likelihood="rare", consequence="minor"),
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
                    ConditionMapping(property="p1", likelihood="rare", consequence="minor"),
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


# ---------------------------------------------------------------------------
# _validate_id
# ---------------------------------------------------------------------------


class TestValidateId:
    @pytest.mark.parametrize("good", ["foo", "foo_bar", "_foo", "Foo123", "a"])
    def test_valid_ids_pass(self, good):
        _validate_id(good, kind="property")  # should not raise

    @pytest.mark.parametrize(
        "bad",
        [
            "my-risk",  # hyphen
            "2fa_required",  # leading digit
            "",  # empty
            "foo bar",  # space
            "foo.bar",  # dot
            "foo$bar",  # dollar sign (legal JS but we don't allow it)
            "café",  # non-ASCII
        ],
    )
    def test_invalid_shape_raises(self, bad):
        with pytest.raises(ValueError, match="Invalid id"):
            _validate_id(bad, kind="property")

    @pytest.mark.parametrize("reserved", ["class", "return", "new", "this", "null"])
    def test_reserved_words_raise(self, reserved):
        with pytest.raises(ValueError, match="reserved word"):
            _validate_id(reserved, kind="risk")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="Invalid id"):
            _validate_id(123, kind="property")

    def test_error_mentions_kind(self):
        with pytest.raises(ValueError, match="risk"):
            _validate_id("bad-id", kind="risk")


# ---------------------------------------------------------------------------
# Per-parse_* bad-id cases
# ---------------------------------------------------------------------------


class TestParseBadIds:
    """Spot-check that each parse_* function actually calls _validate_id."""

    def test_parse_property_bad_id(self):
        with pytest.raises(ValueError, match="Invalid id"):
            parse_property({"id": "bad-id", "description": "X"})

    def test_parse_detail_bad_id(self):
        with pytest.raises(ValueError, match="Invalid id"):
            parse_detail({"id": "2bad", "description": "X"})

    def test_parse_binary_question_bad_id(self):
        with pytest.raises(ValueError, match="Invalid id"):
            parse_question({"type": "binary", "id": "bad id", "text": "Q"})

    def test_parse_detail_question_bad_id(self):
        det = Detail(id="det1", description="D", properties=())
        with pytest.raises(ValueError, match="Invalid id"):
            parse_question(
                {"type": "detail", "id": "bad-q", "text": "Q", "detail_id": "det1"},
                details_by_id={"det1": det},
            )

    def test_parse_section_bad_id(self):
        with pytest.raises(ValueError, match="Invalid id"):
            parse_section(
                {
                    "id": "bad-section",
                    "title": "T",
                    "description": "D",
                    "subsections": [],
                }
            )

    def test_parse_risk_bad_id(self):
        with pytest.raises(ValueError, match="Invalid id"):
            parse_risk({"id": "bad-risk", "description": "D", "conditions": []})

    def test_parse_control_bad_id(self):
        with pytest.raises(ValueError, match="Invalid id"):
            parse_control({"id": "bad-ctrl", "description": "D", "property": "p1", "effects": []})


# ---------------------------------------------------------------------------
# validate_id_namespaces
# ---------------------------------------------------------------------------


def _risk(rid: str) -> Risk:
    return Risk(
        id=rid,
        description="D",
        conditions=(ConditionMapping(property="p1", likelihood="rare", consequence="minor"),),
    )


def _section(sid: str, question_ids: tuple[str, ...] = ()) -> Section:
    return Section(
        id=sid,
        title="T",
        description="D",
        subsections=(
            SubSection(
                title="Sub",
                description="D",
                questions=tuple(
                    BinaryQuestion(id=qid, text="Q", properties=()) for qid in question_ids
                ),
            ),
        ),
    )


class TestValidateIdNamespaces:
    def test_valid(self):
        validate_id_namespaces(
            sections=[_section("s1", ("q1",))],
            properties=[Property(id="p1", description="P")],
            risks=[_risk("r1")],
            controls=[Control(id="c1", description="C", property="p1", effects=())],
            details=[Detail(id="d1", description="D", properties=())],
        )  # should not raise

    def test_risk_collides_with_state_field(self):
        with pytest.raises(ValueError, match="reserved Alpine scope name"):
            validate_id_namespaces(
                sections=[],
                properties=[],
                risks=[_risk("answers")],
                controls=[],
                details=[],
            )

    def test_risk_collides_with_helper_method(self):
        with pytest.raises(ValueError, match="reserved Alpine scope name"):
            validate_id_namespaces(
                sections=[],
                properties=[],
                risks=[_risk("_worst")],
                controls=[],
                details=[],
            )

    def test_risk_residual_collides_with_state_field(self):
        # "control_effectiveness_residual" isn't a real state name, so this
        # checks the other direction: a risk id whose `_residual` sibling
        # would collide with a different risk id.
        with pytest.raises(ValueError, match="collides with"):
            validate_id_namespaces(
                sections=[],
                properties=[],
                risks=[_risk("foo"), _risk("foo_residual")],
                controls=[],
                details=[],
            )

    def test_cross_namespace_collision(self):
        with pytest.raises(ValueError, match="unique across namespaces"):
            validate_id_namespaces(
                sections=[],
                properties=[Property(id="shared", description="P")],
                risks=[],
                controls=[Control(id="shared", description="C", property="shared", effects=())],
                details=[],
            )

    def test_multiple_errors_reported(self):
        with pytest.raises(ValueError, match="answers") as exc_info:
            validate_id_namespaces(
                sections=[],
                properties=[Property(id="dup", description="P")],
                risks=[_risk("answers"), _risk("details")],
                controls=[Control(id="dup", description="C", property="dup", effects=())],
                details=[],
            )
        msg = str(exc_info.value)
        assert "details" in msg
        assert "unique across namespaces" in msg


class TestUnknownKeys:
    """Each parser should reject unknown YAML keys so typos surface at load time."""

    def test_property_typo(self):
        with pytest.raises(ValueError, match="descripton"):
            parse_property({"id": "p1", "descripton": "typo"})

    def test_detail_typo(self):
        with pytest.raises(ValueError, match="guidelines"):
            parse_detail({"id": "d1", "description": "ok", "guidelines": "nope"})

    def test_binary_question_typo(self):
        with pytest.raises(ValueError, match="guidelines"):
            parse_question({"type": "binary", "id": "q1", "text": "Q", "guidelines": "nope"})

    def test_detail_question_typo(self):
        # `properties` is derived from the referenced Detail, so supplying it
        # on the question itself is a mistake and should be flagged.
        with pytest.raises(ValueError, match="properties"):
            parse_question(
                {
                    "type": "detail",
                    "id": "q1",
                    "text": "Q",
                    "detail_id": "d1",
                    "properties": ["p1"],
                },
                details_by_id={"d1": Detail(id="d1", description="D", properties=("p1",))},
            )

    def test_subsection_typo(self):
        with pytest.raises(ValueError, match="heading"):
            parse_subsection({"heading": "oops", "description": "ok", "questions": []})

    def test_section_typo(self):
        with pytest.raises(ValueError, match="subsection"):
            parse_section(
                {
                    "id": "s1",
                    "title": "T",
                    "description": "D",
                    "subsection": [],  # should be "subsections"
                }
            )

    def test_condition_mapping_typo(self):
        with pytest.raises(ValueError, match="likelyhood"):
            parse_condition_mapping(
                {
                    "property": "p1",
                    "likelyhood": "low",  # typo
                    "consequence": "minor",
                }
            )

    def test_risk_typo(self):
        with pytest.raises(ValueError, match="condition"):
            parse_risk({"id": "r1", "description": "R", "condition": []})

    def test_control_effect_typo(self):
        with pytest.raises(ValueError, match="risk"):
            parse_control_effect({"risk": "r1"})  # should be "risk_id"

    def test_control_typo(self):
        with pytest.raises(ValueError, match="effect"):
            parse_control(
                {
                    "id": "c1",
                    "description": "C",
                    "property": "p1",
                    "effect": [],  # should be "effects"
                }
            )


# ---------------------------------------------------------------------------
# validate_all — orchestrator
# ---------------------------------------------------------------------------


class TestValidateAll:
    """`validate_all` is the single entry point used by `main.main()`. Its
    job is to surface the first invariant violation before render. Each
    constituent validator has its own tests above; here we pin the
    orchestration: a happy path passes, and a violation in any one
    constituent is propagated."""

    def _good_inputs(self):
        section = Section(
            id="s1",
            title="T",
            description="D",
            subsections=(
                SubSection(
                    title="Sub",
                    description="D",
                    questions=(
                        BinaryQuestion(id="q1", text="Q", properties=("p1",)),
                        DetailQuestion(id="q_det", text="D", detail_id="d1", properties=("p1",)),
                    ),
                ),
            ),
        )
        properties = [Property(id="p1", description="P1")]
        risks = [
            Risk(
                id="r1",
                description="R",
                conditions=(
                    ConditionMapping(property="p1", likelihood="rare", consequence="minor"),
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
        details = [Detail(id="d1", description="D", properties=("p1",))]
        return section, properties, risks, controls, details

    def test_happy_path(self):
        section, properties, risks, controls, details = self._good_inputs()
        validate_all([section], properties, risks, controls, details)

    def test_propagates_dag_error(self):
        section, _, risks, controls, details = self._good_inputs()
        # Cycle in property DAG.
        bad_props = [
            Property(id="a", description="A", parents=("b",)),
            Property(id="b", description="B", parents=("a",)),
        ]
        with pytest.raises(ValueError, match="cycle"):
            validate_all([section], bad_props, risks, controls, details)

    def test_propagates_question_property_error(self):
        _section, properties, risks, controls, details = self._good_inputs()
        bad_section = Section(
            id="s1",
            title="T",
            description="D",
            subsections=(
                SubSection(
                    title="Sub",
                    description="D",
                    questions=(BinaryQuestion(id="q1", text="Q", properties=("p_missing",)),),
                ),
            ),
        )
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_all([bad_section], properties, risks, controls, details)

    def test_propagates_risk_property_error(self):
        section, properties, _, controls, details = self._good_inputs()
        bad_risks = [
            Risk(
                id="r1",
                description="R",
                conditions=(
                    ConditionMapping(property="p_missing", likelihood="rare", consequence="minor"),
                ),
            )
        ]
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_all([section], properties, bad_risks, controls, details)

    def test_propagates_control_property_error(self):
        section, properties, risks, _, details = self._good_inputs()
        bad_controls = [
            Control(
                id="c1",
                description="C",
                property="p_missing",
                effects=(ControlEffect(risk_id="r1"),),
            )
        ]
        with pytest.raises(ValueError, match="unknown property 'p_missing'"):
            validate_all([section], properties, risks, bad_controls, details)

    def test_propagates_control_risk_error(self):
        section, properties, risks, _, details = self._good_inputs()
        bad_controls = [
            Control(
                id="c1",
                description="C",
                property="p1",
                effects=(ControlEffect(risk_id="r_missing"),),
            )
        ]
        with pytest.raises(ValueError, match="unknown risk 'r_missing'"):
            validate_all([section], properties, risks, bad_controls, details)

    def test_propagates_detail_property_error(self):
        section, properties, risks, controls, _ = self._good_inputs()
        bad_details = [Detail(id="d1", description="D", properties=("p_missing",))]
        with pytest.raises(ValueError, match="p_missing"):
            validate_all([section], properties, risks, controls, bad_details)

    def test_propagates_namespace_collision(self):
        section, properties, risks, _, details = self._good_inputs()
        # Control id collides with property id.
        bad_controls = [
            Control(
                id="p1",
                description="C",
                property="p1",
                effects=(ControlEffect(risk_id="r1"),),
            )
        ]
        with pytest.raises(ValueError, match="unique across namespaces"):
            validate_all([section], properties, risks, bad_controls, details)
