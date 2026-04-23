"""Tests for render.py — template preparation and rendering."""

from __future__ import annotations

import pytest

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
from render import (
    _compile_property_getter,
    _compile_question_visibility,
    _detail_show_js,
    render_app_js,
    render_form,
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
# render_form / render_app_js — integration
# ---------------------------------------------------------------------------


class TestRenderForm:
    def test_returns_html(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_alpine_xdata(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert 'x-data="app"' in html

    def test_sections_appear_as_tabs(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert "sec1" in html
        assert "Section One" in html

    def test_property_getters_in_html(self, sample_sections, sample_properties):
        html = render_form(sample_sections, [], properties=sample_properties)
        assert "prop_prop_a" in html
        assert "prop_prop_b" in html

    def test_with_risks(self, sample_sections, sample_properties):
        risk = Risk(
            id="r1",
            description="Test risk",
            conditions=(
                ConditionMapping(
                    properties=("prop_a",),
                    mode="all",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        html = render_form(sample_sections, [risk], properties=sample_properties)
        assert "r1" in html
        assert "Test risk" in html

    def test_with_controls(self, sample_sections, sample_control, sample_properties):
        risk = Risk(
            id="r1",
            description="D",
            conditions=(
                ConditionMapping(
                    properties=("prop_a",),
                    mode="all",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        html = render_form(sample_sections, [risk], [sample_control], sample_properties)
        js = render_app_js(sample_sections, [risk], [sample_control], sample_properties)
        assert "Encryption enabled" in html
        assert "this.prop_prop_a === true" in js

    def test_with_details(self, sample_sections, sample_properties, sample_detail):
        js = render_app_js(
            sample_sections, [], properties=sample_properties, details=[sample_detail]
        )
        assert "details:" in js
        assert "det1" in js

    def test_detail_rendered_beside_relevant_risk(self, sample_sections, sample_properties):
        risk = Risk(
            id="r1",
            description="Risk tied to prop_a",
            conditions=(
                ConditionMapping(
                    properties=("prop_a",),
                    mode="all",
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
        html = render_form(
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
        html = render_form([sec], [], properties=sample_properties, details=[sample_detail])
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
        html = render_form([sec], [], properties=[root])
        # No conditional x-show wrapping an unconditional question.
        assert 'x-show="true"' not in html

    def test_conditional_question_has_xshow(self):
        root = Property(id="root", description="Root")
        child = Property(id="child", description="Child", parents=("root",))
        q = BinaryQuestion(id="q1", text="Conditional", properties=("child",))
        sub = SubSection(title="S", description="", questions=(q,))
        sec = Section(id="s", title="S", description="", subsections=(sub,))
        html = render_form([sec], [], properties=[root, child])
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
        html = render_form([sec], [], properties=props)
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
        html = render_form([sec], [], properties=props)
        # The subsection's <div class="box"> inherits the OR of its questions' conditions.
        assert '<div class="box stack-md" x-show="(prop_root === true)">' in html


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


@pytest.fixture
def binary_app_js(binary_sections, binary_properties):
    return render_app_js(binary_sections, [], properties=binary_properties)


class TestRenderFormMetadata:
    """Verify build-time metadata arrays are embedded in the Alpine app bundle."""

    def test_question_ids_present(self, binary_app_js):
        assert '_questionIds: ["q_bin", "q_bin2"]' in binary_app_js

    def test_risk_ids_empty(self, binary_app_js):
        assert "_riskIds: []" in binary_app_js

    def test_control_ids_empty(self, binary_app_js):
        assert "_controlIds: {}" in binary_app_js


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


class TestRenderFormResidual:
    """Verify the control-effectiveness / residual-risk wiring is emitted."""

    @pytest.fixture
    def risk_html(self, sample_sections, sample_properties, sample_risk):
        return render_form(sample_sections, [sample_risk], properties=sample_properties)

    @pytest.fixture
    def risk_app_js(self, sample_sections, sample_properties, sample_risk):
        return render_app_js(sample_sections, [sample_risk], properties=sample_properties)

    def test_residual_getter_emitted_per_risk(self, risk_app_js):
        assert "get r1_residual()" in risk_app_js

    def test_controlled_level_in_colour_map(self, risk_html):
        assert "'controlled':" in risk_html

    def test_effectiveness_state_seeded(self, risk_app_js):
        assert "control_effectiveness: Alpine.$persist({" in risk_app_js
        assert "residual_likelihood: Alpine.$persist({" in risk_app_js
        assert "residual_consequence: Alpine.$persist({" in risk_app_js

    def test_assessed_risks_state_removed(self, risk_html, risk_app_js):
        assert "assessed_risks: Alpine.$persist" not in risk_app_js
        assert "this.assessed_risks" not in risk_html
        assert "this.assessed_risks" not in risk_app_js


class TestRenderAppJs:
    """Smoke tests for render_app_js — the Alpine factory module."""

    def test_registers_alpine_component(self, binary_app_js):
        assert "alpine:init" in binary_app_js
        assert "Alpine.data('app'" in binary_app_js

    def test_no_html_autoescape_leaks(self, binary_app_js):
        for entity in ("&#34;", "&#39;", "&quot;", "&amp;", "&gt;", "&lt;"):
            assert entity not in binary_app_js, f"autoescape leak: {entity} in app.js"

    def test_persist_keys_explicit(self, binary_app_js):
        assert ".as('_x_activeTab')" in binary_app_js
        assert ".as('_x_answers')" in binary_app_js

    def test_property_getter_emitted(self, binary_app_js):
        assert "get prop_p1()" in binary_app_js
        assert "get prop_p2()" in binary_app_js

    def test_risk_getter_emitted(self, sample_sections, sample_properties, sample_risk):
        js = render_app_js(sample_sections, [sample_risk], properties=sample_properties)
        assert "get r1()" in js
        assert "get r1_residual()" in js

    def test_control_getter_emitted(
        self, sample_sections, sample_properties, sample_risk, sample_control
    ):
        js = render_app_js(sample_sections, [sample_risk], [sample_control], sample_properties)
        assert "get ctrl_ctrl1()" in js
        assert "this.prop_prop_a === true" in js

    def test_risk_rules_js_from_property(self, sample_sections, sample_properties, sample_risk):
        # Risk.rules_js (@property) drives the rules array in each risk getter.
        js = render_app_js(sample_sections, [sample_risk], properties=sample_properties)
        # sample_risk has two conditions → two rule expressions.
        assert js.count("? {likelihood:") >= 2
