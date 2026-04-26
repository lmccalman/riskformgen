"""Tests for render.py — template preparation and rendering."""

from __future__ import annotations

import pytest

import config
from models import (
    BinaryQuestion,
    ConditionMapping,
    Detail,
    DetailQuestion,
    Property,
    Risk,
    Section,
    SubSection,
)
from registry import SystemMeta, SystemRecord
from render import (
    _compile_property_getter,
    _compile_question_visibility,
    _detail_show_js,
    render_assessment,
    render_assessment_app_js,
    render_landing,
    render_questionnaire,
    render_questionnaire_app_js,
    render_registry_index,
    render_registry_system,
)

# ---------------------------------------------------------------------------
# Property getter compilation
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

    def test_derived_without_question_all_mode(self):
        # No question targets this property; once parents (all-mode) are satisfied,
        # the property is true — a pure computed AND-of-parents.
        prop = Property(id="derived", description="Derived", parents=("p1", "p2"))
        body = _compile_property_getter(prop, {})
        assert "this.prop_p1 === false" in body
        assert "this.prop_p2 === false" in body
        assert body.rstrip().endswith("return true;")
        assert "this.answers[" not in body

    def test_derived_without_question_any_mode(self):
        prop = Property(
            id="derived", description="Derived", parents=("p1", "p2"), activation="any"
        )
        body = _compile_property_getter(prop, {})
        assert "parents.every(p => p === false)" in body
        assert "parents.some(p => p === true)" in body
        assert body.rstrip().endswith("return true;")
        assert "this.answers[" not in body

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
# Question visibility compilation
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
        assert "prop_parent1 === true" in vis
        assert "prop_parent2 === true" in vis
        assert "&&" in vis

    def test_child_any_mode(self):
        prop = Property(id="p1", description="Child", parents=("pa", "pb"), activation="any")
        q = BinaryQuestion(id="q1", text="Q", properties=("p1",))
        vis = _compile_question_visibility(q, {"p1": prop})
        assert "prop_pa === true" in vis
        assert "prop_pb === true" in vis
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
        assert "prop_root === true" in vis
        assert "prop_root2 === true" in vis


# ---------------------------------------------------------------------------
# Detail show_js compilation
# ---------------------------------------------------------------------------


class TestDetailShowJs:
    def test_single_property(self):
        js = _detail_show_js(["p1"])
        assert js == "prop_p1 === true"

    def test_multiple_properties(self):
        js = _detail_show_js(["p1", "p2"])
        assert "prop_p1 === true" in js
        assert "prop_p2 === true" in js
        assert "||" in js

    def test_no_properties(self):
        assert _detail_show_js([]) == "false"


# ---------------------------------------------------------------------------
# Landing & registry pages — small, no Alpine
# ---------------------------------------------------------------------------


class TestRenderLanding:
    def test_returns_html(self):
        html = render_landing()
        assert isinstance(html, str)
        assert len(html) > 0

    def test_links_to_each_tool(self):
        html = render_landing()
        assert 'href="questionnaire.html"' in html
        assert 'href="assessment.html"' in html
        assert 'href="registry.html"' in html

    def test_no_alpine(self):
        html = render_landing()
        assert "x-data" not in html


