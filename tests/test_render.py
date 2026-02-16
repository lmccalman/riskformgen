"""Tests for render.py — template preparation and rendering."""

from __future__ import annotations

import pytest

from models import (
    AnyYesRule,
    BinaryQuestion,
    Control,
    ControlEffect,
    Property,
    Risk,
    Section,
    SubSection,
    all_questions,
)
from render import (
    _compile_property_getter,
    _compile_question_visibility,
    prepare_controls,
    prepare_properties,
    prepare_risks,
    prepare_sections,
    render_form,
    validate_question_ids,
)

# ---------------------------------------------------------------------------
# prepare_properties — property getters
# ---------------------------------------------------------------------------


class TestCompilePropertyGetter:
    def test_root_with_question(self):
        prop = Property(id="active", description="Active")
        q = BinaryQuestion(id="q1", text="Q", properties=("active",))
        body = _compile_property_getter(prop, {"active": q})
        assert "'yes'" in body
        assert "'no'" in body
        assert "return" in body
        # No parent cascade for root
        assert "prop_" not in body

    def test_root_without_question(self):
        prop = Property(id="orphan", description="Orphan")
        body = _compile_property_getter(prop, {})
        assert body == "return null;"

    def test_child_all_mode(self):
        prop = Property(id="child", description="Child", parents=("p1", "p2"))
        q = BinaryQuestion(id="q1", text="Q", properties=("child",))
        body = _compile_property_getter(prop, {"child": q})
        assert "this.prop_p1 === false" in body
        assert "this.prop_p2 === false" in body
        assert "this.prop_p1 === null" in body
        assert "this.prop_p2 === null" in body

    def test_child_any_mode(self):
        prop = Property(id="child", description="Child", parents=("p1", "p2"), activation="any")
        q = BinaryQuestion(id="q1", text="Q", properties=("child",))
        body = _compile_property_getter(prop, {"child": q})
        assert "parents.every(p => p === false)" in body
        assert "parents.some(p => p === true)" in body
        assert "this.prop_p1" in body
        assert "this.prop_p2" in body


# ---------------------------------------------------------------------------
# prepare_properties — question visibility
# ---------------------------------------------------------------------------


class TestCompileQuestionVisibility:
    def test_root_property_always_visible(self):
        prop = Property(id="p1", description="Root")
        q = BinaryQuestion(id="q1", text="Q", properties=("p1",))
        vis = _compile_question_visibility(q, {"p1": prop})
        assert vis == "true"

    def test_child_all_mode(self):
        prop = Property(id="p1", description="Child", parents=("parent1", "parent2"))
        q = BinaryQuestion(id="q1", text="Q", properties=("p1",))
        vis = _compile_question_visibility(q, {"p1": prop})
        assert "this.prop_parent1 === true" in vis
        assert "this.prop_parent2 === true" in vis
        assert "&&" in vis

    def test_child_any_mode(self):
        prop = Property(id="p1", description="Child", parents=("pa", "pb"), activation="any")
        q = BinaryQuestion(id="q1", text="Q", properties=("p1",))
        vis = _compile_question_visibility(q, {"p1": prop})
        assert "this.prop_pa === true" in vis
        assert "this.prop_pb === true" in vis
        assert "||" in vis

    def test_no_properties(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        vis = _compile_question_visibility(q, {})
        assert vis == "true"

    def test_multiple_properties_ored(self):
        root = Property(id="root", description="Root")
        child = Property(id="child", description="Child", parents=("root",))
        q = BinaryQuestion(id="q1", text="Q", properties=("root", "child"))
        vis = _compile_question_visibility(q, {"root": root, "child": child})
        # root is always visible (true), so the whole thing simplifies
        assert vis == "true"

    def test_multiple_non_root_properties(self):
        p1 = Property(id="p1", description="P1", parents=("root",))
        p2 = Property(id="p2", description="P2", parents=("root2",))
        q = BinaryQuestion(id="q1", text="Q", properties=("p1", "p2"))
        vis = _compile_question_visibility(q, {"p1": p1, "p2": p2})
        assert "||" in vis
        assert "this.prop_root === true" in vis
        assert "this.prop_root2 === true" in vis


# ---------------------------------------------------------------------------
# prepare_properties (integration)
# ---------------------------------------------------------------------------


class TestPrepareProperties:
    def test_returns_getters_and_visibility(self):
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
        ]
        questions = [
            BinaryQuestion(id="q1", text="Q1", properties=("root",)),
            BinaryQuestion(id="q2", text="Q2", properties=("child",)),
        ]
        getters, visibility = prepare_properties(props, questions)
        assert len(getters) == 2
        assert getters[0]["id"] == "root"
        assert getters[1]["id"] == "child"
        assert visibility["q1"] == "true"  # root is always reachable
        assert "this.prop_root === true" in visibility["q2"]

    def test_empty(self):
        getters, visibility = prepare_properties([], [])
        assert getters == []
        assert visibility == {}


