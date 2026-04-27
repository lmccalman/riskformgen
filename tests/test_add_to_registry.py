"""Tests for `scripts/add_to_registry.py` — the registry promotion helper.

These exercise the script's filesystem-layout invariants without
actually shelling out: each test imports `main()` and drives it with
`sys.argv`. The fixtures use the canonical format/version constants from
`config.py` so the validation path runs end-to-end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import config
from scripts import add_to_registry


def _q_payload(exported_at: str = "2026-04-01T08:00:00Z") -> dict:
    return {
        "format": config.QUESTIONNAIRE_FORMAT,
        "version": config.QUESTIONNAIRE_VERSION,
        "build_id": "abcd1234",
        "exported_at": exported_at,
        "question_ids": ["q1"],
        "answers": {"q1": "yes"},
        "detail_ids": [],
        "details": {},
        "property_ids": ["p1"],
        "properties": {"p1": True},
    }


def _a_payload(
    exported_at: str = "2026-04-01T09:00:00Z",
    questionnaire_exported_at: str = "2026-04-01T08:00:00Z",
) -> dict:
    return {
        "format": config.ASSESSMENT_FORMAT,
        "version": config.ASSESSMENT_VERSION,
        "build_id": "abcd1234",
        "exported_at": exported_at,
        "questionnaire_exported_at": questionnaire_exported_at,
        "risk_ids": ["r1"],
        "property_ids": ["p1"],
        "properties": {"p1": True},
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
        "mandated_controls": {"r1": {}},
        "mandated_comments": {"r1": {}},
    }


def _run(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["add_to_registry.py", *args])
    return add_to_registry.main()


def test_creates_new_system_folder_with_pair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "registry_dir", tmp_path / "registry")
    q_path = tmp_path / "new-q.json"
    a_path = tmp_path / "new-a.json"
    q_path.write_text(json.dumps(_q_payload()))
    a_path.write_text(json.dumps(_a_payload()))

    rc = _run(
        monkeypatch,
        ["acme", "--questionnaire", str(q_path), "--assessment", str(a_path)],
    )
    assert rc == 0
    target = tmp_path / "registry" / "acme"
    assert (target / "questionnaire.json").exists()
    assert (target / "assessment.json").exists()
    assert not (target / "history").exists()


def test_existing_pair_moves_to_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "registry_dir", tmp_path / "registry")
    target = tmp_path / "registry" / "acme"
    target.mkdir(parents=True)
    # Existing current pair.
    target.joinpath("questionnaire.json").write_text(
        json.dumps(_q_payload(exported_at="2026-01-15T10:00:00Z"))
    )
    target.joinpath("assessment.json").write_text(
        json.dumps(
            _a_payload(
                exported_at="2026-01-15T11:00:00Z",
                questionnaire_exported_at="2026-01-15T10:00:00Z",
            )
        )
    )

    new_q = tmp_path / "new-q.json"
    new_a = tmp_path / "new-a.json"
    new_q.write_text(json.dumps(_q_payload(exported_at="2026-04-01T08:00:00Z")))
    new_a.write_text(
        json.dumps(
            _a_payload(
                exported_at="2026-04-01T09:00:00Z",
                questionnaire_exported_at="2026-04-01T08:00:00Z",
            )
        )
    )

    _run(monkeypatch, ["acme", "--questionnaire", str(new_q), "--assessment", str(new_a)])

    history_dir = target / "history"
    history_files = sorted(p.name for p in history_dir.iterdir())
    assert "2026-01-15T10-00-00Z-questionnaire.json" in history_files
    assert "2026-01-15T11-00-00Z-assessment.json" in history_files

    # Current files reflect the new pair.
    cur_q = json.loads((target / "questionnaire.json").read_text())
    assert cur_q["exported_at"] == "2026-04-01T08:00:00Z"


def test_assessment_without_link_field_is_filled_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A legacy export without `questionnaire_exported_at` is reconciled
    from the supplied questionnaire."""
    monkeypatch.setattr(config, "registry_dir", tmp_path / "registry")
    q_path = tmp_path / "q.json"
    a_path = tmp_path / "a.json"
    q = _q_payload()
    a = _a_payload()
    a.pop("questionnaire_exported_at")
    q_path.write_text(json.dumps(q))
    a_path.write_text(json.dumps(a))

    _run(monkeypatch, ["acme", "--questionnaire", str(q_path), "--assessment", str(a_path)])
    written = json.loads((tmp_path / "registry" / "acme" / "assessment.json").read_text())
    assert written["questionnaire_exported_at"] == q["exported_at"]


def test_assessment_with_disagreeing_link_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "registry_dir", tmp_path / "registry")
    q_path = tmp_path / "q.json"
    a_path = tmp_path / "a.json"
    q_path.write_text(json.dumps(_q_payload()))
    a_path.write_text(json.dumps(_a_payload(questionnaire_exported_at="2025-01-01T00:00:00Z")))
    with pytest.raises(ValueError, match="disagrees"):
        _run(monkeypatch, ["acme", "--questionnaire", str(q_path), "--assessment", str(a_path)])


def test_questionnaire_only_promotion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An in-flight cycle (questionnaire only, no assessment yet) is promotable."""
    monkeypatch.setattr(config, "registry_dir", tmp_path / "registry")
    q_path = tmp_path / "q.json"
    q_path.write_text(json.dumps(_q_payload()))
    rc = _run(monkeypatch, ["acme", "--questionnaire", str(q_path)])
    assert rc == 0
    target = tmp_path / "registry" / "acme"
    assert (target / "questionnaire.json").exists()
    assert not (target / "assessment.json").exists()


def test_invalid_slug_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "registry_dir", tmp_path / "registry")
    q_path = tmp_path / "q.json"
    q_path.write_text(json.dumps(_q_payload()))
    with pytest.raises(SystemExit):
        _run(monkeypatch, ["Capital_Bad", "--questionnaire", str(q_path)])