class TestRenderRegistry:
    def test_index_empty_state_when_no_records(self):
        html = render_registry_index([])
        assert isinstance(html, str)
        assert "Registry" in html
        assert "No systems registered yet" in html
        assert "x-data" not in html

    def test_index_renders_a_row_per_record(self, sample_record_factory):
        records = [sample_record_factory(slug="acme", name="Acme")]
        html = render_registry_index(records)
        assert 'href="registry/acme.html"' in html
        assert "Acme" in html
        # Worst residual level is "high" for the sample record (ineffective),
        # so the colour-coded badge should appear with the red class.
        assert "badge-red" in html

    def test_index_sorts_by_exported_at_desc(self, sample_record_factory):
        old = sample_record_factory(slug="old", name="Old", assessment_at="2026-01-01T00:00:00Z")
        new = sample_record_factory(slug="new", name="New", assessment_at="2026-04-01T00:00:00Z")
        # Pass already-sorted (the loader does the sort); the index renders in
        # whatever order it receives. Pin that the rows preserve input order.
        html = render_registry_index([new, old])
        new_pos = html.find('href="registry/new.html"')
        old_pos = html.find('href="registry/old.html"')
        assert new_pos < old_pos

    def test_questionnaire_only_record_shows_no_assessment(
        self,
        sample_record_factory,
        sample_sections,
        sample_risk,
        sample_control,
        sample_properties,
    ):
        rec = sample_record_factory(slug="drafty", name="Drafty", with_assessment=False)
        html = render_registry_system(
            rec,
            sample_sections,
            [sample_risk],
            [sample_control],
            sample_properties,
            details=[],
        )
        assert "No assessment has been committed" in html

    def test_system_page_renders_question_answer(
        self,
        sample_record_factory,
        sample_sections,
        sample_risk,
        sample_control,
        sample_properties,
    ):
        rec = sample_record_factory(slug="acme", name="Acme")
        html = render_registry_system(
            rec, sample_sections, [sample_risk], [sample_control], sample_properties, details=[]
        )
        assert "Acme" in html
        # binary answer "yes" rendered as "Yes" (case-sensitive copy in template)
        assert "<span>Yes</span>" in html

    def test_system_page_renders_risk_card_with_level_badge(
        self,
        sample_record_factory,
        sample_sections,
        sample_risk,
        sample_control,
        sample_properties,
    ):
        rec = sample_record_factory(slug="acme", name="Acme")
        html = render_registry_system(
            rec, sample_sections, [sample_risk], [sample_control], sample_properties, details=[]
        )
        # Risk card title: r1 → "R1"
        assert "R1" in html
        # Inherent level high → red badge
        assert "badge-red" in html

    def test_system_page_uses_asset_prefix(
        self,
        sample_record_factory,
        sample_sections,
        sample_risk,
        sample_control,
        sample_properties,
    ):
        rec = sample_record_factory(slug="acme", name="Acme")
        html = render_registry_system(
            rec, sample_sections, [sample_risk], [sample_control], sample_properties, details=[]
        )
        assert 'href="../bulma.min.css"' in html
        assert 'href="../input.css"' in html
        assert 'href="../registry.html"' in html

    def test_system_page_skips_not_applicable_risks(
        self,
        sample_record_factory,
        sample_sections,
        sample_risk,
        sample_control,
        sample_properties,
    ):
        # Build a record where r1 is not applicable (level = not_applicable).
        # The risk card should not render at all for that risk.
        rec = sample_record_factory(slug="acme", name="Acme", inherent_level="not_applicable")
        html = render_registry_system(
            rec, sample_sections, [sample_risk], [sample_control], sample_properties, details=[]
        )
        # Risk card is gone — the r1 title only renders when the risk fires.
        assert "card-header-title" not in html
        # Friendly empty-message instead.
        assert "No applicable risks fired" in html

    def test_no_alpine_anywhere(
        self,
        sample_record_factory,
        sample_sections,
        sample_risk,
        sample_control,
        sample_properties,
    ):
        rec = sample_record_factory(slug="acme", name="Acme")
        index_html = render_registry_index([rec])
        system_html = render_registry_system(
            rec, sample_sections, [sample_risk], [sample_control], sample_properties, details=[]
        )
        for html in (index_html, system_html):
            assert "x-data" not in html
            assert "x-show" not in html
            assert "x-text" not in html


@pytest.fixture
def sample_record_factory(sample_questions):
    """Factory for a SystemRecord built around the sample form fixtures."""

    def _make(
        *,
        slug: str = "demo",
        name: str = "Demo",
        with_assessment: bool = True,
        inherent_level: str = "high",
        assessment_at: str = "2026-04-01T09:00:00Z",
    ) -> SystemRecord:
        questionnaire = {
            "format": "riskformgen-answers",
            "version": 2,
            "exported_at": "2026-04-01T08:00:00Z",
            "question_ids": [q.id for q in sample_questions],
            "answers": {q.id: "yes" for q in sample_questions},
            "detail_ids": [],
            "details": {},
            "property_ids": ["prop_a", "prop_b"],
            "properties": {"prop_a": True, "prop_b": True},
        }
        assessment = None
        if with_assessment:
            inherent = {
                "r1": {
                    "likelihood": "likely" if inherent_level != "not_applicable" else None,
                    "consequence": "major" if inherent_level != "not_applicable" else None,
                    "level": inherent_level,
                    "firing_conditions": ["prop_a"] if inherent_level != "not_applicable" else [],
                },
            }
            assessment = {
                "format": "riskformgen-assessment",
                "version": config.ASSESSMENT_VERSION,
                "exported_at": assessment_at,
                "risk_ids": ["r1"],
                "property_ids": ["prop_a", "prop_b"],
                "properties": {"prop_a": True, "prop_b": True},
                "inherent": inherent,
                "control_effectiveness": {"r1": "ineffective"},
                "residual_likelihood": {"r1": ""},
                "residual_consequence": {"r1": ""},
                "justifications": {"r1": ""},
                "mandated_controls": {"r1": {"ctrl1": False}},
                "mandated_comments": {"r1": {"ctrl1": ""}},
                "aggregate_residual_level": "",
                "aggregate_residual_justification": "",
            }
        return SystemRecord(
            slug=slug,
            meta=SystemMeta(name=name, owner="Owner"),
            questionnaire=questionnaire,
            assessment=assessment,
        )

    return _make


