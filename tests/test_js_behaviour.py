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

import json
from pathlib import Path
from typing import Any

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


class TestAggregateResidualRisk:
    """The assessor's overall residual call: default-from-worst + override semantics."""

    @pytest.fixture
    def scope(self) -> Scope:
        # Two firing risks: r1 -> high (likely/major), r2 -> low (rare/minor).
        q1 = BinaryQuestion(id="q1", text="", properties=("p1",))
        q2 = BinaryQuestion(id="q2", text="", properties=("p2",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        r1 = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
            ),
        )
        r2 = Risk(
            id="r2",
            description="",
            conditions=(ConditionMapping(property="p2", likelihood="rare", consequence="minor"),),
        )
        scope = _form([q1, q2], [p1, p2], risks=[r1, r2])
        scope.set_answer("q1", "yes")
        scope.set_answer("q2", "yes")
        return scope

    def test_default_is_worst_per_risk_residual(self, scope: Scope) -> None:
        # r1 → high, r2 → low; worst is high.
        assert scope.eval("scope.aggregate_residual_level_default") == "high"

    def test_default_collapses_to_controlled_when_all_risks_controlled(self, scope: Scope) -> None:
        scope.set_effectiveness("r1", "controlled")
        scope.set_effectiveness("r2", "controlled")
        # RISK_LEVELS = ('not_applicable', 'controlled', 'low', 'medium', 'high'),
        # so both risks are 'controlled'; worst of {controlled, controlled} is 'controlled'.
        assert scope.eval("scope.aggregate_residual_level_default") == "controlled"

    def test_default_picks_higher_when_one_risk_uncontrolled(self, scope: Scope) -> None:
        # r1 stays inherent high; r2 collapsed to controlled.
        scope.set_effectiveness("r2", "controlled")
        assert scope.eval("scope.aggregate_residual_level_default") == "high"

    def test_default_is_not_applicable_when_no_risk_fires(self) -> None:
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
        # q1 unanswered -> r1 not_applicable
        assert scope.eval("scope.aggregate_residual_level_default") == "not_applicable"

    def test_override_persists_independently_of_default(self, scope: Scope) -> None:
        # Default is 'high'; override to 'medium' — getter should still report
        # the worst, leaving the override decoupled from it.
        scope.eval("scope.aggregate_residual_level = 'medium';")
        assert scope.eval("scope.aggregate_residual_level") == "medium"
        assert scope.eval("scope.aggregate_residual_level_default") == "high"

    def test_default_excludes_not_applicable_from_worst(self) -> None:
        # Mix one firing risk (medium) and one not_applicable risk; the
        # aggregate default must skip 'not_applicable' rather than treating
        # it as the worst.
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p1 = Property(id="p1", description="")
        p2 = Property(id="p2", description="")
        r1 = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="possible", consequence="medium"),
            ),
        )
        r2 = Risk(
            id="r2",
            description="",
            conditions=(ConditionMapping(property="p2", likelihood="rare", consequence="minor"),),
        )
        scope = _form([q], [p1, p2], risks=[r1, r2])
        scope.set_answer("q1", "yes")
        # r2 has no question answering p2 → not_applicable
        assert scope.eval("scope.aggregate_residual_level_default") == "medium"


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


class TestJsDiffParity:
    """The JS `_diffPair` and Python `diff.diff_pair` must produce identical
    output for the same inputs. The same fixture corpus that drives the
    Python tests is fed through a live assessment scope here — a regression
    in either implementation breaks parity and fails this test.
    """

    @staticmethod
    def _scope() -> Scope:
        # `_diffPair` reads only its arguments; the form structure on the
        # surrounding scope is irrelevant to the diff.
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        return _form([q], [p])

    @staticmethod
    def _fixtures_dir() -> Path:
        return Path(__file__).parent / "fixtures" / "diff"

    @pytest.mark.parametrize(
        "scenario",
        sorted(
            p.name for p in (Path(__file__).parent / "fixtures" / "diff").iterdir() if p.is_dir()
        ),
    )
    def test_js_diff_matches_python_expected(self, scenario: str) -> None:
        folder = self._fixtures_dir() / scenario
        prev_q = self._maybe_load(folder / "prev_q.json")
        prev_a = self._maybe_load(folder / "prev_a.json")
        cur_q = json.loads((folder / "cur_q.json").read_text())
        cur_a = self._maybe_load(folder / "cur_a.json")
        expected = json.loads((folder / "expected.json").read_text())

        scope = self._scope()
        result = scope.eval(
            "JSON.stringify(scope._diffPair("
            f"{json.dumps(prev_q)}, {json.dumps(prev_a)}, "
            f"{json.dumps(cur_q)}, {json.dumps(cur_a)}"
            "))"
        )
        assert json.loads(result) == expected

    @staticmethod
    def _maybe_load(path: Path) -> Any:
        if not path.exists():
            return None
        return json.loads(path.read_text())


