"""Tests for render.py — template preparation and rendering."""

from __future__ import annotations

from models import (
    AnyYesRule,
    Control,
    ControlEffect,
    Equals,
    Risk,
    Section,
    SubSection,
    YesNoQuestion,
    all_questions,
)
from render import prepare_controls, prepare_risks, prepare_sections, render_form

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
