"""Integration tests — load the actual YAML form files and verify consistency."""

from __future__ import annotations

import config
from models import all_questions
from parse import (
    load_properties,
    load_sections,
    validate_property_dag,
    validate_question_properties,
)

SECTIONS = load_sections(config.form_dir / "sections.yaml")
PROPERTIES = load_properties(config.form_dir / "properties.yaml")
QUESTIONS = all_questions(SECTIONS)
QUESTION_IDS = {q.id for q in QUESTIONS}
PROPERTY_IDS = {p.id for p in PROPERTIES}


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

    def test_all_questions_are_binary(self):
        for q in QUESTIONS:
            assert q.type == "binary", f"Question {q.id!r} has type {q.type!r}, expected 'binary'"


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