# ---------------------------------------------------------------------------
# prepare_sections
# ---------------------------------------------------------------------------


class TestPrepareSections:
    def test_output_structure(self, sample_sections, sample_properties):
        _, question_visibility = prepare_properties(
            sample_properties,
            all_questions(sample_sections),
        )
        result = prepare_sections(sample_sections, question_visibility)
        assert len(result) == 1
        sec = result[0]
        assert sec["id"] == "sec1"
        assert sec["title"] == "Section One"
        assert len(sec["subsections"]) == 1
        sub = sec["subsections"][0]
        assert sub["title"] == "Basics"
        assert len(sub["questions"]) == 2

    def test_visibility_compiled(self):
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
        ]
        q1 = BinaryQuestion(id="q1", text="Q1", properties=("root",))
        q2 = BinaryQuestion(id="q2", text="Q2", properties=("child",))
        sub = SubSection(title="S", description="", questions=(q1, q2))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        _, vis = prepare_properties(props, [q1, q2])
        result = prepare_sections([sec], vis)
        q1_dict = result[0]["subsections"][0]["questions"][0]
        q2_dict = result[0]["subsections"][0]["questions"][1]
        # q1 targets root (always visible) — no visibility_js
        assert "visibility_js" not in q1_dict
        # q2 targets child (needs root === true) — has visibility_js
        assert "visibility_js" in q2_dict
        assert "this.prop_root === true" in q2_dict["visibility_js"]

    def test_subsection_visibility(self):
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
        ]
        q = BinaryQuestion(id="q1", text="Q", properties=("child",))
        sub = SubSection(title="Conditional", description="", questions=(q,))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        _, vis = prepare_properties(props, [q])
        result = prepare_sections([sec], vis)
        # Subsection should have visibility_js since all questions are conditional
        assert "visibility_js" in result[0]["subsections"][0]

    def test_empty_sections(self):
        assert prepare_sections([], {}) == []


# ---------------------------------------------------------------------------
# prepare_risks
# ---------------------------------------------------------------------------


class TestPrepareRisks:
    def test_output_structure(self):
        q = BinaryQuestion(id="q1", text="Risky?", properties=())
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=("q1",), likelihood="likely"),),
        )
        result = prepare_risks([risk], [q])
        assert len(result) == 1
        r = result[0]
        assert r["id"] == "r1"
        assert "rules_js" in r
        assert len(r["rules_js"]) == 1
        assert "questions" in r
        assert r["questions"][0]["id"] == "q1"
        assert r["questions"][0]["text"] == "Risky?"

    def test_question_ids_deduplicated(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(
                AnyYesRule(question_ids=("q1",), likelihood="likely"),
                AnyYesRule(question_ids=("q1",), consequence="major"),
            ),
        )
        result = prepare_risks([risk], [q])
        assert len(result[0]["questions"]) == 1

    def test_defaults_passed_through(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=("q1",), likelihood="likely"),),
            default_likelihood="possible",
            default_consequence="major",
        )
        result = prepare_risks([risk], [q])
        assert result[0]["default_likelihood"] == "possible"
        assert result[0]["default_consequence"] == "major"


# ---------------------------------------------------------------------------
# prepare_controls
# ---------------------------------------------------------------------------


class TestPrepareControls:
    def test_control_getters(self, sample_control):
        risk_dicts = [{"id": "r1", "name": "R"}]
        getters = prepare_controls([sample_control], risk_dicts)
        assert len(getters) == 1
        assert getters[0]["id"] == "ctrl1"
        assert "js" in getters[0]

    def test_effects_grouped_by_risk(self, sample_control):
        risk_dicts: list[dict] = [{"id": "r1", "name": "R"}]
        prepare_controls([sample_control], risk_dicts)
        assert len(risk_dicts[0]["controls"]) == 1
        assert risk_dicts[0]["controls"][0]["id"] == "ctrl1"
        assert risk_dicts[0]["controls"][0]["reduces_likelihood"] is True

    def test_missing_risk_skipped(self):
        ctrl = Control(
            id="c1",
            name="C",
            question_id="q1",
            present_value="yes",
            effects=(ControlEffect(risk_id="nonexistent", reduces_likelihood=True),),
        )
        risk_dicts = [{"id": "r1", "name": "R"}]
        getters = prepare_controls([ctrl], risk_dicts)
        assert len(getters) == 1
        assert risk_dicts[0]["controls"] == []

    def test_empty_controls(self):
        risk_dicts = [{"id": "r1", "name": "R"}]
        getters = prepare_controls([], risk_dicts)
        assert getters == []
        assert risk_dicts[0]["controls"] == []