# ---------------------------------------------------------------------------
# Questionnaire page integration
# ---------------------------------------------------------------------------


class TestRenderQuestionnaire:
    def test_returns_html(self, sample_sections, sample_properties):
        html = render_questionnaire(sample_sections, properties=sample_properties)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_alpine_xdata(self, sample_sections, sample_properties):
        html = render_questionnaire(sample_sections, properties=sample_properties)
        assert 'x-data="questionnaire"' in html

    def test_no_risk_analysis_tab(self, sample_sections, sample_properties):
        # The questionnaire view must not surface risk content; that lives on
        # the assessment page now.
        html = render_questionnaire(sample_sections, properties=sample_properties)
        assert "Risk Analysis" not in html

    def test_sections_appear_as_tabs(self, sample_sections, sample_properties):
        html = render_questionnaire(sample_sections, properties=sample_properties)
        assert "sec1" in html
        assert "Section One" in html

    def test_property_getters_referenced(self, sample_sections, sample_properties):
        # The questionnaire page references prop_* via x-show; the factory
        # defines them.
        js = render_questionnaire_app_js(sample_sections, properties=sample_properties)
        assert "prop_prop_a" in js
        assert "prop_prop_b" in js

    def test_back_link_to_landing(self, sample_sections, sample_properties):
        html = render_questionnaire(sample_sections, properties=sample_properties)
        assert 'href="index.html"' in html


# ---------------------------------------------------------------------------
# Assessment page integration
# ---------------------------------------------------------------------------


