"""Integration tests — load the actual YAML form files and verify consistency."""

from __future__ import annotations

import config
from models import all_questions
from parse import (
    load_controls,
    load_details,
    load_properties,
    load_risks,
    load_sections,
    validate_control_properties,
    validate_control_risk_ids,
    validate_detail_properties,
    validate_detail_questions,
    validate_property_dag,
    validate_question_properties,
    validate_risk_properties,
)

_details_path = config.form_dir / "details.yaml"
DETAILS = load_details(_details_path) if _details_path.exists() else []
DETAILS_BY_ID = {d.id: d for d in DETAILS}

SECTIONS = load_sections(config.form_dir / "sections.yaml", DETAILS_BY_ID)
PROPERTIES = load_properties(config.form_dir / "properties.yaml")
RISKS = load_risks(config.form_dir / "risks.yaml")
CONTROLS = load_controls(config.form_dir / "controls.yaml")
QUESTIONS = all_questions(SECTIONS)
QUESTION_IDS = {q.id for q in QUESTIONS}
PROPERTY_IDS = {p.id for p in PROPERTIES}
RISK_IDS = {r.id for r in RISKS}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class TestSections:
    def test_section_count(self):
        assert len(SECTIONS) == 3

    def test_section_ids(self):
        ids = [s.id for s in SECTIONS]
        assert ids == ["personal", "social", "lifestyle"]

    def test_question_ids_unique(self):
        ids = [q.id for q in QUESTIONS]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert len(ids) == len(set(ids)), f"Duplicate question IDs: {dupes}"

    def test_question_types_are_known(self):
        known_types = {"binary", "detail"}
        for q in QUESTIONS:
            assert q.type in known_types, f"Question {q.id!r} has unknown type {q.type!r}"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_property_count(self):
        assert len(PROPERTIES) == 7

    def test_dag_valid(self):
        validate_property_dag(PROPERTIES)  # should not raise

    def test_question_properties_valid(self):
        validate_question_properties(QUESTIONS, PROPERTIES)  # should not raise

    def test_all_question_property_refs_exist(self):
        for q in QUESTIONS:
            for pid in q.properties:
                assert pid in PROPERTY_IDS, (
                    f"Question {q.id!r} references unknown property {pid!r}"
                )


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


class TestRisks:
    def test_risk_count(self):
        assert len(RISKS) == 3

    def test_risk_ids_unique(self):
        ids = [r.id for r in RISKS]
        assert len(ids) == len(set(ids)), f"Duplicate risk IDs: {ids}"

    def test_risk_properties_valid(self):
        validate_risk_properties(RISKS, PROPERTIES)  # should not raise

    def test_all_condition_property_refs_exist(self):
        for risk in RISKS:
            for cond in risk.conditions:
                for pid in cond.properties:
                    assert pid in PROPERTY_IDS, (
                        f"Risk {risk.id!r} references unknown property {pid!r}"
                    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class TestControls:
    def test_control_count(self):
        assert len(CONTROLS) == 4

    def test_control_ids_unique(self):
        ids = [c.id for c in CONTROLS]
        assert len(ids) == len(set(ids)), f"Duplicate control IDs: {ids}"

    def test_control_properties_valid(self):
        validate_control_properties(CONTROLS, PROPERTIES)  # should not raise

    def test_control_risk_ids_valid(self):
        validate_control_risk_ids(CONTROLS, RISKS)  # should not raise

    def test_all_property_refs_exist(self):
        for ctrl in CONTROLS:
            assert ctrl.property in PROPERTY_IDS, (
                f"Control {ctrl.id!r} references unknown property {ctrl.property!r}"
            )

    def test_all_effect_risk_refs_exist(self):
        for ctrl in CONTROLS:
            for effect in ctrl.effects:
                assert effect.risk_id in RISK_IDS, (
                    f"Control {ctrl.id!r} references unknown risk {effect.risk_id!r}"
                )


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


class TestDetails:
    def test_detail_ids_unique(self):
        ids = [d.id for d in DETAILS]
        assert len(ids) == len(set(ids)), f"Duplicate detail IDs: {ids}"

    def test_detail_properties_valid(self):
        validate_detail_properties(DETAILS, PROPERTIES)  # should not raise

    def test_detail_questions_valid(self):
        validate_detail_questions(QUESTIONS, DETAILS)  # should not raise

    def test_all_detail_property_refs_exist(self):
        for detail in DETAILS:
            for pid in detail.properties:
                assert pid in PROPERTY_IDS, (
                    f"Detail {detail.id!r} references unknown property {pid!r}"
                )