# ---------------------------------------------------------------------------
# render_form (integration)
# ---------------------------------------------------------------------------


class TestRenderForm:
    def test_returns_html(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_alpine_xdata(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert "x-data" in html

    def test_sections_appear_as_tabs(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert "sec1" in html
        assert "Section One" in html

    def test_property_getters_in_html(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert "prop_prop_a" in html
        assert "prop_prop_b" in html

    def test_with_controls(self, sample_sections, sample_control, sample_properties):
        q = all_questions(sample_sections)
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=(q[0].id,), likelihood="likely"),),
        )
        html = render_form(sample_sections, [risk], [sample_control], sample_properties)
        assert "Encryption enabled" in html


# ---------------------------------------------------------------------------
# render_form — save/load export/import
# ---------------------------------------------------------------------------


@pytest.fixture
def binary_sections():
    """Sections with binary questions."""
    q1 = BinaryQuestion(id="q_bin", text="Yes or no?", properties=("p1",))
    q2 = BinaryQuestion(id="q_bin2", text="Another?", properties=("p2",))
    sub = SubSection(title="Mixed", description="", questions=(q1, q2))
    return [Section(id="mixed", title="Mixed", description="", subsections=(sub,))]


@pytest.fixture
def binary_properties():
    return [
        Property(id="p1", description="P1"),
        Property(id="p2", description="P2", parents=("p1",)),
    ]


@pytest.fixture
def binary_html(binary_sections, binary_properties):
    return render_form(binary_sections, [], properties=binary_properties)


class TestRenderFormMetadata:
    """Verify build-time metadata arrays are embedded in rendered output."""

    def test_question_ids_present(self, binary_html):
        assert "'q_bin'" in binary_html
        assert "'q_bin2'" in binary_html

    def test_risk_ids_empty(self, binary_html):
        assert "_riskIds: [" in binary_html
        start = binary_html.index("_riskIds: [")
        end = binary_html.index("]", start)
        assert binary_html[start:end].strip() == "_riskIds: ["


class TestRenderFormSaveLoad:
    """Verify save/load buttons and file inputs are rendered."""

    def test_answers_save_button_in_section(self, binary_html):
        assert "exportAnswers()" in binary_html
        assert "Save answers" in binary_html

    def test_answers_load_button_in_section(self, binary_html):
        assert "importAnswers($event)" in binary_html
        assert "Load answers" in binary_html

    def test_no_assessment_buttons_without_risks(self, binary_sections, binary_properties):
        html = render_form(binary_sections, [], properties=binary_properties)
        assert "Save assessment" not in html
        assert "Load assessment" not in html

    def test_hidden_file_inputs_present(self, binary_html):
        assert 'type="file"' in binary_html
        assert 'accept=".json"' in binary_html


# ---------------------------------------------------------------------------
# validate_question_ids
# ---------------------------------------------------------------------------


class TestValidateQuestionIds:
    def test_valid_ids_pass(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=("q1",), likelihood="likely"),),
        )
        ctrl = Control(
            id="c1",
            name="C",
            question_id="q1",
            present_value="yes",
            effects=(ControlEffect(risk_id="r1", reduces_likelihood=True),),
        )
        validate_question_ids([q], [risk], [ctrl])  # should not raise

    def test_invalid_risk_rule_question_id(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=("q_typo",), likelihood="likely"),),
        )
        with pytest.raises(ValueError, match="unknown question 'q_typo'"):
            validate_question_ids([q], [risk], [])

    def test_invalid_control_question_id(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        ctrl = Control(
            id="c1",
            name="C",
            question_id="q_typo",
            present_value="yes",
            effects=(ControlEffect(risk_id="r1", reduces_likelihood=True),),
        )
        with pytest.raises(ValueError, match="unknown question 'q_typo'"):
            validate_question_ids([q], [], [ctrl])

    def test_multiple_errors_reported(self):
        q = BinaryQuestion(id="q1", text="Q", properties=())
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=("bad1",), likelihood="likely"),),
        )
        ctrl = Control(
            id="c1",
            name="C",
            question_id="bad2",
            present_value="yes",
            effects=(ControlEffect(risk_id="r1", reduces_likelihood=True),),
        )
        with pytest.raises(ValueError, match="bad1") as exc_info:
            validate_question_ids([q], [risk], [ctrl])
        assert "bad2" in str(exc_info.value)
