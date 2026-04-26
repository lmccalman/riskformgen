"""Behaviour tests for the JS emitted by the per-tool factory renderers.

Each test builds a minimal form, compiles one of the Alpine factories
(questionnaire or assessment), and asserts on what the compiled `prop_*` /
risk / residual / `ctrl_*` getters *return* as answers change. The substring
tests in `test_render.py` / `test_models.py` pin the compiler's output
shape; these tests pin the runtime semantics.

Most tests run against the assessment factory because it carries the full
surface (answers, details, prop_, ctrl_, risk, residual, control_effectiveness,
mandated_*). The questionnaire factory is exercised separately for the
clearAnswers / `_x_q_*` migration semantics that are unique to it.
"""

from __future__ import annotations

import pytest

from models import (
    BinaryQuestion,
    ConditionMapping,
    Control,
    ControlEffect,
    Detail,
    Property,
    Risk,
    Section,
    SubSection,
)
from render import _compile_question_visibility, _detail_show_js
from tests.js_harness import Scope, build_assessment_scope, build_questionnaire_scope


def _form(
    questions: list[BinaryQuestion],
    properties: list[Property],
    risks: list[Risk] | None = None,
    controls: list[Control] | None = None,
    details: list[Detail] | None = None,
    *,
    persisted_state: dict[str, object] | None = None,
) -> Scope:
    """Build an assessment scope — full surface (prop_, ctrl_, risk, residual)."""
    sub = SubSection(title="t", description="", questions=tuple(questions))
    sec = Section(id="s1", title="S", description="", subsections=(sub,))
    return build_assessment_scope(
        [sec],
        properties,
        risks or [],
        controls,
        details,
        persisted_state=persisted_state,
    )


def _questionnaire_form(
    questions: list[BinaryQuestion],
    properties: list[Property],
    details: list[Detail] | None = None,
    *,
    persisted_state: dict[str, object] | None = None,
) -> Scope:
    """Build a questionnaire scope — answers, details, and prop_ only."""
    sub = SubSection(title="t", description="", questions=tuple(questions))
    sec = Section(id="s1", title="S", description="", subsections=(sub,))
    return build_questionnaire_scope([sec], properties, details, persisted_state=persisted_state)


# ---------------------------------------------------------------------------
# Property cascade — root question
# ---------------------------------------------------------------------------


