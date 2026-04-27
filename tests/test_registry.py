"""Unit tests for the registry loader.

The loader walks `registry/<slug>/`, validates each system's
questionnaire/assessment JSON shape, warns on ids that no longer exist
in the form, and returns a list of `SystemRecord`s sorted newest-first.
The display name and owner come from the questionnaire JSON's
`system_name` / `system_owner` fields. These tests pin that contract.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

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
    aggregate_residual_level,
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
    system_name: str = "Acme",
    system_owner: str = "Jane",
) -> None:
    payload = {
        "format": fmt,
        "version": version,
        "exported_at": exported_at,
        "system_name": system_name,
        "system_owner": system_owner,
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
        _write_questionnaire(folder, system_name="Acme Payments", system_owner="Jane")
        _write_assessment(folder)

        records = load_registry(tmp_path, **form)
        assert len(records) == 1
        rec = records[0]
        assert rec.slug == "acme"
        assert rec.system_name == "Acme Payments"
        assert rec.system_owner == "Jane"
        assert rec.assessment is not None
        assert rec.exported_at == "2026-04-26T09:00:00Z"

    def test_questionnaire_only_system_is_accepted(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "drafty")
        _write_questionnaire(folder, system_name="Drafty")

        records = load_registry(tmp_path, **form)
        assert len(records) == 1
        assert records[0].assessment is None
        # falls back to questionnaire.exported_at when no assessment
        assert records[0].exported_at == "2026-04-26T08:00:00Z"

    def test_records_sorted_newest_first(self, tmp_path: Path, form: dict) -> None:
        a = _make_system(tmp_path, "a-old")
        _write_questionnaire(a, system_name="Old", exported_at="2026-01-01T00:00:00Z")
        _write_assessment(a, exported_at="2026-01-02T00:00:00Z")

        b = _make_system(tmp_path, "b-new")
        _write_questionnaire(b, system_name="New", exported_at="2026-04-01T00:00:00Z")
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
    def test_missing_questionnaire_fails(self, tmp_path: Path, form: dict) -> None:
        _make_system(tmp_path, "acme")
        with pytest.raises(ValueError, match=r"Missing.*questionnaire\.json"):
            load_registry(tmp_path, **form)

    def test_questionnaire_wrong_format_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder, fmt="some-other-tool")
        with pytest.raises(ValueError, match="wrong format"):
            load_registry(tmp_path, **form)

    def test_questionnaire_wrong_version_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder, version=1)
        with pytest.raises(ValueError, match="incompatible version"):
            load_registry(tmp_path, **form)

    def test_assessment_wrong_version_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder)
        _write_assessment(folder, version=2)
        with pytest.raises(ValueError, match="incompatible version"):
            load_registry(tmp_path, **form)

    def test_invalid_slug_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "Capital_Bad")
        _write_questionnaire(folder)
        with pytest.raises(ValueError, match="Invalid system slug"):
            load_registry(tmp_path, **form)

    def test_invalid_json_fails(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        (folder / "questionnaire.json").write_text("{not json")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_registry(tmp_path, **form)


class TestSystemIdentityWarnings:
    def test_missing_system_name_warns_but_loads(
        self, tmp_path: Path, form: dict, caplog: pytest.LogCaptureFixture
    ) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder, system_name="")
        with caplog.at_level(logging.WARNING):
            records = load_registry(tmp_path, **form)
        assert len(records) == 1
        assert records[0].system_name == ""
        assert any("system_name" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Validation: unknown ids — warn but do not fail
# ---------------------------------------------------------------------------


class TestUnknownIdsWarn:
    def test_unknown_question_id_emits_warning(
        self, tmp_path: Path, form: dict, caplog: pytest.LogCaptureFixture
    ) -> None:
        folder = _make_system(tmp_path, "acme")
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


# ---------------------------------------------------------------------------
# aggregate_residual_level
# ---------------------------------------------------------------------------


def _record_with_aggregate(
    *,
    inherent: dict[str, dict],
    effectiveness: dict[str, str],
    aggregate: str,
) -> SystemRecord:
    return SystemRecord(
        slug="x",
        questionnaire={"properties": {}},
        assessment={
            "inherent": inherent,
            "control_effectiveness": effectiveness,
            "residual_likelihood": {},
            "residual_consequence": {},
            "aggregate_residual_level": aggregate,
        },
    )


class TestHistoryLoading:
    """`registry/<slug>/history/` holds prior (questionnaire, assessment)
    pairs. Loader walks the folder, validates each file, pairs them via
    `assessment.questionnaire_exported_at`, and exposes them in oldest-first
    order on `SystemRecord.history`. Each entry carries a precomputed
    `change_summary` against its predecessor; `current_change_summary` is
    the diff between the current pair and the latest history entry.
    """

    def _write_history_pair(
        self,
        history_dir: Path,
        *,
        q_exported_at: str,
        a_exported_at: str,
        answers: dict[str, str] | None = None,
        properties: dict[str, bool | None] | None = None,
    ) -> None:
        history_dir.mkdir(exist_ok=True)
        q_payload = {
            "format": config.QUESTIONNAIRE_FORMAT,
            "version": config.QUESTIONNAIRE_VERSION,
            "exported_at": q_exported_at,
            "system_name": "Acme",
            "system_owner": "Jane",
            "question_ids": list((answers or {"q1": "yes"}).keys()),
            "answers": answers or {"q1": "yes"},
            "detail_ids": [],
            "details": {},
            "property_ids": list((properties or {"p1": True, "p2": False}).keys()),
            "properties": properties or {"p1": True, "p2": False},
        }
        a_payload = {
            "format": config.ASSESSMENT_FORMAT,
            "version": config.ASSESSMENT_VERSION,
            "exported_at": a_exported_at,
            "questionnaire_exported_at": q_exported_at,
            "system_name": "Acme",
            "system_owner": "Jane",
            "risk_ids": ["r1"],
            "property_ids": list(q_payload["property_ids"]),
            "properties": dict(q_payload["properties"]),
            "inherent": {
                "r1": {
                    "likelihood": "likely",
                    "consequence": "major",
                    "level": "high",
                    "firing_conditions": ["p1"],
                }
            },
            "control_effectiveness": {"r1": "ineffective"},
            "residual_likelihood": {"r1": ""},
            "residual_consequence": {"r1": ""},
            "justifications": {"r1": ""},
            "mandated_controls": {"r1": {"c1": False}},
            "mandated_comments": {"r1": {"c1": ""}},
        }
        safe_q = q_exported_at.replace(":", "-")
        safe_a = a_exported_at.replace(":", "-")
        (history_dir / f"{safe_q}-questionnaire.json").write_text(json.dumps(q_payload))
        (history_dir / f"{safe_a}-assessment.json").write_text(json.dumps(a_payload))

    def test_no_history_dir_means_empty_history(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder)
        _write_assessment(folder)
        records = load_registry(tmp_path, **form)
        assert records[0].history == ()

    def test_single_history_pair_loaded_oldest_first(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder, exported_at="2026-04-01T08:00:00Z")
        _write_assessment(folder, exported_at="2026-04-01T09:00:00Z")
        self._write_history_pair(
            folder / "history",
            q_exported_at="2026-01-15T10:00:00Z",
            a_exported_at="2026-01-15T11:00:00Z",
        )
        records = load_registry(tmp_path, **form)
        rec = records[0]
        assert len(rec.history) == 1
        entry = rec.history[0]
        assert entry.questionnaire["exported_at"] == "2026-01-15T10:00:00Z"
        assert entry.assessment is not None
        assert entry.assessment["exported_at"] == "2026-01-15T11:00:00Z"
        # First entry has no predecessor, so populated current_only_ids
        # but empty change lists.
        assert entry.change_summary.is_empty
        assert entry.change_summary.current_only_ids

    def test_multiple_history_pairs_sorted_oldest_first(self, tmp_path: Path, form: dict) -> None:
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder, exported_at="2026-04-01T08:00:00Z")
        _write_assessment(folder, exported_at="2026-04-01T09:00:00Z")
        # Write the newer pair first to verify sort logic isn't insertion-order.
        self._write_history_pair(
            folder / "history",
            q_exported_at="2026-03-01T10:00:00Z",
            a_exported_at="2026-03-01T11:00:00Z",
            answers={"q1": "no"},
            properties={"p1": False, "p2": False},
        )
        self._write_history_pair(
            folder / "history",
            q_exported_at="2026-01-15T10:00:00Z",
            a_exported_at="2026-01-15T11:00:00Z",
        )
        rec = load_registry(tmp_path, **form)[0]
        assert [e.questionnaire["exported_at"] for e in rec.history] == [
            "2026-01-15T10:00:00Z",
            "2026-03-01T10:00:00Z",
        ]
        # The second history entry diffs against the first — q1 flipped yes→no,
        # p1 flipped true→false, so non-empty change lists.
        second_diff = rec.history[1].change_summary
        assert not second_diff.is_empty
        assert any(c.id == "q1" for c in second_diff.answer_changes)

    def test_current_change_summary_diffs_against_latest_history(
        self, tmp_path: Path, form: dict
    ) -> None:
        folder = _make_system(tmp_path, "acme")
        # Current: q1=yes, p1=True, r1 high.
        _write_questionnaire(folder, exported_at="2026-04-01T08:00:00Z")
        _write_assessment(folder, exported_at="2026-04-01T09:00:00Z")
        # History entry: q1=no, p1=False, r1 not_applicable — so the current
        # diff vs history should report q1 changed and the inherent block.
        history_dir = folder / "history"
        history_dir.mkdir()
        q_payload = {
            "format": config.QUESTIONNAIRE_FORMAT,
            "version": config.QUESTIONNAIRE_VERSION,
            "exported_at": "2026-01-15T10:00:00Z",
            "system_name": "Acme",
            "system_owner": "Jane",
            "question_ids": ["q1"],
            "answers": {"q1": "no"},
            "detail_ids": [],
            "details": {},
            "property_ids": ["p1", "p2"],
            "properties": {"p1": False, "p2": False},
        }
        a_payload = {
            "format": config.ASSESSMENT_FORMAT,
            "version": config.ASSESSMENT_VERSION,
            "exported_at": "2026-01-15T11:00:00Z",
            "questionnaire_exported_at": "2026-01-15T10:00:00Z",
            "risk_ids": ["r1"],
            "property_ids": ["p1", "p2"],
            "properties": {"p1": False, "p2": False},
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
        }
        (history_dir / "2026-01-15T10-00-00Z-questionnaire.json").write_text(json.dumps(q_payload))
        (history_dir / "2026-01-15T11-00-00Z-assessment.json").write_text(json.dumps(a_payload))

        rec = load_registry(tmp_path, **form)[0]
        assert rec.current_change_summary is not None
        diff = rec.current_change_summary
        assert any(c.id == "q1" for c in diff.answer_changes)
        # r1 inherent flipped from not_applicable to high.
        risk_change = next((c for c in diff.risk_changes if c.risk_id == "r1"), None)
        assert risk_change is not None
        assert risk_change.before is not None and risk_change.before.level == "not_applicable"
        assert risk_change.after is not None and risk_change.after.level == "high"

    def test_legacy_pair_without_questionnaire_link_falls_back_to_chronology(
        self, tmp_path: Path, form: dict
    ) -> None:
        """An assessment without `questionnaire_exported_at` is paired with
        the latest unused questionnaire whose `exported_at` <= the
        assessment's. Pins the legacy fallback path."""
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder)
        _write_assessment(folder)

        history_dir = folder / "history"
        history_dir.mkdir()
        q_payload = {
            "format": config.QUESTIONNAIRE_FORMAT,
            "version": config.QUESTIONNAIRE_VERSION,
            "exported_at": "2025-12-01T10:00:00Z",
            "system_name": "Acme",
            "system_owner": "Jane",
            "question_ids": ["q1"],
            "answers": {"q1": "yes"},
            "detail_ids": [],
            "details": {},
            "property_ids": ["p1", "p2"],
            "properties": {"p1": True, "p2": False},
        }
        a_payload = {
            "format": config.ASSESSMENT_FORMAT,
            "version": config.ASSESSMENT_VERSION,
            "exported_at": "2025-12-01T11:00:00Z",
            # NB: no questionnaire_exported_at field.
            "risk_ids": ["r1"],
            "property_ids": ["p1", "p2"],
            "properties": {"p1": True, "p2": False},
            "inherent": {
                "r1": {
                    "likelihood": "likely",
                    "consequence": "major",
                    "level": "high",
                    "firing_conditions": ["p1"],
                }
            },
            "control_effectiveness": {"r1": "ineffective"},
            "residual_likelihood": {"r1": ""},
            "residual_consequence": {"r1": ""},
            "justifications": {"r1": ""},
            "mandated_controls": {"r1": {"c1": False}},
            "mandated_comments": {"r1": {"c1": ""}},
        }
        (history_dir / "2025-12-01T10-00-00Z-questionnaire.json").write_text(json.dumps(q_payload))
        (history_dir / "2025-12-01T11-00-00Z-assessment.json").write_text(json.dumps(a_payload))

        rec = load_registry(tmp_path, **form)[0]
        assert len(rec.history) == 1
        assert rec.history[0].assessment is not None

    def test_questionnaire_only_history_entry_is_kept(self, tmp_path: Path, form: dict) -> None:
        """A historical cycle where only the questionnaire was committed (no
        assessment) is preserved as a questionnaire-only history entry."""
        folder = _make_system(tmp_path, "acme")
        _write_questionnaire(folder, exported_at="2026-04-01T08:00:00Z")
        _write_assessment(folder, exported_at="2026-04-01T09:00:00Z")
        history_dir = folder / "history"
        history_dir.mkdir()
        q_payload = {
            "format": config.QUESTIONNAIRE_FORMAT,
            "version": config.QUESTIONNAIRE_VERSION,
            "exported_at": "2026-01-15T10:00:00Z",
            "system_name": "Acme",
            "system_owner": "Jane",
            "question_ids": ["q1"],
            "answers": {"q1": "yes"},
            "detail_ids": [],
            "details": {},
            "property_ids": ["p1", "p2"],
            "properties": {"p1": True, "p2": False},
        }
        (history_dir / "2026-01-15T10-00-00Z-questionnaire.json").write_text(json.dumps(q_payload))
        rec = load_registry(tmp_path, **form)[0]
        assert len(rec.history) == 1
        assert rec.history[0].assessment is None


