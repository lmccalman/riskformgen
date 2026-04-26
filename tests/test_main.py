"""Smoke test for main.py — end-to-end build into a tmpdir."""

from __future__ import annotations

from pathlib import Path

from py_mini_racer import MiniRacer

import config
import main
from tests.js_harness import _BOOTSTRAP_JS


def test_main_builds_expected_files(tmp_path: Path, monkeypatch):
    """main() produces a non-empty output directory with all expected assets."""
    monkeypatch.setattr(config, "output_dir", tmp_path / "output")

    main.main()

    out = tmp_path / "output"
    pages = (
        out / "index.html",
        out / "questionnaire.html",
        out / "assessment.html",
        out / "registry.html",
    )
    factories = (
        out / "app-questionnaire.js",
        out / "app-assessment.js",
    )
    assets = (
        out / "bulma.min.css",
        out / "input.css",
        out / config.alpine_src.name,
        out / config.persist_src.name,
    )

    for f in pages + factories + assets:
        assert f.exists(), f"Expected {f.name} in output"
        assert f.stat().st_size > 0, f"{f.name} is empty"

    landing = (out / "index.html").read_text()
    assert "questionnaire.html" in landing
    assert "assessment.html" in landing
    assert "registry.html" in landing

    questionnaire_html = (out / "questionnaire.html").read_text()
    assert 'x-data="questionnaire"' in questionnaire_html
    assessment_html = (out / "assessment.html").read_text()
    assert 'x-data="assessment"' in assessment_html

    questionnaire_js = (out / "app-questionnaire.js").read_text()
    assert "Alpine.data('questionnaire'" in questionnaire_js
    assessment_js = (out / "app-assessment.js").read_text()
    assert "Alpine.data('assessment'" in assessment_js


def _eval_factory(js: str) -> None:
    ctx = MiniRacer()
    ctx.eval(_BOOTSTRAP_JS)
    ctx.eval(js)
    ctx.eval("var scope = __state.factory();")
    ctx.eval("if (typeof scope.init === 'function') scope.init();")


def test_built_factories_parse(tmp_path: Path, monkeypatch):
    """Both emitted factory files must parse and execute without throwing — a
    Jinja syntax error producing malformed JS would still pass the size>0
    check above but break in the browser."""
    monkeypatch.setattr(config, "output_dir", tmp_path / "output")
    main.main()

    _eval_factory((tmp_path / "output" / "app-questionnaire.js").read_text())
    _eval_factory((tmp_path / "output" / "app-assessment.js").read_text())