class TestRenderAssessment:
    def test_returns_html(self, sample_sections, sample_properties, sample_risk):
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_alpine_xdata(self, sample_sections, sample_properties):
        html = render_assessment(sample_sections, [], properties=sample_properties)
        assert 'x-data="assessment"' in html

    def test_load_questionnaire_button(self, sample_sections, sample_properties):
        html = render_assessment(sample_sections, [], properties=sample_properties)
        assert "Load questionnaire" in html
        assert 'x-ref="answersFile"' in html

    def test_renders_risks(self, sample_sections, sample_properties):
        risk = Risk(
            id="r1",
            description="Test risk",
            conditions=(
                ConditionMapping(
                    property="prop_a",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        html = render_assessment(sample_sections, [risk], properties=sample_properties)
        assert "r1" in html
        assert "Test risk" in html

    def test_renders_controls(self, sample_sections, sample_control, sample_properties):
        risk = Risk(
            id="r1",
            description="D",
            conditions=(
                ConditionMapping(
                    property="prop_a",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        html = render_assessment(sample_sections, [risk], [sample_control], sample_properties)
        js = render_assessment_app_js(sample_sections, [risk], [sample_control], sample_properties)
        assert "Encryption enabled" in html
        assert "this.prop_prop_a === true" in js

    def test_detail_rendered_beside_relevant_risk(self, sample_sections, sample_properties):
        risk = Risk(
            id="r1",
            description="Risk tied to prop_a",
            conditions=(
                ConditionMapping(
                    property="prop_a",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        relevant = Detail(
            id="det_relevant",
            description="Outdoor context",
            properties=("prop_a",),
        )
        unrelated = Detail(
            id="det_unrelated",
            description="Something else",
            properties=("prop_b",),
        )
        html = render_assessment(
            sample_sections,
            [risk],
            properties=sample_properties,
            details=[relevant, unrelated],
        )
        # The relevant detail's description and show_js condition reach the risk card
        assert "Outdoor context" in html
        assert "prop_prop_a === true" in html
        assert "details['det_relevant']" in html
        # The unrelated detail (referencing prop_b, which isn't in risk r1's conditions)
        # is filtered out of this risk's card
        assert "Something else" not in html
        assert "details['det_unrelated']" not in html

    def test_risk_guidance_rendered(self, sample_sections, sample_properties):
        risk = Risk(
            id="r1",
            description="Test risk",
            conditions=(
                ConditionMapping(property="prop_a", likelihood="likely", consequence="major"),
            ),
            guidance="Talk to the risk manager about the next steps.",
        )
        html = render_assessment(sample_sections, [risk], properties=sample_properties)
        assert "Talk to the risk manager about the next steps." in html

    def test_risk_no_guidance_renders_no_help_block(
        self, sample_sections, sample_properties, sample_risk
    ):
        # sample_risk has no guidance — verify no orphan <p class="help"> from the
        # risk card sneaks in.
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert '<p class="help"><em></em></p>' not in html

    def test_answers_summary_rendered(self, sample_sections, sample_properties, sample_risk):
        # The assessment page includes a read-only summary of the loaded answers.
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert "answers-summary" in html
        # Question text from the section appears in the summary
        assert "Is it risky?" in html


# ---------------------------------------------------------------------------
# Read-only answers summary — visibility wiring
# ---------------------------------------------------------------------------


class TestAnswersSummary:
    def test_binary_question_renders_yes_no_dispatch(
        self, sample_sections, sample_properties, sample_risk
    ):
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        # The summary should switch on the answer value, defaulting to '—'.
        assert "answers['q_bin'] === 'yes'" in html
        assert "Yes" in html
        assert "No" in html

    def test_detail_question_renders_detail_text(
        self, sample_properties, sample_detail, detail_question
    ):
        sub = SubSection(title="Context", description="", questions=(detail_question,))
        sec = Section(id="ctx", title="Context", description="", subsections=(sub,))
        html = render_assessment([sec], [], properties=sample_properties, details=[sample_detail])
        # Free-text answer comes from details[detail_id]
        assert "details['det1']" in html

    def test_subsection_visibility_propagates_to_summary(self):
        # A subsection containing only a conditional question gets an x-show
        # in the summary mirroring the questionnaire's gating.
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
        ]
        q_root = BinaryQuestion(id="q_root", text="Root q", properties=("root",))
        q_child = BinaryQuestion(id="q_child", text="Child q", properties=("child",))
        sub = SubSection(title="Conditional", description="", questions=(q_child,))
        always_sub = SubSection(title="Always", description="", questions=(q_root,))
        sec = Section(id="s", title="S", description="", subsections=(always_sub, sub))
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="root", likelihood="rare", consequence="minor"),
            ),
        )
        html = render_assessment([sec], [risk], properties=props)
        # The conditional sub's wrapper inside the summary inherits the
        # question-level visibility expression.
        assert 'class="answers-summary-subsection"' in html
        assert "prop_root === true" in html


# ---------------------------------------------------------------------------
# Detail-question guidance
# ---------------------------------------------------------------------------


class TestDetailQuestionGuidance:
    def test_detail_question_guidance_rendered(self, sample_properties, sample_detail):
        dq = DetailQuestion(
            id="q_det",
            text="Describe the context.",
            detail_id=sample_detail.id,
            properties=sample_detail.properties,
            guidance="Be specific about locations.",
        )
        sub = SubSection(title="Context", description="", questions=(dq,))
        sec = Section(id="ctx", title="Context", description="", subsections=(sub,))
        html = render_questionnaire([sec], properties=sample_properties, details=[sample_detail])
        assert "Describe the context." in html
        assert "Be specific about locations." in html
        assert "details['det1']" in html


# ---------------------------------------------------------------------------
# Cross-entity visibility semantics (driven through the rendered output)
# ---------------------------------------------------------------------------


class TestRenderedVisibility:
    def test_always_visible_question_has_no_xshow(self):
        # A question targeting a root property never needs a per-question x-show.
        root = Property(id="root", description="Root")
        q = BinaryQuestion(id="q1", text="Always", properties=("root",))
        sub = SubSection(title="S", description="", questions=(q,))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        html = render_questionnaire([sec], properties=[root])
        # No conditional x-show wrapping an unconditional question.
        assert 'x-show="true"' not in html

    def test_conditional_question_has_xshow(self):
        root = Property(id="root", description="Root")
        child = Property(id="child", description="Child", parents=("root",))
        q = BinaryQuestion(id="q1", text="Conditional", properties=("child",))
        sub = SubSection(title="S", description="", questions=(q,))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        html = render_questionnaire([sec], properties=[root, child])
        assert 'x-show="(prop_root === true)"' in html

    def test_subsection_always_visible_when_any_question_is(self):
        # A subsection with one always-visible + one conditional question should
        # itself always render (no subsection-level x-show).
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
            Property(id="gc", description="Grandchild", parents=("child",)),
        ]
        q_root = BinaryQuestion(id="q_root", text="Q root", properties=("root",))
        q_gc = BinaryQuestion(id="q_gc", text="Q grandchild", properties=("gc",))
        sub = SubSection(title="Mixed", description="", questions=(q_root, q_gc))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        html = render_questionnaire([sec], properties=props)
        # The subsection's opening <div class="box stack-md"> should have no x-show.
        assert '<div class="box stack-md">' in html

    def test_subsection_hidden_when_all_questions_are_conditional(self):
        props = [
            Property(id="root", description="Root"),
            Property(id="child", description="Child", parents=("root",)),
        ]
        q = BinaryQuestion(id="q1", text="Q", properties=("child",))
        sub = SubSection(title="Conditional", description="", questions=(q,))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        html = render_questionnaire([sec], properties=props)
        # The subsection's <div class="box"> inherits the OR of its questions' conditions.
        assert '<div class="box stack-md" x-show="(prop_root === true)">' in html


# ---------------------------------------------------------------------------
# render_questionnaire — save/load wiring
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
def binary_questionnaire_html(binary_sections, binary_properties):
    return render_questionnaire(binary_sections, properties=binary_properties)


@pytest.fixture
def binary_questionnaire_js(binary_sections, binary_properties):
    return render_questionnaire_app_js(binary_sections, properties=binary_properties)


@pytest.fixture
def binary_assessment_html(binary_sections, binary_properties):
    return render_assessment(binary_sections, [], properties=binary_properties)


@pytest.fixture
def binary_assessment_js(binary_sections, binary_properties):
    return render_assessment_app_js(binary_sections, [], properties=binary_properties)


class TestQuestionnaireMetadata:
    """Build-time metadata arrays embedded in the questionnaire factory."""

    def test_question_ids_present(self, binary_questionnaire_js):
        assert '_questionIds: ["q_bin", "q_bin2"]' in binary_questionnaire_js

    def test_no_risk_metadata(self, binary_questionnaire_js):
        # The questionnaire factory must not carry risk-only state.
        assert "_riskIds" not in binary_questionnaire_js
        assert "control_effectiveness" not in binary_questionnaire_js


class TestAssessmentMetadata:
    """Build-time metadata arrays embedded in the assessment factory."""

    def test_question_ids_present(self, binary_assessment_js):
        assert '_questionIds: ["q_bin", "q_bin2"]' in binary_assessment_js

    def test_risk_ids_empty(self, binary_assessment_js):
        assert "_riskIds: []" in binary_assessment_js

    def test_control_ids_empty(self, binary_assessment_js):
        assert "_controlIds: {}" in binary_assessment_js


class TestQuestionnaireSaveLoad:
    """Verify save/load buttons and file inputs are rendered."""

    def test_answers_save_button_in_section(self, binary_questionnaire_html):
        assert "exportAnswers()" in binary_questionnaire_html
        assert "Save answers" in binary_questionnaire_html

    def test_answers_load_button_in_section(self, binary_questionnaire_html):
        assert "importAnswers($event)" in binary_questionnaire_html
        assert "Load answers" in binary_questionnaire_html

    def test_no_assessment_buttons(self, binary_questionnaire_html):
        # Assessment-only buttons must not leak into the questionnaire surface.
        assert "Save assessment" not in binary_questionnaire_html
        assert "Load assessment" not in binary_questionnaire_html

    def test_hidden_file_inputs_present(self, binary_questionnaire_html):
        assert 'type="file"' in binary_questionnaire_html
        assert 'accept=".json"' in binary_questionnaire_html


class TestAssessmentSaveLoad:
    """The assessment view exports/imports assessment JSON, not answers JSON.
    It does still import questionnaire JSON via a Load-questionnaire button."""

    def test_assessment_export_button(self, sample_sections, sample_properties, sample_risk):
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert "exportAssessment()" in html
        assert "Save assessment" in html

    def test_assessment_import_button(self, sample_sections, sample_properties, sample_risk):
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert "importAssessment($event)" in html

    def test_load_questionnaire_button(self, sample_sections, sample_properties, sample_risk):
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert "importAnswers($event)" in html

    def test_no_export_answers_button(self, sample_sections, sample_properties, sample_risk):
        # The assessor doesn't export answers — that's the system owner's job.
        html = render_assessment(sample_sections, [sample_risk], properties=sample_properties)
        assert "exportAnswers" not in html


class TestAssessmentResidual:
    """Verify the control-effectiveness / residual-risk wiring is emitted."""

    @pytest.fixture
    def risk_html(self, sample_sections, sample_properties, sample_risk):
        return render_assessment(sample_sections, [sample_risk], properties=sample_properties)

    @pytest.fixture
    def risk_js(self, sample_sections, sample_properties, sample_risk):
        return render_assessment_app_js(
            sample_sections, [sample_risk], properties=sample_properties
        )

    def test_residual_getter_emitted_per_risk(self, risk_js):
        assert "get r1_residual()" in risk_js

    def test_controlled_level_in_colour_map(self, risk_html):
        assert "'controlled':" in risk_html

    def test_effectiveness_state_seeded(self, risk_js):
        assert "control_effectiveness: Alpine.$persist({" in risk_js
        assert "residual_likelihood: Alpine.$persist({" in risk_js
        assert "residual_consequence: Alpine.$persist({" in risk_js


# ---------------------------------------------------------------------------
# render_*_app_js — factory smoke tests
# ---------------------------------------------------------------------------


class TestQuestionnaireAppJs:
    def test_registers_alpine_component(self, binary_questionnaire_js):
        assert "alpine:init" in binary_questionnaire_js
        assert "Alpine.data('questionnaire'" in binary_questionnaire_js

    def test_no_html_autoescape_leaks(self, binary_questionnaire_js):
        for entity in ("&#34;", "&#39;", "&quot;", "&amp;", "&gt;", "&lt;"):
            assert entity not in binary_questionnaire_js, (
                f"autoescape leak: {entity} in app-questionnaire.js"
            )

    def test_persist_keys_prefixed(self, binary_questionnaire_js):
        assert ".as('_x_q_activeTab')" in binary_questionnaire_js
        assert ".as('_x_q_answers')" in binary_questionnaire_js
        # Must not bleed into the unprefixed namespace
        assert ".as('_x_answers')" not in binary_questionnaire_js

    def test_property_getter_emitted(self, binary_questionnaire_js):
        assert "get prop_p1()" in binary_questionnaire_js
        assert "get prop_p2()" in binary_questionnaire_js


class TestAssessmentAppJs:
    def test_registers_alpine_component(self, binary_assessment_js):
        assert "alpine:init" in binary_assessment_js
        assert "Alpine.data('assessment'" in binary_assessment_js

    def test_no_html_autoescape_leaks(self, binary_assessment_js):
        for entity in ("&#34;", "&#39;", "&quot;", "&amp;", "&gt;", "&lt;"):
            assert entity not in binary_assessment_js, (
                f"autoescape leak: {entity} in app-assessment.js"
            )

    def test_persist_keys_prefixed(self, binary_assessment_js):
        assert ".as('_x_a_activeTab')" in binary_assessment_js
        assert ".as('_x_a_answers')" in binary_assessment_js
        assert ".as('_x_a_control_effectiveness')" in binary_assessment_js
        # Must not bleed into the questionnaire's namespace
        assert ".as('_x_q_answers')" not in binary_assessment_js

    def test_risk_getter_emitted(self, sample_sections, sample_properties, sample_risk):
        js = render_assessment_app_js(sample_sections, [sample_risk], properties=sample_properties)
        assert "get r1()" in js
        assert "get r1_residual()" in js

    def test_control_getter_emitted(
        self, sample_sections, sample_properties, sample_risk, sample_control
    ):
        js = render_assessment_app_js(
            sample_sections, [sample_risk], [sample_control], sample_properties
        )
        assert "get ctrl_ctrl1()" in js
        assert "this.prop_prop_a === true" in js

    def test_risk_rules_js_from_property(self, sample_sections, sample_properties, sample_risk):
        # Risk.rules_js (@property) drives the rules array in each risk getter.
        js = render_assessment_app_js(sample_sections, [sample_risk], properties=sample_properties)
        # sample_risk has two conditions → two rule expressions.
        assert js.count("? {likelihood:") >= 2
