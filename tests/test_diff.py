"""Fixture-driven tests for `diff.diff_pair`.

Each subfolder under `tests/fixtures/diff/` is a complete scenario:
inputs in `prev_q.json` / `prev_a.json` / `cur_q.json` / `cur_a.json` and
the expected output in `expected.json`. The same fixtures are also loaded
by `tests/test_js_behaviour.py` to assert JS/Python parity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from diff import diff_pair

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "diff"


def _scenarios() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())


def _load(folder: Path, name: str) -> dict | None:
    path = folder / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


@pytest.mark.parametrize("folder", _scenarios(), ids=lambda p: p.name)
def test_diff_matches_expected(folder: Path) -> None:
    prev_q = _load(folder, "prev_q.json")
    prev_a = _load(folder, "prev_a.json")
    cur_q = _load(folder, "cur_q.json")
    cur_a = _load(folder, "cur_a.json")
    assert cur_q is not None, f"{folder.name}: cur_q.json is required"

    expected = _load(folder, "expected.json")
    assert expected is not None, f"{folder.name}: expected.json is required"

    summary = diff_pair(prev_q, prev_a, cur_q, cur_a)
    assert summary.to_dict() == expected


def test_no_change_summary_is_empty() -> None:
    folder = FIXTURES_DIR / "no_change"
    summary = diff_pair(
        _load(folder, "prev_q.json"),
        _load(folder, "prev_a.json"),
        _load(folder, "cur_q.json"),  # type: ignore[arg-type]
        _load(folder, "cur_a.json"),
    )
    assert summary.is_empty


def test_first_record_summary_is_empty_change_lists_with_current_only_ids() -> None:
    folder = FIXTURES_DIR / "first_record"
    summary = diff_pair(
        None,
        None,
        _load(folder, "cur_q.json"),  # type: ignore[arg-type]
        _load(folder, "cur_a.json"),
    )
    assert summary.is_empty
    assert summary.current_only_ids
    assert "questions" in summary.current_only_ids
    assert "risks" in summary.current_only_ids
