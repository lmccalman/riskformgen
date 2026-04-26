"""Integration tests — load the actual YAML form files and verify consistency."""

from __future__ import annotations

import pytest

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


@pytest.fixture(scope="module")
def details():
    path = config.form_dir / "details.yaml"
    return load_details(path) if path.exists() else []


@pytest.fixture(scope="module")
def details_by_id(details):
    return {d.id: d for d in details}


@pytest.fixture(scope="module")
def sections(details_by_id):
    return load_sections(config.form_dir / "sections.yaml", details_by_id)


@pytest.fixture(scope="module")
def properties():
    return load_properties(config.form_dir / "properties.yaml")


@pytest.fixture(scope="module")
def risks():
    return load_risks(config.form_dir / "risks.yaml")


@pytest.fixture(scope="module")
def controls():
    return load_controls(config.form_dir / "controls.yaml")


@pytest.fixture(scope="module")
def questions(sections):
    return all_questions(sections)


@pytest.fixture(scope="module")
def property_ids(properties):
    return {p.id for p in properties}


@pytest.fixture(scope="module")
def risk_ids(risks):
    return {r.id for r in risks}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class TestSections:
    def test_section_ids_unique(self, sections):
        ids = [s.id for s in sections]
        assert len(ids) == len(set(ids)), f"Duplicate section IDs: {ids}"

    def test_question_ids_unique(self, questions):
        ids = [q.id for q in questions]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert len(ids) == len(set(ids)), f"Duplicate question IDs: {dupes}"

    def test_question_types_are_known(self, questions):
        known_types = {"binary", "detail"}
        for q in questions:
            assert q.type in known_types, f"Question {q.id!r} has unknown type {q.type!r}"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_dag_valid(self, properties):
        validate_property_dag(properties)  # should not raise

    def test_question_properties_valid(self, questions, properties):
        validate_question_properties(questions, properties)  # should not raise

    def test_all_question_property_refs_exist(self, questions, property_ids):
        for q in questions:
            for pid in q.properties:
                assert pid in property_ids, (
                    f"Question {q.id!r} references unknown property {pid!r}"
                )


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


class TestRisks:
    def test_risk_ids_unique(self, risks):
        ids = [r.id for r in risks]
        assert len(ids) == len(set(ids)), f"Duplicate risk IDs: {ids}"

    def test_risk_properties_valid(self, risks, properties):
        validate_risk_properties(risks, properties)  # should not raise

    def test_all_condition_property_refs_exist(self, risks, property_ids):
        for risk in risks:
            for cond in risk.conditions:
                assert cond.property in property_ids, (
                    f"Risk {risk.id!r} references unknown property {cond.property!r}"
                )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class TestControls:
    def test_control_ids_unique(self, controls):
        ids = [c.id for c in controls]
        assert len(ids) == len(set(ids)), f"Duplicate control IDs: {ids}"

    def test_control_properties_valid(self, controls, properties):
        validate_control_properties(controls, properties)  # should not raise

    def test_control_risk_ids_valid(self, controls, risks):
        validate_control_risk_ids(controls, risks)  # should not raise

    def test_all_property_refs_exist(self, controls, property_ids):
        for ctrl in controls:
            assert ctrl.property in property_ids, (
                f"Control {ctrl.id!r} references unknown property {ctrl.property!r}"
            )

    def test_all_effect_risk_refs_exist(self, controls, risk_ids):
        for ctrl in controls:
            for effect in ctrl.effects:
                assert effect.risk_id in risk_ids, (
                    f"Control {ctrl.id!r} references unknown risk {effect.risk_id!r}"
                )


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


class TestDetails:
    def test_detail_ids_unique(self, details):
        ids = [d.id for d in details]
        assert len(ids) == len(set(ids)), f"Duplicate detail IDs: {ids}"

    def test_detail_properties_valid(self, details, properties):
        validate_detail_properties(details, properties)  # should not raise

    def test_detail_questions_valid(self, questions, details):
        validate_detail_questions(questions, details)  # should not raise

    def test_all_detail_property_refs_exist(self, details, property_ids):
        for detail in details:
            for pid in detail.properties:
                assert pid in property_ids, (
                    f"Detail {detail.id!r} references unknown property {pid!r}"
                )