class TestAssessmentPriorLoad:
    """The "Load prior version" affordance populates the prior_* slots and
    flips `diffMode` on. Loading the prior assessment also carries its
    residual / justification / mandate state forward into live state, so
    the assessor only edits what changed.
    """

    def _scope_with_assessment(self) -> Scope:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
            ),
        )
        c = Control(id="c1", description="", property="p1", effects=(ControlEffect(risk_id="r1"),))
        return _form([q], [p], risks=[r], controls=[c])

    def test_diff_mode_off_by_default(self) -> None:
        scope = self._scope_with_assessment()
        assert scope.eval("scope.diffMode") is False
        assert scope.eval("scope.change_summary") is None

    def test_setting_prior_questionnaire_flips_diff_mode_on(self) -> None:
        scope = self._scope_with_assessment()
        scope.eval("scope.prior_questionnaire = {question_ids: ['q1'], answers: {q1: 'no'}};")
        assert scope.eval("scope.diffMode") is True
        # change_summary now resolves to a populated diff (q1 changed yes/empty → live).
        result = scope.eval("scope.change_summary")
        assert result is not None
        assert "answer_changes" in result

    def test_carry_forward_prior_assessment_populates_live_state(self) -> None:
        scope = self._scope_with_assessment()
        prior_assessment = {
            "risk_ids": ["r1"],
            "control_effectiveness": {"r1": "partial"},
            "residual_likelihood": {"r1": "possible"},
            "residual_consequence": {"r1": "medium"},
            "justifications": {"r1": "Prior call."},
            "mandated_controls": {"r1": {"c1": True}},
            "mandated_comments": {"r1": {"c1": "Implement before EOY."}},
            "aggregate_residual_level": "medium",
            "aggregate_residual_justification": "Prior aggregate.",
        }
        scope.eval(f"scope._carryForwardPriorAssessment({json.dumps(prior_assessment)});")
        assert scope.eval("scope.control_effectiveness") == {"r1": "partial"}
        assert scope.eval("scope.residual_likelihood") == {"r1": "possible"}
        assert scope.eval("scope.residual_consequence") == {"r1": "medium"}
        assert scope.eval("scope.justifications") == {"r1": "Prior call."}
        assert scope.eval("scope.mandated_controls") == {"r1": {"c1": True}}
        assert scope.eval("scope.mandated_comments") == {"r1": {"c1": "Implement before EOY."}}
        assert scope.eval("scope.aggregate_residual_level") == "medium"
        assert scope.eval("scope.aggregate_residual_justification") == "Prior aggregate."

    def test_risk_inherent_changed_detects_level_flip(self) -> None:
        scope = self._scope_with_assessment()
        scope.eval(
            "scope.prior_assessment = {"
            " inherent: {r1: {likelihood: null, consequence: null, "
            "level: 'not_applicable', firing_conditions: []}}"
            "};"
        )
        # Live: q1 unanswered → r1 not_applicable. No change.
        assert scope.eval("scope.riskInherentChanged('r1')") is False
        # Flip live to applicable → change detected.
        scope.set_answer("q1", "yes")
        assert scope.eval("scope.riskInherentChanged('r1')") is True

    def test_prior_residual_returns_prior_values_when_loaded(self) -> None:
        scope = self._scope_with_assessment()
        scope.eval(
            "scope.prior_assessment = {"
            " control_effectiveness: {r1: 'partial'},"
            " residual_likelihood: {r1: 'unlikely'},"
            " residual_consequence: {r1: 'minor'},"
            " justifications: {r1: 'Prior reasoning.'}"
            "};"
        )
        result = scope.eval("scope.priorResidual('r1')")
        assert dict(result) == {
            "effectiveness": "partial",
            "likelihood": "unlikely",
            "consequence": "minor",
            "justification": "Prior reasoning.",
        }

    def test_prior_residual_returns_null_when_no_prior(self) -> None:
        scope = self._scope_with_assessment()
        assert scope.eval("scope.priorResidual('r1')") is None

    def test_clear_prior_resets_slots(self) -> None:
        scope = self._scope_with_assessment()
        scope.eval(
            "scope.prior_questionnaire = {question_ids: ['q1']};"
            "scope.prior_assessment = {risk_ids: ['r1']};"
            "scope.prior_assessment_at = '2026-01-01T00:00:00Z';"
        )
        scope.eval("scope.clearPrior();")
        assert scope.eval("scope.prior_questionnaire") is None
        assert scope.eval("scope.prior_assessment") is None
        assert scope.eval("scope.prior_assessment_at") == ""
        assert scope.eval("scope.diffMode") is False

    def test_clear_prior_cancel_keeps_state(self) -> None:
        scope = self._scope_with_assessment()
        scope.eval("scope.prior_questionnaire = {question_ids: ['q1']};")
        scope.eval("confirm = () => false;")
        scope.eval("scope.clearPrior();")
        assert scope.eval("scope.prior_questionnaire") is not None


