"""Integration tests — load the actual YAML form files and verify consistency."""

from __future__ import annotations

import pytest

import config
from models import ChoiceMapRule, all_questions
from parse import load_controls, load_risks, load_sections

SECTIONS = load_sections(config.form_dir / "sections.yaml")
RISKS = load_risks(config.form_dir / "risks.yaml")
CONTROLS = load_controls(config.form_dir / "controls.yaml")
QUESTIONS = all_questions(SECTIONS)
QUESTION_IDS = {q.id for q in QUESTIONS}
RISK_IDS = {r.id for r in RISKS}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class TestSections:
    def test_section_count(self):
        assert len(SECTIONS) == 3

    def test_section_ids(self):
        ids = [s.id for s in SECTIONS]
        assert ids == ["personal", "activities", "environment"]

    def test_question_ids_unique(self):
        ids = [q.id for q in QUESTIONS]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert len(ids) == len(set(ids)), f"Duplicate question IDs: {dupes}"


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


class TestRisks:
    def test_risk_count(self):
        assert len(RISKS) == 4

    def test_risk_ids(self):
        ids = [r.id for r in RISKS]
        assert ids == ["sedentary_risk", "seasonal_mood_risk", "burnout_risk", "isolation_risk"]

    def test_default_likelihood_valid(self):
        for risk in RISKS:
            assert risk.default_likelihood in config.LIKELIHOODS, (
                f"Risk {risk.id}: invalid default_likelihood {risk.default_likelihood!r}"
            )

    def test_default_consequence_valid(self):
        for risk in RISKS:
            assert risk.default_consequence in config.CONSEQUENCES, (
                f"Risk {risk.id}: invalid default_consequence {risk.default_consequence!r}"
            )

    @pytest.mark.parametrize("risk", RISKS, ids=[r.id for r in RISKS])
    def test_rule_question_ids_exist(self, risk):
        """Every question_id referenced by a risk rule must exist in the sections."""
        for rule in risk.rules:
            for qid in rule.referenced_question_ids():
                assert qid in QUESTION_IDS, (
                    f"Risk {risk.id}: rule references unknown question {qid!r}"
                )

    @pytest.mark.parametrize("risk", RISKS, ids=[r.id for r in RISKS])
    def test_rule_scale_values_valid(self, risk):
        """Likelihood/consequence values in rules must be valid scale entries."""
        for rule in risk.rules:
            if isinstance(rule, ChoiceMapRule):
                for answer, dims in rule.mapping.items():
                    lk = dims.get("likelihood")
                    cq = dims.get("consequence")
                    if lk is not None:
                        assert lk in config.LIKELIHOODS, (
                            f"Risk {risk.id}, choice_map answer {answer!r}: "
                            f"invalid likelihood {lk!r}"
                        )
                    if cq is not None:
                        assert cq in config.CONSEQUENCES, (
                            f"Risk {risk.id}, choice_map answer {answer!r}: "
                            f"invalid consequence {cq!r}"
                        )
            else:
                if rule.likelihood is not None:
                    assert rule.likelihood in config.LIKELIHOODS, (
                        f"Risk {risk.id}: invalid likelihood {rule.likelihood!r}"
                    )
                if rule.consequence is not None:
                    assert rule.consequence in config.CONSEQUENCES, (
                        f"Risk {risk.id}: invalid consequence {rule.consequence!r}"
                    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class TestControls:
    def test_control_count(self):
        assert len(CONTROLS) == 3

    def test_control_ids(self):
        ids = [c.id for c in CONTROLS]
        assert ids == ["outdoor_access", "active_hobbies", "group_activities"]

    @pytest.mark.parametrize("control", CONTROLS, ids=[c.id for c in CONTROLS])
    def test_question_id_exists(self, control):
        """The question referenced by a control must exist in the sections."""
        assert control.question_id in QUESTION_IDS, (
            f"Control {control.id}: references unknown question {control.question_id!r}"
        )

    @pytest.mark.parametrize("control", CONTROLS, ids=[c.id for c in CONTROLS])
    def test_effect_risk_ids_exist(self, control):
        """Every risk_id in a control's effects must exist in the risks file."""
        for effect in control.effects:
            assert effect.risk_id in RISK_IDS, (
                f"Control {control.id}: effect references unknown risk {effect.risk_id!r}"
            )