class TestPropertyCascadeRoot:
    @pytest.fixture
    def scope(self) -> Scope:
        q = BinaryQuestion(id="q1", text="?", properties=("p1",))
        p = Property(id="p1", description="")
        return _form([q], [p])

    def test_yes_makes_prop_true(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        assert scope.prop("p1") is True

    def test_no_makes_prop_false(self, scope: Scope) -> None:
        scope.set_answer("q1", "no")
        assert scope.prop("p1") is False

    def test_unanswered_is_null(self, scope: Scope) -> None:
        assert scope.prop("p1") is None


# ---------------------------------------------------------------------------
# Property cascade — child with activation="all"
# ---------------------------------------------------------------------------


class TestPropertyCascadeAllMode:
    @pytest.fixture
    def scope(self) -> Scope:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        q3 = BinaryQuestion(id="q3", text="", properties=("p3",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        p3 = Property(id="p3", description="", parents=("p1", "p2"), activation="all")
        return _form([q1, q2, q3], [p1, p2, p3])

    def test_any_parent_false_forces_false(self, scope: Scope) -> None:
        scope.set_answer("q1", "no")
        scope.set_answer("q2", "yes")
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is False

    def test_all_parents_true_and_own_yes_is_true(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "yes")
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is True

    def test_all_parents_true_but_own_no_is_false(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "yes")
        scope.set_answer("q3", "no")
        assert scope.prop("p3") is False

    def test_some_parent_null_none_false_is_null(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        # q2 unanswered → p2 null
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is None

    def test_false_beats_null(self, scope: Scope) -> None:
        # Both a null parent and a false parent present — false wins.
        scope.set_answer("q2", "no")  # p2 false
        # q1 unanswered → p1 null
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is False


# ---------------------------------------------------------------------------
# Property cascade — child with activation="any"
# ---------------------------------------------------------------------------


class TestDerivedPropertyWithoutQuestion:
    """A property with parents and no question is a pure computed truth — true
    when its parent activation is satisfied, false when forced false by parent
    cascade, null otherwise. No question is required (or visible) for it."""

    def test_all_mode_true_when_all_parents_true(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        derived = Property(id="derived", description="", parents=("p1", "p2"), activation="all")
        scope = _form([q1, q2], [p1, p2, derived])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "yes")
        assert scope.prop("derived") is True

    def test_all_mode_false_when_any_parent_false(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        derived = Property(id="derived", description="", parents=("p1", "p2"), activation="all")
        scope = _form([q1, q2], [p1, p2, derived])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        assert scope.prop("derived") is False

    def test_all_mode_null_when_any_parent_unanswered(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        derived = Property(id="derived", description="", parents=("p1", "p2"), activation="all")
        scope = _form([q1, q2], [p1, p2, derived])
        scope.set_answer("q1", "yes")
        # q2 unanswered → p2 null → derived null
        assert scope.prop("derived") is None

    def test_any_mode_true_when_one_parent_true(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        derived = Property(id="derived", description="", parents=("p1", "p2"), activation="any")
        scope = _form([q1, q2], [p1, p2, derived])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        assert scope.prop("derived") is True

    def test_any_mode_false_when_all_parents_false(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        derived = Property(id="derived", description="", parents=("p1", "p2"), activation="any")
        scope = _form([q1, q2], [p1, p2, derived])
        scope.set_answer("q1", "no")
        scope.set_answer("q2", "no")
        assert scope.prop("derived") is False


class TestPropertyCascadeAnyMode:
    @pytest.fixture
    def scope(self) -> Scope:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        q3 = BinaryQuestion(id="q3", text="", properties=("p3",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        p3 = Property(id="p3", description="", parents=("p1", "p2"), activation="any")
        return _form([q1, q2, q3], [p1, p2, p3])

    def test_all_parents_false_is_false(self, scope: Scope) -> None:
        scope.set_answer("q1", "no")
        scope.set_answer("q2", "no")
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is False

    def test_one_parent_true_and_own_yes_is_true(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is True

    def test_one_parent_true_but_own_no_is_false(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        scope.set_answer("q3", "no")
        assert scope.prop("p3") is False

    def test_no_parent_true_some_null_is_null(self, scope: Scope) -> None:
        # q1 unanswered → p1 null; p2 false. No parent true, not all false → null.
        scope.set_answer("q2", "no")
        scope.set_answer("q3", "yes")
        assert scope.prop("p3") is None


# ---------------------------------------------------------------------------
# Question visibility
# ---------------------------------------------------------------------------


class TestQuestionVisibility:
    """A child question is visible only once its parent property is explicitly
    `true` (the parent question answered "yes"). An unanswered parent (`null`)
    or a parent answered "no" (`false`) keeps the child hidden — the form
    expands progressively as the user answers."""

    @pytest.fixture
    def scope_and_expr(self) -> tuple[Scope, str]:
        q_parent = BinaryQuestion(id="q_parent", text="", properties=("p_parent",))
        q_child = BinaryQuestion(id="q_child", text="", properties=("p_child",))
        p_parent = Property(id="p_parent", description="")
        p_child = Property(
            id="p_child",
            description="",
            parents=("p_parent",),
            activation="all",
        )
        props = [p_parent, p_child]
        prop_by_id = {p.id: p for p in props}
        vis_expr = _compile_question_visibility(q_child, prop_by_id)
        scope = _form([q_parent, q_child], props)
        return scope, vis_expr

    def test_hidden_when_parent_unanswered(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        assert scope.visibility(expr) is False

    def test_visible_when_parent_yes(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_parent", "yes")
        assert scope.visibility(expr) is True

    def test_hidden_when_parent_no(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_parent", "no")
        assert scope.visibility(expr) is False


class TestQuestionVisibilityAnyMode:
    """For an `activation: any` child property, the child question is visible
    when *any* of its parents is explicitly `true`. Pins the OR branch in
    `_compile_question_visibility`."""

    @pytest.fixture
    def scope_and_expr(self) -> tuple[Scope, str]:
        q_pa = BinaryQuestion(id="q_pa", text="", properties=("pa",))
        q_pb = BinaryQuestion(id="q_pb", text="", properties=("pb",))
        q_child = BinaryQuestion(id="q_child", text="", properties=("p_child",))
        pa = Property(id="pa", description="")
        pb = Property(id="pb", description="")
        p_child = Property(
            id="p_child",
            description="",
            parents=("pa", "pb"),
            activation="any",
        )
        props = [pa, pb, p_child]
        prop_by_id = {p.id: p for p in props}
        vis_expr = _compile_question_visibility(q_child, prop_by_id)
        scope = _form([q_pa, q_pb, q_child], props)
        return scope, vis_expr

    def test_hidden_when_both_parents_unanswered(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        assert scope.visibility(expr) is False

    def test_hidden_when_both_parents_no(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_pa", "no")
        scope.set_answer("q_pb", "no")
        assert scope.visibility(expr) is False

    def test_visible_when_first_parent_yes(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_pa", "yes")
        # second parent left unanswered — any-mode still shows the child
        assert scope.visibility(expr) is True

    def test_visible_when_second_parent_yes(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_pb", "yes")
        assert scope.visibility(expr) is True


class TestQuestionVisibilityMultiProperty:
    """A question targeting multiple properties is visible when *any* of those
    properties is reachable. Pins the cross-property OR aggregation in
    `_compile_question_visibility`."""

    @pytest.fixture
    def scope_and_expr(self) -> tuple[Scope, str]:
        # q_target sets both p1 and p2; p1 is gated by root1, p2 by root2.
        # Question visibility is the OR of (root1 satisfied, root2 satisfied).
        q_root1 = BinaryQuestion(id="q_root1", text="", properties=("root1",))
        q_root2 = BinaryQuestion(id="q_root2", text="", properties=("root2",))
        q_target = BinaryQuestion(id="q_target", text="", properties=("p1", "p2"))
        root1 = Property(id="root1", description="")
        root2 = Property(id="root2", description="")
        p1 = Property(id="p1", description="", parents=("root1",))
        p2 = Property(id="p2", description="", parents=("root2",))
        props = [root1, root2, p1, p2]
        prop_by_id = {p.id: p for p in props}
        vis_expr = _compile_question_visibility(q_target, prop_by_id)
        scope = _form([q_root1, q_root2, q_target], props)
        return scope, vis_expr

    def test_hidden_when_neither_root_yes(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        assert scope.visibility(expr) is False

    def test_visible_when_first_root_yes(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_root1", "yes")
        assert scope.visibility(expr) is True

    def test_visible_when_second_root_yes(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q_root2", "yes")
        assert scope.visibility(expr) is True


# ---------------------------------------------------------------------------
# Risk aggregation
# ---------------------------------------------------------------------------


class TestRiskAggregation:
    def _build(self, conditions: tuple[ConditionMapping, ...]) -> Scope:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        risk = Risk(id="r1", description="", conditions=conditions)
        return _form([q1, q2], [p1, p2], risks=[risk])

    def test_no_conditions_fire_is_not_applicable(self) -> None:
        scope = self._build(
            (
                ConditionMapping(
                    property="p1",
                    likelihood="likely",
                    consequence="major",
                ),
            )
        )
        # q1 unanswered → p1 null → condition does not fire
        assert scope.risk("r1") == {
            "level": "not_applicable",
            "likelihood": None,
            "consequence": None,
        }

    def test_single_condition_passes_through(self) -> None:
        scope = self._build(
            (
                ConditionMapping(
                    property="p1",
                    likelihood="possible",
                    consequence="medium",
                ),
            )
        )
        scope.set_answer("q1", "yes")
        assert scope.risk("r1") == {
            "likelihood": "possible",
            "consequence": "medium",
            "level": "medium",
        }

    def test_worst_per_dimension_is_independent(self) -> None:
        # Condition A: high likelihood, low consequence.
        # Condition B: low likelihood, high consequence.
        # Expected worst per axis: likely / major → high.
        scope = self._build(
            (
                ConditionMapping(
                    property="p1",
                    likelihood="likely",
                    consequence="minor",
                ),
                ConditionMapping(
                    property="p2",
                    likelihood="rare",
                    consequence="major",
                ),
            )
        )
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "yes")
        assert scope.risk("r1") == {
            "likelihood": "likely",
            "consequence": "major",
            "level": "high",
        }

    def test_mixed_firing_only_uses_firing_conditions(self) -> None:
        """Aggregation uses *only* the conditions whose property is true.
        Worst-per-axis must ignore non-firing conditions, even if their
        declared (likelihood, consequence) would have been worse. Pins
        SPEC §Risks → "A condition fires when its property is true. Only
        true satisfies; an unset/null property never does."""
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        q3 = BinaryQuestion(id="q3", text="", properties=("p3",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        p3 = Property(id="p3", description="")
        # The *worst* declared values are on conditions that won't fire (p2
        # left unanswered, p3 explicitly false). The fired condition is p1
        # only — a low/medium pair.
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="rare", consequence="medium"),
                ConditionMapping(property="p2", likelihood="almost_certain", consequence="major"),
                ConditionMapping(property="p3", likelihood="likely", consequence="major"),
            ),
        )
        scope = _form([q1, q2, q3], [p1, p2, p3], risks=[risk])
        scope.set_answer("q1", "yes")
        # q2 unanswered → p2 null → its condition does not fire
        scope.set_answer("q3", "no")  # p3 false → its condition does not fire
        assert scope.risk("r1") == {
            "likelihood": "rare",
            "consequence": "medium",
            "level": "low",
        }


# ---------------------------------------------------------------------------
# _worst helper
# ---------------------------------------------------------------------------


class TestWorstHelper:
    """`_worst(results, dim, scale)` picks the highest-severity value along
    one axis, ignoring null entries. It's the engine of worst-per-dimension
    aggregation; tests in `TestRiskAggregation` cover it indirectly, but
    the all-null sentinel and empty-input cases are easier to assert here."""

    @pytest.fixture
    def scope(self) -> Scope:
        # Any minimal form will do — we only need a scope on which `_worst`
        # is defined; it doesn't depend on form contents.
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        return _form([q], [p])

    def test_empty_input_returns_null(self, scope: Scope) -> None:
        assert (
            scope.eval("scope._worst([], 'likelihood', ['rare', 'unlikely', 'possible'])") is None
        )

    def test_all_null_returns_null(self, scope: Scope) -> None:
        result = scope.eval(
            "scope._worst("
            "[{likelihood: null, consequence: null},"
            " {likelihood: null, consequence: null}],"
            " 'likelihood', ['rare', 'unlikely', 'possible'])"
        )
        assert result is None

    def test_picks_highest_index_in_scale(self, scope: Scope) -> None:
        result = scope.eval(
            "scope._worst("
            "[{likelihood: 'rare', consequence: 'minor'},"
            " {likelihood: 'likely', consequence: 'minor'},"
            " {likelihood: 'unlikely', consequence: 'minor'}],"
            " 'likelihood', ['rare', 'unlikely', 'possible', 'likely', 'almost_certain'])"
        )
        assert result == "likely"

    def test_skips_null_entries_among_others(self, scope: Scope) -> None:
        result = scope.eval(
            "scope._worst("
            "[{likelihood: null},"
            " {likelihood: 'unlikely'},"
            " {likelihood: 'rare'}],"
            " 'likelihood', ['rare', 'unlikely', 'possible'])"
        )
        assert result == "unlikely"

    def test_single_entry_returns_its_value(self, scope: Scope) -> None:
        result = scope.eval(
            "scope._worst("
            "[{likelihood: 'possible'}],"
            " 'likelihood', ['rare', 'unlikely', 'possible'])"
        )
        assert result == "possible"


# ---------------------------------------------------------------------------
# Risk matrix lookup
# ---------------------------------------------------------------------------


class TestRiskMatrixLookup:
    @pytest.mark.parametrize(
        "likelihood,consequence,level",
        [
            ("rare", "minor", "low"),
            ("unlikely", "major", "medium"),
            ("possible", "medium", "medium"),
            ("almost_certain", "major", "high"),
        ],
    )
    def test_sentinel_lookups(self, likelihood: str, consequence: str, level: str) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(
                    property="p1",
                    likelihood=likelihood,
                    consequence=consequence,
                ),
            ),
        )
        scope = _form([q], [p], risks=[risk])
        scope.set_answer("q1", "yes")
        assert scope.risk("r1")["level"] == level


# ---------------------------------------------------------------------------
# Residual risk
# ---------------------------------------------------------------------------


class TestResidualRisk:
    @pytest.fixture
    def scope(self) -> Scope:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(
                    property="p1",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        scope = _form([q], [p], risks=[risk])
        scope.set_answer("q1", "yes")
        # Inherent: likely / major → high
        return scope

    def test_not_applicable_stays_not_applicable(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(
                    property="p1",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        scope = _form([q], [p], risks=[risk])
        # q1 unanswered → no conditions fire → inherent not_applicable
        scope.set_effectiveness("r1", "controlled")
        assert scope.residual("r1")["level"] == "not_applicable"

    def test_default_effectiveness_returns_inherent(self, scope: Scope) -> None:
        assert scope.residual("r1") == scope.risk("r1")

    def test_ineffective_returns_inherent(self, scope: Scope) -> None:
        scope.set_effectiveness("r1", "ineffective")
        assert scope.residual("r1") == scope.risk("r1")

    def test_controlled_sets_level_to_controlled(self, scope: Scope) -> None:
        scope.set_effectiveness("r1", "controlled")
        assert scope.residual("r1") == {
            "likelihood": "likely",
            "consequence": "major",
            "level": "controlled",
        }

    def test_partial_with_both_set_uses_matrix_on_residual(self, scope: Scope) -> None:
        scope.set_effectiveness("r1", "partial")
        scope.set_residual("r1", "unlikely", "medium")
        assert scope.residual("r1") == {
            "likelihood": "unlikely",
            "consequence": "medium",
            "level": "medium",
        }

    def test_partial_with_missing_residual_falls_back_to_inherent(self, scope: Scope) -> None:
        scope.set_effectiveness("r1", "partial")
        # residual_likelihood and residual_consequence both still ''
        assert scope.residual("r1") == scope.risk("r1")


# ---------------------------------------------------------------------------
# Control getters
# ---------------------------------------------------------------------------


class TestControlGetters:
    @pytest.fixture
    def scope(self) -> Scope:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(
                    property="p1",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        ctrl = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        return _form([q], [p], risks=[risk], controls=[ctrl])

    def test_control_false_when_property_null(self, scope: Scope) -> None:
        assert scope.ctrl("c1") is False

    def test_control_false_when_property_false(self, scope: Scope) -> None:
        scope.set_answer("q1", "no")
        assert scope.ctrl("c1") is False

    def test_control_true_when_property_true(self, scope: Scope) -> None:
        scope.set_answer("q1", "yes")
        assert scope.ctrl("c1") is True


# ---------------------------------------------------------------------------
# Detail show expressions
# ---------------------------------------------------------------------------


class TestDetailShow:
    @pytest.fixture
    def scope_and_expr(self) -> tuple[Scope, str]:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(
                    property="p1",
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )
        detail = Detail(id="d1", description="", properties=("p1",))
        scope = _form([q], [p], risks=[risk], details=[detail])
        show_js = _detail_show_js(detail.properties)
        return scope, show_js

    def test_hidden_when_property_null(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        assert scope.visibility(expr) is False

    def test_hidden_when_property_false(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q1", "no")
        assert scope.visibility(expr) is False

    def test_shown_when_property_true(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q1", "yes")
        assert scope.visibility(expr) is True


class TestDetailShowMultiProperty:
    """A detail with multiple properties is shown when *any* one of them is
    `true`. Pins the OR semantics in `_detail_show_js` against mixed
    parent state, where the single-property tests above cannot."""

    @pytest.fixture
    def scope_and_expr(self) -> tuple[Scope, str]:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
                ConditionMapping(property="p2", likelihood="rare", consequence="minor"),
            ),
        )
        detail = Detail(id="d1", description="", properties=("p1", "p2"))
        scope = _form([q1, q2], [p1, p2], risks=[risk], details=[detail])
        show_js = _detail_show_js(detail.properties)
        return scope, show_js

    def test_hidden_when_both_null(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        assert scope.visibility(expr) is False

    def test_hidden_when_both_false(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q1", "no")
        scope.set_answer("q2", "no")
        assert scope.visibility(expr) is False

    def test_shown_when_only_first_true(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        assert scope.visibility(expr) is True

    def test_shown_when_only_second_true(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q1", "no")
        scope.set_answer("q2", "yes")
        assert scope.visibility(expr) is True

    def test_shown_when_one_true_one_null(self, scope_and_expr: tuple[Scope, str]) -> None:
        scope, expr = scope_and_expr
        scope.set_answer("q1", "yes")
        # q2 unanswered → p2 null
        assert scope.visibility(expr) is True


# ---------------------------------------------------------------------------
# Schema migration — assessment factory init() seeds missing keys
# ---------------------------------------------------------------------------


class TestAssessmentSchemaMigration:
    """Assessment factory's init() fills any ID present in the current build
    but absent from the localStorage-restored object with its default (empty
    string for most fields, `false` for mandated-control checkboxes).

    Persisted keys are prefixed `_x_a_*` (questionnaire factory uses
    `_x_q_*`)."""

    def _risk(self, rid: str, prop_id: str = "p1") -> Risk:
        return Risk(
            id=rid,
            description="",
            conditions=(
                ConditionMapping(
                    property=prop_id,
                    likelihood="likely",
                    consequence="major",
                ),
            ),
        )

    def test_answers_missing_key_gets_default(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        scope = _form([q1, q2], [p1, p2], persisted_state={"_x_a_answers": {"q1": "yes"}})
        assert scope.eval("scope.answers") == {"q1": "yes", "q2": ""}

    def test_details_missing_key_gets_default(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        d1 = Detail(id="d1", description="", properties=("p1",))
        d2 = Detail(id="d2", description="", properties=("p1",))
        scope = _form(
            [q],
            [p],
            details=[d1, d2],
            persisted_state={"_x_a_details": {"d1": "prior note"}},
        )
        assert scope.eval("scope.details") == {"d1": "prior note", "d2": ""}

    @pytest.mark.parametrize(
        "persist_key,field_name",
        [
            ("_x_a_justifications", "justifications"),
            ("_x_a_control_effectiveness", "control_effectiveness"),
            ("_x_a_residual_likelihood", "residual_likelihood"),
            ("_x_a_residual_consequence", "residual_consequence"),
        ],
    )
    def test_risk_keyed_field_seeds_missing_risk(self, persist_key: str, field_name: str) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        scope = _form(
            [q],
            [p],
            risks=[self._risk("r1"), self._risk("r2")],
            persisted_state={persist_key: {"r1": "prior"}},
        )
        assert scope.eval(f"scope.{field_name}") == {"r1": "prior", "r2": ""}

    def test_mandated_controls_missing_risk_fills_all_controls_false(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r1 = self._risk("r1")
        r2 = self._risk("r2")
        c1 = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r2"),),
        )
        scope = _form(
            [q],
            [p],
            risks=[r1, r2],
            controls=[c1],
            persisted_state={"_x_a_mandated_controls": {"r1": {}}},
        )
        assert scope.eval("scope.mandated_controls") == {"r1": {}, "r2": {"c1": False}}

    def test_mandated_controls_existing_risk_seeds_missing_control(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r1 = self._risk("r1")
        c1 = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        c2 = Control(
            id="c2",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        scope = _form(
            [q],
            [p],
            risks=[r1],
            controls=[c1, c2],
            persisted_state={"_x_a_mandated_controls": {"r1": {"c1": True}}},
        )
        assert scope.eval("scope.mandated_controls") == {"r1": {"c1": True, "c2": False}}

    def test_mandated_comments_missing_risk_fills_all_controls_empty(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r1 = self._risk("r1")
        r2 = self._risk("r2")
        c1 = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r2"),),
        )
        scope = _form(
            [q],
            [p],
            risks=[r1, r2],
            controls=[c1],
            persisted_state={"_x_a_mandated_comments": {"r1": {}}},
        )
        assert scope.eval("scope.mandated_comments") == {"r1": {}, "r2": {"c1": ""}}

    def test_mandated_comments_existing_risk_seeds_missing_control(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r1 = self._risk("r1")
        c1 = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        c2 = Control(
            id="c2",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        scope = _form(
            [q],
            [p],
            risks=[r1],
            controls=[c1, c2],
            persisted_state={"_x_a_mandated_comments": {"r1": {"c1": "prior note"}}},
        )
        assert scope.eval("scope.mandated_comments") == {"r1": {"c1": "prior note", "c2": ""}}

    def test_existing_values_are_not_clobbered(self) -> None:
        """init() is additive only — it must never overwrite restored values."""
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        r1 = self._risk("r1")
        scope = _form(
            [q1, q2],
            [p1, p2],
            risks=[r1],
            persisted_state={
                "_x_a_answers": {"q1": "yes", "q2": "no"},
                "_x_a_control_effectiveness": {"r1": "controlled"},
                "_x_a_justifications": {"r1": "prior justification"},
            },
        )
        assert scope.eval("scope.answers") == {"q1": "yes", "q2": "no"}
        assert scope.eval("scope.control_effectiveness") == {"r1": "controlled"}
        assert scope.eval("scope.justifications") == {"r1": "prior justification"}

    def test_no_persisted_state_is_noop(self) -> None:
        """Without an injected persisted state, init() should see the full seed
        and make no changes — guards the common (non-migration) case."""
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r1 = self._risk("r1")
        c1 = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        scope = _form([q], [p], risks=[r1], controls=[c1])
        assert scope.eval("scope.answers") == {"q1": ""}
        assert scope.eval("scope.mandated_controls") == {"r1": {"c1": False}}
        assert scope.eval("scope.mandated_comments") == {"r1": {"c1": ""}}

    def test_init_is_idempotent(self) -> None:
        """init() only fills *missing* keys; calling it a second time on
        already-migrated state must be a no-op. A regression here would
        clobber user state on hot-reload or dev-server reinit."""
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        r1 = self._risk("r1")
        c1 = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        scope = _form(
            [q1, q2],
            [p1, p2],
            risks=[r1],
            controls=[c1],
            persisted_state={
                "_x_a_answers": {"q1": "yes"},
                "_x_a_mandated_controls": {"r1": {"c1": True}},
            },
        )
        snapshot_keys = (
            "answers",
            "details",
            "control_effectiveness",
            "residual_likelihood",
            "residual_consequence",
            "justifications",
            "mandated_controls",
            "mandated_comments",
        )
        before = {k: scope.eval(f"scope.{k}") for k in snapshot_keys}
        scope.eval("scope.init();")
        after = {k: scope.eval(f"scope.{k}") for k in snapshot_keys}
        assert before == after


class TestQuestionnaireSchemaMigration:
    """Questionnaire factory has a smaller surface — only answers and details
    persist (under `_x_q_*`). Pins that the questionnaire's init() fills
    those gaps."""

    def test_answers_missing_key_gets_default(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        scope = _questionnaire_form(
            [q1, q2],
            [p1, p2],
            persisted_state={"_x_q_answers": {"q1": "yes"}},
        )
        assert scope.eval("scope.answers") == {"q1": "yes", "q2": ""}

    def test_details_missing_key_gets_default(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        d1 = Detail(id="d1", description="", properties=("p1",))
        d2 = Detail(id="d2", description="", properties=("p1",))
        scope = _questionnaire_form(
            [q],
            [p],
            details=[d1, d2],
            persisted_state={"_x_q_details": {"d1": "prior note"}},
        )
        assert scope.eval("scope.details") == {"d1": "prior note", "d2": ""}


# ---------------------------------------------------------------------------
# clearAnswers / clearAssessment
# ---------------------------------------------------------------------------


class TestQuestionnaireClearAnswers:
    """The questionnaire's clearAnswers wipes answers + details only — the
    questionnaire factory has no assessment state to wipe."""

    def _populate(self) -> Scope:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        d = Detail(id="d1", description="", properties=("p1",))
        scope = _questionnaire_form([q1, q2], [p1, p2], details=[d])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        scope.set_detail("d1", "field notes")
        return scope

    def test_clear_resets_answers_and_details(self) -> None:
        scope = self._populate()
        scope.eval("scope.clearAnswers();")
        assert scope.eval("scope.answers") == {"q1": "", "q2": ""}
        assert scope.eval("scope.details") == {"d1": ""}

    def test_clear_cancel_keeps_state(self) -> None:
        scope = self._populate()
        scope.eval("confirm = () => false;")
        scope.eval("scope.clearAnswers();")
        assert scope.eval("scope.answers") == {"q1": "yes", "q2": "no"}
        assert scope.eval("scope.details") == {"d1": "field notes"}


class TestExportSnapshotsBakedValues:
    """The registry consumes the JSON exports without re-evaluating the
    property DAG or the risk conditions. That contract relies on the
    factories writing their resolved state at export time. Pin both:

    1. Questionnaire export carries `properties` snapshotting every
       `prop_*` getter under the same key as the property id.
    2. Assessment export carries `inherent` snapshotting each risk's
       `{likelihood, consequence, level, firing_conditions}` plus the
       same `properties` map.

    A regression here would silently feed stale data into the registry.
    """

    def test_questionnaire_property_snapshot_round_trips(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        scope = _questionnaire_form([q1, q2], [p1, p2])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")

        snapshot = scope.eval("scope._propertySnapshot()")
        assert snapshot == {"p1": True, "p2": False}

    def test_questionnaire_property_snapshot_includes_null_when_unanswered(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        scope = _questionnaire_form([q], [p])

        snapshot = scope.eval("scope._propertySnapshot()")
        # Unanswered → null (matches the prop_* getter return).
        assert snapshot == {"p1": None}

    def test_assessment_inherent_snapshot_round_trips_levels(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="minor"),
                ConditionMapping(property="p2", likelihood="rare", consequence="major"),
            ),
        )
        scope = _form([q1, q2], [p1, p2], risks=[risk])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "yes")

        inherent = dict(scope.eval("scope._inherentSnapshot()"))
        r1 = dict(inherent["r1"])
        # Worst-per-dimension: likely / major → high
        assert r1["likelihood"] == "likely"
        assert r1["consequence"] == "major"
        assert r1["level"] == "high"
        assert sorted(r1["firing_conditions"]) == ["p1", "p2"]

    def test_assessment_inherent_firing_conditions_filters_to_truthy(self) -> None:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
                ConditionMapping(property="p2", likelihood="rare", consequence="minor"),
            ),
        )
        scope = _form([q1, q2], [p1, p2], risks=[risk])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")  # condition does not fire

        inherent = dict(scope.eval("scope._inherentSnapshot()"))
        r1 = dict(inherent["r1"])
        assert list(r1["firing_conditions"]) == ["p1"]

    def test_assessment_inherent_no_firing_is_not_applicable(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
            ),
        )
        scope = _form([q], [p], risks=[risk])
        # Question unanswered → property null → no condition fires.

        inherent = dict(scope.eval("scope._inherentSnapshot()"))
        r1 = dict(inherent["r1"])
        assert r1["level"] == "not_applicable"
        assert list(r1["firing_conditions"]) == []


class TestAssessmentClearAssessment:
    """The assessment's clearAssessment wipes assessment state only and
    leaves the loaded answers + details intact (those came from a
    questionnaire JSON, not from the assessor's input)."""

    def _populate(self) -> Scope:
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
            ),
        )
        ctrl = Control(
            id="c1",
            description="",
            property="p1",
            effects=(ControlEffect(risk_id="r1"),),
        )
        detail = Detail(id="d1", description="", properties=("p1",))
        scope = _form([q1, q2], [p1, p2], risks=[risk], controls=[ctrl], details=[detail])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "no")
        scope.set_detail("d1", "field notes")
        scope.set_effectiveness("r1", "partial")
        scope.set_residual("r1", "unlikely", "medium")
        scope.eval("scope.justifications['r1'] = 'looks fine';")
        scope.eval("scope.mandated_controls['r1']['c1'] = true;")
        scope.eval("scope.mandated_comments['r1']['c1'] = 'do this';")
        return scope

    def test_clear_keeps_loaded_answers_and_details(self) -> None:
        scope = self._populate()
        scope.eval("scope.clearAssessment();")
        # Answers + details preserved (they are loaded data, not assessor input).
        assert scope.eval("scope.answers") == {"q1": "yes", "q2": "no"}
        assert scope.eval("scope.details") == {"d1": "field notes"}
        # Assessment state wiped.
        assert scope.eval("scope.control_effectiveness") == {"r1": ""}
        assert scope.eval("scope.residual_likelihood") == {"r1": ""}
        assert scope.eval("scope.residual_consequence") == {"r1": ""}
        assert scope.eval("scope.justifications") == {"r1": ""}
        assert scope.eval("scope.mandated_controls") == {"r1": {"c1": False}}
        assert scope.eval("scope.mandated_comments") == {"r1": {"c1": ""}}

    def test_clear_cancel_keeps_state(self) -> None:
        scope = self._populate()
        scope.eval("confirm = () => false;")
        scope.eval("scope.clearAssessment();")
        assert scope.eval("scope.control_effectiveness") == {"r1": "partial"}
        assert scope.eval("scope.justifications") == {"r1": "looks fine"}
        assert scope.eval("scope.mandated_controls") == {"r1": {"c1": True}}