class TestAssessmentDiffPresentationHelpers:
    """Presentation-layer helpers used by the diff-summary banner and the
    diff-aware Loaded Answers tab. Each derives from `change_summary` and
    the prior_* slots; together they let the templates render per-row /
    per-risk diff state without re-walking the change arrays.
    """

    def _scope_with_one_risk_one_control(self) -> Scope:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
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
        return _form([q], [p], risks=[risk], controls=[ctrl])

    def _set_prior(self, scope: Scope, prior_q: dict[str, Any], prior_a: dict[str, Any]) -> None:
        scope.eval(f"scope.prior_questionnaire = {json.dumps(prior_q)};")
        scope.eval(f"scope.prior_assessment = {json.dumps(prior_a)};")

    def test_no_prior_returns_inert_helpers(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        assert scope.eval("scope.diffMode") is False
        assert scope.eval("scope.riskChanged('r1')") is False
        assert list(scope.eval("scope.riskChangeKinds('r1')")) == []
        assert list(scope.eval("scope.changed_risk_ids")) == []
        assert dict(scope.eval("scope.answer_changes_by_id")) == {}
        assert dict(scope.eval("scope.detail_changes_by_id")) == {}
        assert dict(scope.eval("scope.residual_changes_by_id")) == {}
        assert dict(scope.eval("scope.mandate_changes_by_risk")) == {}
        counts = dict(scope.eval("scope.change_counts"))
        assert counts == {
            "answers": 0,
            "details": 0,
            "risks": 0,
            "residual": 0,
            "mandates": 0,
            "aggregate": 0,
        }

    def test_inherent_only_change_marks_risk_changed_with_inherent_kind(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        # Live: q1 = yes → r1 inherent = high. Prior: q1 = no → r1 inherent = N/A.
        scope.set_answer("q1", "yes")
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "no"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": False},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": None,
                        "consequence": None,
                        "level": "not_applicable",
                        "firing_conditions": [],
                    }
                },
                "control_effectiveness": {"r1": ""},
                "residual_likelihood": {"r1": ""},
                "residual_consequence": {"r1": ""},
                "justifications": {"r1": ""},
                "mandated_controls": {"r1": {"c1": False}},
                "mandated_comments": {"r1": {"c1": ""}},
            },
        )
        assert scope.eval("scope.riskChanged('r1')") is True
        assert list(scope.eval("scope.riskChangeKinds('r1')")) == ["inherent"]
        assert list(scope.eval("scope.changed_risk_ids")) == ["r1"]

    def test_residual_only_change_marks_risk_changed_with_residual_kind(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        # Same answers either side → inherent unchanged.
        scope.set_answer("q1", "yes")
        scope.set_effectiveness("r1", "controlled")
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "yes"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": True},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": "likely",
                        "consequence": "major",
                        "level": "high",
                        "firing_conditions": ["p1"],
                    }
                },
                # Prior was 'partial'; live is 'controlled' → residual changed.
                "control_effectiveness": {"r1": "partial"},
                "residual_likelihood": {"r1": "unlikely"},
                "residual_consequence": {"r1": "minor"},
                "justifications": {"r1": "prior call"},
                "mandated_controls": {"r1": {"c1": False}},
                "mandated_comments": {"r1": {"c1": ""}},
            },
        )
        assert scope.eval("scope.riskChanged('r1')") is True
        assert list(scope.eval("scope.riskChangeKinds('r1')")) == ["residual"]

    def test_mandate_only_change_marks_risk_changed_with_mandates_kind(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        scope.set_answer("q1", "yes")
        scope.eval("scope.mandated_controls['r1']['c1'] = true;")
        scope.eval("scope.mandated_comments['r1']['c1'] = 'do this';")
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "yes"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": True},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": "likely",
                        "consequence": "major",
                        "level": "high",
                        "firing_conditions": ["p1"],
                    }
                },
                "control_effectiveness": {"r1": ""},
                "residual_likelihood": {"r1": ""},
                "residual_consequence": {"r1": ""},
                "justifications": {"r1": ""},
                # Prior had this mandate flag off and no comment.
                "mandated_controls": {"r1": {"c1": False}},
                "mandated_comments": {"r1": {"c1": ""}},
            },
        )
        assert scope.eval("scope.riskChanged('r1')") is True
        assert list(scope.eval("scope.riskChangeKinds('r1')")) == ["mandates"]

    def test_combined_changes_lists_all_kinds_in_canonical_order(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        # Live: yes → inherent high; mandate flagged on; effectiveness 'controlled'.
        scope.set_answer("q1", "yes")
        scope.set_effectiveness("r1", "controlled")
        scope.eval("scope.mandated_controls['r1']['c1'] = true;")
        # Prior: differs on inherent (no), residual (partial), and mandate (off).
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "no"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": False},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": None,
                        "consequence": None,
                        "level": "not_applicable",
                        "firing_conditions": [],
                    }
                },
                "control_effectiveness": {"r1": "partial"},
                "residual_likelihood": {"r1": "unlikely"},
                "residual_consequence": {"r1": "minor"},
                "justifications": {"r1": ""},
                "mandated_controls": {"r1": {"c1": False}},
                "mandated_comments": {"r1": {"c1": ""}},
            },
        )
        assert list(scope.eval("scope.riskChangeKinds('r1')")) == [
            "inherent",
            "residual",
            "mandates",
        ]

    def test_unchanged_risk_is_not_in_changed_list(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        scope.set_answer("q1", "yes")
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "yes"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": True},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": "likely",
                        "consequence": "major",
                        "level": "high",
                        "firing_conditions": ["p1"],
                    }
                },
                "control_effectiveness": {"r1": ""},
                "residual_likelihood": {"r1": ""},
                "residual_consequence": {"r1": ""},
                "justifications": {"r1": ""},
                "mandated_controls": {"r1": {"c1": False}},
                "mandated_comments": {"r1": {"c1": ""}},
            },
        )
        assert scope.eval("scope.riskChanged('r1')") is False
        assert list(scope.eval("scope.changed_risk_ids")) == []

    def test_answer_changes_by_id_keys_match_summary(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        scope.set_answer("q1", "yes")
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "no"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": False},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": None,
                        "consequence": None,
                        "level": "not_applicable",
                        "firing_conditions": [],
                    }
                },
            },
        )
        by_id = dict(scope.eval("scope.answer_changes_by_id"))
        assert set(by_id) == {"q1"}
        assert dict(by_id["q1"]) == {"id": "q1", "before": "no", "after": "yes"}

    def test_detail_changes_by_id_keys_match_summary(self) -> None:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        d = Detail(id="d1", description="", properties=("p1",))
        scope = _form([q], [p], details=[d])
        scope.set_detail("d1", "current note")
        scope.eval(
            "scope.prior_questionnaire = "
            + json.dumps(
                {
                    "question_ids": ["q1"],
                    "answers": {"q1": ""},
                    "detail_ids": ["d1"],
                    "details": {"d1": "prior note"},
                    "property_ids": ["p1"],
                    "properties": {"p1": None},
                }
            )
            + ";"
        )
        by_id = dict(scope.eval("scope.detail_changes_by_id"))
        assert set(by_id) == {"d1"}
        assert dict(by_id["d1"]) == {
            "id": "d1",
            "before": "prior note",
            "after": "current note",
        }

    def test_change_counts_reflect_each_dimension(self) -> None:
        scope = self._scope_with_one_risk_one_control()
        scope.set_answer("q1", "yes")
        scope.set_effectiveness("r1", "controlled")
        self._set_prior(
            scope,
            {
                "question_ids": ["q1"],
                "answers": {"q1": "no"},
                "detail_ids": [],
                "details": {},
                "property_ids": ["p1"],
                "properties": {"p1": False},
            },
            {
                "risk_ids": ["r1"],
                "inherent": {
                    "r1": {
                        "likelihood": None,
                        "consequence": None,
                        "level": "not_applicable",
                        "firing_conditions": [],
                    }
                },
                "control_effectiveness": {"r1": "partial"},
                "residual_likelihood": {"r1": "unlikely"},
                "residual_consequence": {"r1": "minor"},
                "justifications": {"r1": ""},
                "mandated_controls": {"r1": {"c1": False}},
                "mandated_comments": {"r1": {"c1": ""}},
                "aggregate_residual_level": "medium",
                "aggregate_residual_justification": "prior",
            },
        )
        counts = dict(scope.eval("scope.change_counts"))
        assert counts["answers"] == 1
        assert counts["details"] == 0
        assert counts["risks"] == 1
        assert counts["residual"] == 1
        assert counts["mandates"] == 0
        assert counts["aggregate"] == 1


