"""Behaviour tests for the JS emitted by `render_app_js()`.

Each test builds a minimal form, compiles the Alpine factory, and asserts on
what the compiled `prop_*` / risk / residual / `ctrl_*` getters *return* as
answers change. The substring tests in `test_render.py` / `test_models.py`
pin the compiler's output shape; these tests pin the runtime semantics.
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
from tests.js_harness import Scope, build_scope


def _form(
    questions: list[BinaryQuestion],
    properties: list[Property],
    risks: list[Risk] | None = None,
    controls: list[Control] | None = None,
    details: list[Detail] | None = None,
    *,
    persisted_state: dict[str, object] | None = None,
) -> Scope:
    sub = SubSection(title="t", description="", questions=tuple(questions))
    sec = Section(id="s1", title="S", description="", subsections=(sub,))
    return build_scope(
        [sec], properties, risks or [], controls, details, persisted_state=persisted_state
    )


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


# ---------------------------------------------------------------------------
# Schema migration — init() fills keys missing from $persist-restored state
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """Pins §1.3's fix: on component init, any ID present in the current build
    but absent from the localStorage-restored object is seeded with its default
    (empty string for most fields, `false` for mandated-control checkboxes)."""

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
        scope = _form([q1, q2], [p1, p2], persisted_state={"_x_answers": {"q1": "yes"}})
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
            persisted_state={"_x_details": {"d1": "prior note"}},
        )
        assert scope.eval("scope.details") == {"d1": "prior note", "d2": ""}

    @pytest.mark.parametrize(
        "persist_key,field_name",
        [
            ("_x_justifications", "justifications"),
            ("_x_control_effectiveness", "control_effectiveness"),
            ("_x_residual_likelihood", "residual_likelihood"),
            ("_x_residual_consequence", "residual_consequence"),
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
            persisted_state={"_x_mandated_controls": {"r1": {}}},
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
            persisted_state={"_x_mandated_controls": {"r1": {"c1": True}}},
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
            persisted_state={"_x_mandated_comments": {"r1": {}}},
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
            persisted_state={"_x_mandated_comments": {"r1": {"c1": "prior note"}}},
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
                "_x_answers": {"q1": "yes", "q2": "no"},
                "_x_control_effectiveness": {"r1": "controlled"},
                "_x_justifications": {"r1": "prior justification"},
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
