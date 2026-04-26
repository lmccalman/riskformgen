"""Unit tests for the registry loader.

The loader walks `registry/<slug>/`, validates each system's
questionnaire/assessment JSON shape and the `meta.yaml` metadata, warns
on ids that no longer exist in the form, and returns a list of
`SystemRecord`s sorted newest-first. These tests pin that contract.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import yaml

import config
from models import (
    BinaryQuestion,
    ConditionMapping,
    Control,
    ControlEffect,
    Property,
    Risk,
    Section,
    SubSection,
)
from registry import (
    SystemRecord,
    load_registry,
    worst_residual_level,
)


@pytest.fixture
def form() -> dict[str, list]:
    """Tiny form: one question, two properties, one risk, one control."""
    q = BinaryQuestion(id="q1", text="?", properties=("p1",))
    sub = SubSection(title="t", description="", questions=(q,))
    sec = Section(id="s1", title="S", description="", subsections=(sub,))
    return {
        "sections": [sec],
        "properties": [
            Property(id="p1", description=""),
            Property(id="p2", description=""),
        ],
        "risks": [
            Risk(
                id="r1",
                description="",
                conditions=(
                    ConditionMapping(property="p1", likelihood="likely", consequence="major"),
                ),
            ),
        ],
        "controls": [
            Control(
                id="c1",
                description="ctrl",
                property="p2",
                effects=(ControlEffect(risk_id="r1"),),
            ),
        ],
    }


def _write_questionnaire(
    folder: Path,
    *,
    answers: dict[str, str] | None = None,
    properties: dict[str, bool | None] | None = None,
    version: int = config.QUESTIONNAIRE_VERSION,
    fmt: str = config.QUESTIONNAIRE_FORMAT,
    exported_at: str = "2026-04-26T08:00:00Z",
) -> None:
    payload = {
        "format": fmt,
        "version": version,
        "exported_at": exported_at,
        "question_ids": list((answers or {"q1": "yes"}).keys()),
        "answers": answers or {"q1": "yes"},
        "detail_ids": [],
        "details": {},
        "property_ids": list((properties or {"p1": True, "p2": False}).keys()),
        "properties": properties or {"p1": True, "p2": False},
    }
    (folder / "questionnaire.json").write_text(json.dumps(payload))


def _write_assessment(
    folder: Path,
    *,
    risk_ids: list[str] | None = None,
    inherent: dict[str, dict] | None = None,
    effectiveness: dict[str, str] | None = None,
    res_l: dict[str, str] | None = None,
    res_c: dict[str, str] | None = None,
    version: int = config.ASSESSMENT_VERSION,
    fmt: str = config.ASSESSMENT_FORMAT,
    exported_at: str = "2026-04-26T09:00:00Z",
    mandated_controls: dict[str, dict[str, bool]] | None = None,
) -> None:
    risk_ids = risk_ids or ["r1"]
    payload = {
        "format": fmt,
        "version": version,
        "exported_at": exported_at,
        "risk_ids": risk_ids,
        "property_ids": ["p1", "p2"],
        "properties": {"p1": True, "p2": False},
        "inherent": inherent
        or {
            "r1": {
                "likelihood": "likely",
                "consequence": "major",
                "level": "high",
                "firing_conditions": ["p1"],
            }
        },
        "control_effectiveness": effectiveness or {"r1": "ineffective"},
        "residual_likelihood": res_l or {"r1": ""},
        "residual_consequence": res_c or {"r1": ""},
        "justifications": {"r1": ""},
        "mandated_controls": mandated_controls or {"r1": {"c1": False}},
        "mandated_comments": {"r1": {"c1": ""}},
    }
    (folder / "assessment.json").write_text(json.dumps(payload))


def _write_meta(folder: Path, name: str = "Acme", **extra: object) -> None:
    payload: dict[str, object] = {"name": name, **extra}
    (folder / "meta.yaml").write_text(yaml.safe_dump(payload))


def _make_system(root: Path, slug: str, **kw: object) -> Path:
    folder = root / slug
    folder.mkdir()
    return folder


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestLoadRegistryHappyPath:
    def test_empty_dir_returns_empty_list(self, tmp_path: Path, form: dict) -> None:
        records = load_registry(tmp_path, **form)
        assert records == []

    def test_missing_dir_returns_empty_list(self, tmp_path: Path, form: dict) -> None:
        records = load_registry(tmp_path / "nope", **form)
        assert records == []

    def test_single_system_loads(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder, "Acme Payments", owner="Jane")
        _write_questionnaire(folder)
        _write_assessment(folder)

        records = load_registry(tmp_path, **form)
        assert len(records) == 1
        rec = records[0]
        assert rec.slug == "acme"
        assert rec.meta.name == "Acme Payments"
        assert rec.meta.owner == "Jane"
        assert rec.assessment is not None
        assert rec.exported_at == "2026-04-26T09:00:00Z"

    def test_questionnaire_only_system_is_accepted(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "drafty")
        _write_meta(folder, "Drafty")
        _write_questionnaire(folder)

        records = load_registry(tmp_path, **form)
        assert len(records) == 1
        assert records[0].assessment is None
        # falls back to questionnaire.exported_at when no assessment
        assert records[0].exported_at == "2026-04-26T08:00:00Z"

    def test_records_sorted_newest_first(self, tmp_path: Path, form: dict) -> None:
        a = _make_system(tmp_path, "a-old")
        _write_meta(a, "Old")
        _write_questionnaire(a, exported_at="2026-01-01T00:00:00Z")
        _write_assessment(a, exported_at="2026-01-02T00:00:00Z")

        b = _make_system(tmp_path, "b-new")
        _write_meta(b, "New")
        _write_questionnaire(b, exported_at="2026-04-01T00:00:00Z")
        _write_assessment(b, exported_at="2026-04-25T00:00:00Z")

        records = load_registry(tmp_path, **form)
        assert [r.slug for r in records] == ["b-new", "a-old"]

    def test_hidden_dirs_skipped(self, tmp_path: Path, form: dict) -> None:
        # `.git`, etc. — never picked up as a system folder.
        hidden = _make_system(tmp_path, ".git")
        (hidden / "config").write_text("# git config")
        records = load_registry(tmp_path, **form)
        assert records == []

    def test_files_at_top_level_skipped(self, tmp_path: Path, form: dict) -> None:
        (tmp_path / "README.md").write_text("# notes")
        records = load_registry(tmp_path, **form)
        assert records == []


# ---------------------------------------------------------------------------
# Validation: format / version
# ---------------------------------------------------------------------------


class TestValidationHardFails:
    def test_missing_meta_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder)
        with pytest.raises(ValueError, match=r"Missing.*meta\.yaml"):
            load_registry(tmp_path, **form)

    def test_missing_questionnaire_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        with pytest.raises(ValueError, match=r"Missing.*questionnaire\.json"):
            load_registry(tmp_path, **form)

    def test_meta_missing_name_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        (folder / "meta.yaml").write_text("owner: Jane\n")
        _write_questionnaire(folder)
        with pytest.raises(ValueError, match="'name' is required"):
            load_registry(tmp_path, **form)

    def test_questionnaire_wrong_format_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        _write_questionnaire(folder, fmt="some-other-tool")
        with pytest.raises(ValueError, match="wrong format"):
            load_registry(tmp_path, **form)

    def test_questionnaire_wrong_version_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        _write_questionnaire(folder, version=1)
        with pytest.raises(ValueError, match="incompatible version"):
            load_registry(tmp_path, **form)

    def test_assessment_wrong_version_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        _write_questionnaire(folder)
        _write_assessment(folder, version=2)
        with pytest.raises(ValueError, match="incompatible version"):
            load_registry(tmp_path, **form)

    def test_invalid_slug_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "Capital_Bad")
        _write_meta(folder)
        _write_questionnaire(folder)
        with pytest.raises(ValueError, match="Invalid system slug"):
            load_registry(tmp_path, **form)

    def test_invalid_json_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        (folder / "questionnaire.json").write_text("{not json")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_registry(tmp_path, **form)


# ---------------------------------------------------------------------------
# Validation: unknown ids — warn but do not fail
# ---------------------------------------------------------------------------


class TestUnknownIdsWarn:
    def test_unknown_question_id_emits_warning(
        self, tmp_path: Path, form: dict, caplog: pytest.LogCaptureFixture
    ) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        _write_questionnaire(
            folder,
            answers={"q1": "yes", "q_old_removed": "yes"},
            properties={"p1": True, "p2": False},
        )
        with caplog.at_level(logging.WARNING):
            records = load_registry(tmp_path, **form)
        assert len(records) == 1
        assert any("q_old_removed" in r.message for r in caplog.records)

    def test_unknown_risk_id_emits_warning(
        self, tmp_path: Path, form: dict, caplog: pytest.LogCaptureFixture
    ) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_meta(folder)
        _write_questionnaire(folder)
        _write_assessment(
            folder,
            risk_ids=["r1", "r_old_removed"],
            inherent={
                "r1": {
                    "likelihood": "likely",
                    "consequence": "major",
                    "level": "high",
                    "firing_conditions": ["p1"],
                },
                "r_old_removed": {
                    "likelihood": "rare",
                    "consequence": "minor",
                    "level": "low",
                    "firing_conditions": [],
                },
            },
            effectiveness={"r1": "ineffective", "r_old_removed": "ineffective"},
            res_l={"r1": "", "r_old_removed": ""},
            res_c={"r1": "", "r_old_removed": ""},
        )
        with caplog.at_level(logging.WARNING):
            records = load_registry(tmp_path, **form)
        assert len(records) == 1
        assert any("r_old_removed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# worst_residual_level
# ---------------------------------------------------------------------------


def _record(
    *,
    inherent: dict[str, dict],
    effectiveness: dict[str, str],
    res_l: dict[str, str] | None = None,
    res_c: dict[str, str] | None = None,
) -> SystemRecord:
    return SystemRecord(
        slug="x",
        meta=__import__("registry").SystemMeta(name="X"),
        questionnaire={"properties": {}},
        assessment={
            "inherent": inherent,
            "control_effectiveness": effectiveness,
            "residual_likelihood": res_l or {},
            "residual_consequence": res_c or {},
        },
    )


class TestWorstResidualLevel:
    def test_no_assessment_is_not_applicable(self) -> None:
        rec = SystemRecord(
            slug="x",
            meta=__import__("registry").SystemMeta(name="X"),
            questionnaire={},
            assessment=None,
        )
        assert worst_residual_level(rec, config.RISK_LEVELS) == "not_applicable"

    def test_picks_highest_severity_across_risks(self) -> None:
        rec = _record(
            inherent={
                "r1": {"likelihood": "rare", "consequence": "minor", "level": "low"},
                "r2": {"likelihood": "likely", "consequence": "major", "level": "high"},
            },
            effectiveness={"r1": "ineffective", "r2": "ineffective"},
        )
        assert worst_residual_level(rec, config.RISK_LEVELS) == "high"

    def test_controlled_overrides_inherent_high(self) -> None:
        rec = _record(
            inherent={
                "r1": {"likelihood": "likely", "consequence": "major", "level": "high"},
            },
            effectiveness={"r1": "controlled"},
        )
        assert worst_residual_level(rec, config.RISK_LEVELS) == "controlled"

    def test_partial_uses_residual_matrix(self) -> None:
        rec = _record(
            inherent={
                "r1": {"likelihood": "likely", "consequence": "major", "level": "high"},
            },
            effectiveness={"r1": "partial"},
            res_l={"r1": "rare"},
            res_c={"r1": "minor"},
        )
        # rare/minor → low per RISK_MATRIX
        assert worst_residual_level(rec, config.RISK_LEVELS) == "low"

    def test_partial_with_missing_residual_falls_back(self) -> None:
        rec = _record(
            inherent={
                "r1": {"likelihood": "likely", "consequence": "major", "level": "high"},
            },
            effectiveness={"r1": "partial"},
            res_l={"r1": ""},
            res_c={"r1": ""},
        )
        assert worst_residual_level(rec, config.RISK_LEVELS) == "high"

    def test_not_applicable_inherent_does_not_lift_floor(self) -> None:
        rec = _record(
            inherent={
                "r1": {
                    "likelihood": None,
                    "consequence": None,
                    "level": "not_applicable",
                },
            },
            effectiveness={"r1": "ineffective"},
        )
        assert worst_residual_level(rec, config.RISK_LEVELS) == "not_applicable"