class TestPriorQuestionnaireOnlyDiff:
    """When the assessor loads a prior questionnaire but no prior assessment,
    inherent-risk diffs should still be detected — the prior inherent is
    synthesised from the prior questionnaire's `properties` snapshot using
    the current form's risk rules.
    """

    def _scope(self) -> Scope:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        risk = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
            ),
        )
        return _form([q], [p], risks=[risk])

    def test_changed_property_drives_riskChanged_without_prior_assessment(self) -> None:
        scope = self._scope()
        # Live answer fires the risk; prior questionnaire shows the property
        # was false on the prior side. No prior assessment loaded.
        scope.set_answer("q1", "yes")
        scope.eval(
            "scope.prior_questionnaire = "
            + json.dumps(
                {
                    "question_ids": ["q1"],
                    "answers": {"q1": "no"},
                    "detail_ids": [],
                    "details": {},
                    "property_ids": ["p1"],
                    "properties": {"p1": False},
                }
            )
            + ";"
        )
        assert scope.eval("scope.diffMode") is True
        assert scope.eval("scope.riskInherentChanged('r1')") is True
        assert scope.eval("scope.riskChanged('r1')") is True
        assert dict(scope.eval("scope.change_counts"))["risks"] == 1

    def test_clearPrior_resets_show_only_changed_toggles(self) -> None:
        scope = self._scope()
        scope.eval("scope.prior_questionnaire = {question_ids: ['q1']};")
        scope.eval("scope.show_only_changed_risks = true;")
        scope.eval("scope.show_only_changed_answers = true;")
        # The clearPrior() guarded confirm() defaults to true in the harness.
        scope.eval("scope.clearPrior();")
        assert scope.eval("scope.show_only_changed_risks") is False
        assert scope.eval("scope.show_only_changed_answers") is False


