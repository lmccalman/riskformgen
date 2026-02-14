"""Tests for render.py — template preparation and rendering."""

from __future__ import annotations

import pytest

from models import (
    AnyYesRule,
    Control,
    ControlEffect,
    Equals,
    MultipleSelectQuestion,
    Risk,
    Section,
    SubSection,
    YesNoQuestion,
    all_questions,
)
from render import (
    prepare_controls,
    prepare_risks,
    prepare_sections,
    render_form,
    validate_question_ids,
)

# ---------------------------------------------------------------------------
# prepare_sections
# ---------------------------------------------------------------------------


class TestPrepareSections:
    def test_output_structure(self, sample_sections):
        result = prepare_sections(sample_sections)
        assert len(result) == 1
        sec = result[0]
        assert sec["id"] == "sec1"
        assert sec["title"] == "Section One"
        assert len(sec["subsections"]) == 1
        sub = sec["subsections"][0]
        assert sub["title"] == "Basics"
        assert len(sub["questions"]) == 2

    def test_visibility_compiled(self):
        q = YesNoQuestion(
            id="q1",
            text="Q",
            visible_when=Equals(question_id="q0", value="yes"),
        )
        sub = SubSection(title="S", description="", questions=(q,))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        result = prepare_sections([sec])
        q_dict = result[0]["subsections"][0]["questions"][0]
        assert "visible_when_js" in q_dict
        assert "q0" in q_dict["visible_when_js"]

    def test_subsection_visibility(self):
        q = YesNoQuestion(id="q1", text="Q")
        sub = SubSection(
            title="Conditional",
            description="",
            questions=(q,),
            visible_when=Equals(question_id="q0", value="yes"),
        )
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        result = prepare_sections([sec])
        assert "visible_when_js" in result[0]["subsections"][0]

    def test_empty_sections(self):
        assert prepare_sections([]) == []


# ---------------------------------------------------------------------------
# prepare_risks
# ---------------------------------------------------------------------------


class TestPrepareRisks:
    def test_output_structure(self):
        q = YesNoQuestion(id="q1", text="Risky?")
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
        q = YesNoQuestion(id="q1", text="Q")
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
        # q1 appears in both rules but should only be listed once
        assert len(result[0]["questions"]) == 1

    def test_defaults_passed_through(self):
        q = YesNoQuestion(id="q1", text="Q")
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
        # Getter is still created
        assert len(getters) == 1
        # But no controls attached to r1
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
    def test_returns_html(self, sample_sections):
        q = all_questions(sample_sections)
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=(q[0].id,), likelihood="likely"),),
        )
        html = render_form(sample_sections, [risk])
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_alpine_xdata(self, sample_sections):
        q = all_questions(sample_sections)
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=(q[0].id,), likelihood="likely"),),
        )
        html = render_form(sample_sections, [risk])
        assert "x-data" in html

    def test_sections_appear_as_tabs(self, sample_sections):
        q = all_questions(sample_sections)
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=(q[0].id,), likelihood="likely"),),
        )
        html = render_form(sample_sections, [risk])
        assert "sec1" in html  # section id appears
        assert "Section One" in html

    def test_with_controls(self, sample_sections, sample_control):
        q = all_questions(sample_sections)
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=(q[0].id,), likelihood="likely"),),
        )
        html = render_form(sample_sections, [risk], [sample_control])
        assert "Encryption enabled" in html


# ---------------------------------------------------------------------------
# render_form — save/load export/import
# ---------------------------------------------------------------------------


@pytest.fixture
def mixed_sections():
    """Sections with both scalar and array question types."""
    q1 = YesNoQuestion(id="q_yn", text="Yes or no?")
    q2 = MultipleSelectQuestion(id="q_ms", text="Pick many", options=("a", "b"))
    sub = SubSection(title="Mixed", description="", questions=(q1, q2))
    return [Section(id="mixed", title="Mixed", description="", subsections=(sub,))]


@pytest.fixture
def mixed_risk():
    return Risk(
        id="test_risk",
        name="Test Risk",
        description="A test risk",
        rules=(AnyYesRule(question_ids=("q_yn",), likelihood="likely"),),
    )


@pytest.fixture
def mixed_html(mixed_sections, mixed_risk):
    return render_form(mixed_sections, [mixed_risk])


class TestRenderFormMetadata:
    """Verify build-time metadata arrays are embedded in rendered output."""

    def test_question_ids_present(self, mixed_html):
        assert "'q_yn'" in mixed_html
        assert "'q_ms'" in mixed_html

    def test_array_question_ids_only_multiple_select(self, mixed_html):
        # _arrayQuestionIds should contain q_ms but not q_yn
        assert "_arrayQuestionIds: [" in mixed_html
        # Extract the array content between _arrayQuestionIds: [ and the next ]
        start = mixed_html.index("_arrayQuestionIds: [")
        end = mixed_html.index("]", start)
        array_content = mixed_html[start:end]
        assert "'q_ms'" in array_content
        assert "'q_yn'" not in array_content

    def test_risk_ids_present(self, mixed_html):
        assert "_riskIds: [" in mixed_html
        start = mixed_html.index("_riskIds: [")
        end = mixed_html.index("]", start)
        assert "'test_risk'" in mixed_html[start:end]

    def test_no_risks_means_empty_risk_ids(self, mixed_sections):
        html = render_form(mixed_sections, [])
        start = html.index("_riskIds: [")
        end = html.index("]", start)
        assert html[start:end].strip() == "_riskIds: ["


class TestRenderFormSaveLoad:
    """Verify save/load buttons and file inputs are rendered."""

    def test_answers_save_button_in_section(self, mixed_html):
        assert "exportAnswers()" in mixed_html
        assert "Save answers" in mixed_html

    def test_answers_load_button_in_section(self, mixed_html):
        assert "importAnswers($event)" in mixed_html
        assert "Load answers" in mixed_html

    def test_assessment_save_button_in_risks_tab(self, mixed_html):
        assert "exportAssessment()" in mixed_html
        assert "Save assessment" in mixed_html

    def test_assessment_load_button_in_risks_tab(self, mixed_html):
        assert "importAssessment($event)" in mixed_html
        assert "Load assessment" in mixed_html

    def test_no_assessment_buttons_without_risks(self, mixed_sections):
        html = render_form(mixed_sections, [])
        assert "Save assessment" not in html
        assert "Load assessment" not in html

    def test_hidden_file_inputs_present(self, mixed_html):
        assert 'type="file"' in mixed_html
        assert 'accept=".json"' in mixed_html


# ---------------------------------------------------------------------------
# validate_question_ids
# ---------------------------------------------------------------------------


class TestValidateQuestionIds:
    def test_valid_ids_pass(self):
        q = YesNoQuestion(id="q1", text="Q")
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
        q = YesNoQuestion(id="q1", text="Q")
        risk = Risk(
            id="r1",
            name="R",
            description="D",
            rules=(AnyYesRule(question_ids=("q_typo",), likelihood="likely"),),
        )
        with pytest.raises(ValueError, match="unknown question 'q_typo'"):
            validate_question_ids([q], [risk], [])

    def test_invalid_control_question_id(self):
        q = YesNoQuestion(id="q1", text="Q")
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
        q = YesNoQuestion(id="q1", text="Q")
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