class TestAggregateResidualLevel:
    def test_no_assessment_is_not_applicable(self) -> None:
        rec = SystemRecord(
            slug="x",
            questionnaire={},
            assessment=None,
        )
        assert aggregate_residual_level(rec, config.RISK_LEVELS) == "not_applicable"

    def test_empty_pick_falls_back_to_worst(self) -> None:
        rec = _record_with_aggregate(
            inherent={
                "r1": {"likelihood": "likely", "consequence": "major", "level": "high"},
            },
            effectiveness={"r1": "ineffective"},
            aggregate="",
        )
        assert aggregate_residual_level(rec, config.RISK_LEVELS) == "high"

    def test_explicit_pick_overrides_worst(self) -> None:
        # Worst would be 'high'; assessor picked 'medium'.
        rec = _record_with_aggregate(
            inherent={
                "r1": {"likelihood": "likely", "consequence": "major", "level": "high"},
            },
            effectiveness={"r1": "ineffective"},
            aggregate="medium",
        )
        assert aggregate_residual_level(rec, config.RISK_LEVELS) == "medium"

    def test_missing_field_falls_back_to_worst(self) -> None:
        # Older payload without the aggregate field at all — fallback path.
        rec = SystemRecord(
            slug="x",
            questionnaire={"properties": {}},
            assessment={
                "inherent": {
                    "r1": {"likelihood": "likely", "consequence": "major", "level": "high"},
                },
                "control_effectiveness": {"r1": "ineffective"},
            },
        )
        assert aggregate_residual_level(rec, config.RISK_LEVELS) == "high"