class TestAssessmentExportLineage:
    """The assessment export carries pointers to the questionnaire it was
    made against and (optionally) the prior assessment it supersedes. The
    registry uses these to chain history without inventing a new ID
    scheme. Pins:

    1. `questionnaire_exported_at` is always emitted; it tracks
       `loaded_questionnaire_at`, which is set when `importAnswers` runs.
    2. `prior_assessment_exported_at` is omitted unless `prior_assessment_at`
       has been set.
    """

    def _scope(self) -> Scope:
        q = BinaryQuestion(id="q1", text="", properties=("p1",))
        p = Property(id="p1", description="")
        r = Risk(
            id="r1",
            description="",
            conditions=(
                ConditionMapping(property="p1", likelihood="likely", consequence="major"),
            ),
        )
        return _form([q], [p], risks=[r])

    def _capture_export(self, scope: Scope) -> dict[str, object]:
        """Stub the download path so exportAssessment hands us the payload."""
        scope.eval(
            "var __captured = null;"
            "scope._downloadJson = (data, _name) => { __captured = data; };"
            "scope.exportAssessment();"
        )
        return dict(scope.eval("__captured"))

    def test_questionnaire_exported_at_defaults_to_empty(self) -> None:
        scope = self._scope()
        payload = self._capture_export(scope)
        assert payload["questionnaire_exported_at"] == ""
        assert "prior_assessment_exported_at" not in payload

    def test_loaded_questionnaire_at_round_trips_to_export(self) -> None:
        scope = self._scope()
        scope.eval("scope.loaded_questionnaire_at = '2026-01-15T10:00:00Z';")
        payload = self._capture_export(scope)
        assert payload["questionnaire_exported_at"] == "2026-01-15T10:00:00Z"

    def test_prior_assessment_at_emits_pointer_field(self) -> None:
        scope = self._scope()
        scope.eval(
            "scope.loaded_questionnaire_at = '2026-04-01T10:00:00Z';"
            "scope.prior_assessment_at = '2026-01-15T11:00:00Z';"
        )
        payload = self._capture_export(scope)
        assert payload["questionnaire_exported_at"] == "2026-04-01T10:00:00Z"
        assert payload["prior_assessment_exported_at"] == "2026-01-15T11:00:00Z"
